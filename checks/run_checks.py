import sys
import duckdb

con = duckdb.connect("data/ipl.duckdb", read_only=True)
failures = []

def check(name, query, expect_zero=True, minimum=None):
    val = con.sql(query).fetchone()[0]
    ok = (val == 0) if expect_zero else (val >= minimum)
    print(("PASS" if ok else "FAIL"), name, "->", val)
    if not ok:
        failures.append(name)

check("duplicate match_id in raw_matches",
      "select count(*) - count(distinct match_id) from raw_matches")
check("matches with null venue",
      "select count(*) from raw_matches where venue is null")
check("old venue alias still present",
      "select count(*) from raw_matches where venue like '%New Chandigarh%'")
check("toss_winner not one of the two teams",
      "select count(*) from raw_matches where toss_winner not in (team1, team2)")
check("winner not one of the two teams",
      "select count(*) from raw_matches where winner is not null and winner not in (team1, team2)")
check("deliveries with no matching match",
      "select count(*) from raw_deliveries d left join raw_matches m using (match_id) where m.match_id is null")
check("matches with no deliveries",
      "select count(*) from raw_matches m left join (select distinct match_id from raw_deliveries) d using (match_id) where d.match_id is null")
check("deliveries with null batter_id or bowler_id",
      "select count(*) from raw_deliveries where batter_id is null or bowler_id is null")
check("innings 1/2 with more than 120 legal balls",
      "select count(*) from (select match_id, innings, sum(is_legal) b from raw_deliveries where innings in (1,2) group by all having b > 120)")
check("seasons with fewer than 60 matches",
      "select count(*) from (select season, count(*) c from raw_matches group by season having c < 60)")
check("total matches loaded (min 200)",
      "select count(*) from raw_matches", expect_zero=False, minimum=200)

if failures:
    print("\nFAILED:", ", ".join(failures))
    sys.exit(1)
print("\nAll checks passed")