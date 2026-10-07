import os
import duckdb
from sklearn.ensemble import HistGradientBoostingRegressor

con = duckdb.connect("data/ipl.duckdb", read_only=True)
df = con.sql("""
    with t as (
        select d.batter_id, d.batter, d.bowler_id, d.bowler,
               d.innings, d."over" as ov, d.is_legal, d.runs_total, d.runs_batter,
               coalesce(sum(d.is_wicket) over w, 0)::INT as wickets_down,
               coalesce(sum(d.is_legal) over w, 0)::INT as balls_before
        from raw_deliveries d
        window w as (partition by d.match_id, d.innings
                     order by d."over", d.ball_in_over, d.rowid
                     rows between unbounded preceding and 1 preceding)
    )
    select * from t where is_legal = 1
""").df()

feats = ["innings", "ov", "wickets_down", "balls_before"]
X = df[feats]

def fit(y):
    m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0)
    return m.fit(X, y).predict(X)

df["exp_total"] = fit(df.runs_total)
df["exp_bat"] = fit(df.runs_batter)

bat = df.groupby("batter_id").agg(batter=("batter", "first"), balls=("runs_batter", "size"),
                                  runs=("runs_batter", "sum"), expected=("exp_bat", "sum"))
bat["runs_above_exp"] = (bat.runs - bat.expected).round(1)
bat["per_100_balls"] = (100 * bat.runs_above_exp / bat.balls).round(1)
bat = bat[bat.balls >= 200].sort_values("per_100_balls", ascending=False)

bowl = df.groupby("bowler_id").agg(bowler=("bowler", "first"), balls=("runs_total", "size"),
                                   runs=("runs_total", "sum"), expected=("exp_total", "sum"))
bowl["runs_saved"] = (bowl.expected - bowl.runs).round(1)
bowl["per_100_balls"] = (100 * bowl.runs_saved / bowl.balls).round(1)
bowl = bowl[bowl.balls >= 200].sort_values("per_100_balls", ascending=False)

os.makedirs("analysis/output", exist_ok=True)
bat.to_csv("analysis/output/batter_runs_above_expected.csv")
bowl.to_csv("analysis/output/bowler_runs_saved.csv")

pd_opts = dict(max_rows=20)
print("TOP BATTERS (runs above expected per 100 balls, min 200 balls)")
print(bat[["batter", "balls", "runs_above_exp", "per_100_balls"]].head(10).to_string(index=False))
print()
print("TOP BOWLERS (runs saved per 100 balls, min 200 balls)")
print(bowl[["bowler", "balls", "runs_saved", "per_100_balls"]].head(10).to_string(index=False))