import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import query_df

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_squared_error, r2_score

df = query_df("""
    with t as (
        select m.season, d.match_id, d.innings, d."over" as ov, d.is_legal, d.runs_total,
               coalesce(sum(d.is_wicket) over w, 0)::INT as wickets_down,
               coalesce(sum(d.is_legal) over w, 0)::INT as balls_before
        from raw_deliveries d join raw_matches m using (match_id)
        window w as (partition by d.match_id, d.innings
                     order by d."over", d.ball_in_over
                     rows between unbounded preceding and 1 preceding)
    )
    select season, innings, ov, wickets_down, balls_before, runs_total
    from t where is_legal = 1
""")

train = df[df.season <= 2025]
test = df[df.season == 2026]
print("train balls:", len(train), "test balls:", len(test))

feats = ["innings", "ov", "wickets_down", "balls_before"]
y_tr, y_te = train.runs_total, test.runs_total

# baseline 1: one constant
p_const = [y_tr.mean()] * len(test)

# baseline 2: average by (innings, over)
by_over = train.groupby(["innings", "ov"]).runs_total.mean().rename("p")
p_over = test.join(by_over, on=["innings", "ov"]).p.fillna(y_tr.mean())

# model
model = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0)
model.fit(train[feats], y_tr)
p_model = model.predict(test[feats])

def rmse(p): return mean_squared_error(y_te, p) ** 0.5

print("RMSE constant :", round(rmse(p_const), 4))
print("RMSE by-over  :", round(rmse(p_over), 4), " R2:", round(r2_score(y_te, p_over), 4))
print("RMSE model    :", round(rmse(p_model), 4), " R2:", round(r2_score(y_te, p_model), 4))