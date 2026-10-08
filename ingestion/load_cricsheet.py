"""Download Cricsheet IPL data and load it into Supabase (Postgres) via SUPABASE_DB_URL.

All seasons are loaded by default; use --seasons N to keep only the last N.
Usage:  python ingestion/load_cricsheet.py [--seasons N] [--json-dir PATH]
Data: Cricsheet (cricsheet.org). Check their licence/attribution before publishing.
"""
import argparse, io, json, sys, urllib.request, zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from db import connect

URL = "https://cricsheet.org/downloads/ipl_json.zip"
NOT_BOWLER_WICKET = {"run out", "retired hurt", "retired out", "obstructing the field"}
VENUE_ALIASES = {
    "Maharaja Yadavindra Singh International Cricket Stadium, New Chandigarh":
        "Maharaja Yadavindra Singh International Cricket Stadium, Mullanpur",
}
clean_venue = lambda v: VENUE_ALIASES.get(v, v)


DDL = """
CREATE TABLE raw_matches (
    match_id text PRIMARY KEY, season int, date date, venue text, city text,
    team1 text, team2 text, toss_winner text, toss_decision text, winner text);
CREATE TABLE raw_deliveries (
    match_id text REFERENCES raw_matches, innings smallint, batting_team text,
    "over" smallint, ball_in_over smallint, phase text,
    batter_id text, batter text, bowler_id text, bowler text,
    runs_batter smallint, runs_total smallint,
    is_wide smallint, is_noball smallint, is_legal smallint,
    is_wicket smallint, is_bowler_wicket smallint,
    PRIMARY KEY (match_id, innings, "over", ball_in_over));
-- Supabase enables RLS on new tables; give the read-only dashboard role a select policy
ALTER TABLE raw_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_deliveries ENABLE ROW LEVEL SECURITY;
CREATE POLICY reader_select ON raw_matches FOR SELECT TO ipl_reader USING (true);
CREATE POLICY reader_select ON raw_deliveries FOR SELECT TO ipl_reader USING (true);
"""

def season_year(date):
    """Season = calendar year of the match date. Cricsheet labels like '2007/08' or '2009/10'
    would otherwise merge or mislabel seasons."""
    return int(str(date)[:4])


def read_matches(json_dir, zip_bytes):
    if json_dir:
        for p in sorted(Path(json_dir).glob("*.json")):
            yield p.stem, json.loads(p.read_text(encoding="utf-8"))
    else:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for n in z.namelist():
                if n.endswith(".json"):
                    yield Path(n).stem, json.loads(z.read(n))


def parse(match_id, m):
    info = m["info"]
    people = info.get("registry", {}).get("people", {})
    pid = lambda name: people.get(name, name)  # id survives name changes
    teams = info["teams"]
    match = dict(
        match_id=match_id, season=season_year(info["dates"][0]),
        date=info["dates"][0], venue=clean_venue(info.get("venue")), city=info.get("city"),
        team1=teams[0], team2=teams[1],
        toss_winner=info.get("toss", {}).get("winner"),
        toss_decision=info.get("toss", {}).get("decision"),
        winner=info.get("outcome", {}).get("winner"),
    )
    balls = []
    for inn_no, inn in enumerate(m.get("innings", []), start=1):
        if inn.get("super_over"):
            continue
        for ov in inn["overs"]:
            over = ov["over"]
            phase = "powerplay" if over < 6 else "middle" if over < 15 else "death"
            for i, d in enumerate(ov["deliveries"], start=1):
                ex = d.get("extras", {})
                w = d.get("wickets", [])
                balls.append(dict(
                    match_id=match_id, innings=inn_no, batting_team=inn["team"],
                    over=over, ball_in_over=i, phase=phase,
                    batter_id=pid(d["batter"]), batter=d["batter"],
                    bowler_id=pid(d["bowler"]), bowler=d["bowler"],
                    runs_batter=d["runs"]["batter"], runs_total=d["runs"]["total"],
                    is_wide=int("wides" in ex), is_noball=int("noballs" in ex),
                    is_legal=int("wides" not in ex and "noballs" not in ex),
                    is_wicket=int(len(w) > 0),
                    is_bowler_wicket=int(any(x["kind"] not in NOT_BOWLER_WICKET for x in w)),
                ))
    return match, balls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=None, help="keep only the last N seasons (default: all)")
    ap.add_argument("--json-dir", help="use local Cricsheet JSON files instead of downloading")
    a = ap.parse_args()

    zip_bytes = None
    if not a.json_dir:
        print("Downloading", URL)
        zip_bytes = urllib.request.urlopen(URL, timeout=120).read()

    parsed = [parse(mid, m) for mid, m in read_matches(a.json_dir, zip_bytes)]
    latest = max(p[0]["season"] for p in parsed)
    first = latest - a.seasons + 1 if a.seasons else min(p[0]["season"] for p in parsed)
    keep = [p for p in parsed if p[0]["season"] >= first]
    matches = pd.DataFrame([p[0] for p in keep])
    deliveries = pd.DataFrame([b for p in keep for b in p[1]])

    with connect() as con:
        con.execute("DROP TABLE IF EXISTS raw_deliveries CASCADE; DROP TABLE IF EXISTS raw_matches CASCADE")
        con.execute(DDL)
        for table, df in (("raw_matches", matches), ("raw_deliveries", deliveries)):
            cols = ", ".join(f'"{c}"' for c in df.columns)
            with con.cursor().copy(f"COPY {table} ({cols}) FROM STDIN (FORMAT csv)") as cp:
                cp.write(df.to_csv(index=False, header=False))
        con.execute((ROOT / "sql" / "models.sql").read_text(encoding="utf-8"))

        # reconciliation check from the plan: match count vs source
        n_src, n_db = len(keep), con.execute("SELECT count(*) FROM raw_matches").fetchone()[0]
        assert n_src == n_db, f"match count mismatch {n_src} vs {n_db}"
    print(f"Loaded {n_db} matches, {len(deliveries):,} deliveries (seasons {first}-{latest}) -> Supabase")


if __name__ == "__main__":
    main()