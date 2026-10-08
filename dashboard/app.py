"""IPL Analytics Engine dashboard.  Run:  streamlit run dashboard/app.py
Reads the Supabase (Postgres) marts built by ingestion/load_cricsheet.py.
Data: Cricsheet (cricsheet.org).
"""
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # Streamlit Cloud: URL lives in secrets
    os.environ.setdefault("SUPABASE_DB_URL", st.secrets["SUPABASE_DB_URL"])
except Exception:
    pass
from db import query_df

st.set_page_config(page_title="IPL Analytics Engine", layout="wide")


@st.cache_data(ttl=3600)
def q(sql, params=()):
    return query_df(sql, list(params))


seasons = q("select distinct season from raw_matches order by season")["season"].tolist()
st.title("IPL Analytics Engine")
st.caption(f"{len(seasons)} seasons ({seasons[0]}-{seasons[-1]}), ball-by-ball data from Cricsheet.")

lo, hi = st.sidebar.select_slider("Seasons", options=seasons, value=(seasons[0], seasons[-1]))
min_balls = st.sidebar.slider("Minimum balls (players)", 50, 1000, 300, step=50)

tab_phase, tab_venue, tab_players, tab_match = st.tabs(
    ["Phases", "Venues & toss", "Batters & bowlers", "Matchups"])

with tab_phase:
    st.subheader("Run rate by phase")
    st.caption("Powerplay = overs 1-6, middle = 7-15, death = 16-20. Run rate = runs per over.")
    ph = q("""select season, phase, run_rate, runs, legal_balls, wickets from phase_stats
              where season between %s and %s""", (lo, hi))
    st.line_chart(ph.pivot(index="season", columns="phase", values="run_rate"))
    pi = q("select * from phase_innings_stats order by innings, phase")
    st.markdown("**By innings (all seasons)**")
    st.dataframe(pi, hide_index=True, width='stretch')

with tab_venue:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Toss impact")
        t = q("select season, toss_win_pct from toss_impact where season between %s and %s order by season", (lo, hi))
        st.line_chart(t.set_index("season"))
        st.caption("% of matches won by the toss winner (50% = no effect). "
                   "Single seasons are small samples, so expect noise.")
        ts = q("""select toss_decision, sum(matches) matches, sum(toss_winner_won) toss_winner_won,
                  round(100.0*sum(toss_winner_won)/sum(matches),1) toss_win_pct
                  from toss_stats where season between %s and %s group by 1""", (lo, hi))
        st.dataframe(ts, hide_index=True, width='stretch')
    with c2:
        st.subheader("Venues")
        min_m = st.slider("Minimum matches at venue", 1, 50, 10)
        v = q("""select v.venue, v.matches, v.avg_1st_inns, v.avg_2nd_inns, c.bat_first_win_pct, c.chase_win_pct
                 from venue_stats v join chase_stats c using (venue) where v.matches >= %s
                 order by v.avg_1st_inns desc""", (min_m,))
        st.dataframe(v, hide_index=True, width='stretch')
        st.caption("Venue and chase tables cover all loaded seasons.")

with tab_players:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top run scorers")
        b = q("""select batter, sum(runs) runs, sum(balls_faced) balls,
                 round(100.0*sum(runs)/sum(balls_faced),1) strike_rate,
                 sum(sixes) sixes, sum(fours) fours
                 from batter_season where season between %s and %s group by batter_id, batter
                 having sum(balls_faced) >= %s order by runs desc limit 25""", (lo, hi, min_balls))
        st.dataframe(b, hide_index=True, width='stretch')
    with c2:
        st.subheader("Top wicket takers")
        w = q("""select bowler, sum(wickets) wickets, sum(legal_balls) balls,
                 round(6.0*sum(runs_conceded)/sum(legal_balls),2) economy
                 from bowler_season where season between %s and %s group by bowler_id, bowler
                 having sum(legal_balls) >= %s order by wickets desc limit 25""", (lo, hi, min_balls))
        st.dataframe(w, hide_index=True, width='stretch')
    st.subheader("Bowlers: runs saved vs league average (by phase)")
    st.caption("All seasons. Compares each bowler with the league run rate in the same phase. Min 200 balls.")
    bv = q("select bowler, balls, wickets, expected_wickets, wickets_above_expected, economy, runs_saved "
           "from bowler_vs_expected order by runs_saved desc limit 25")
    st.dataframe(bv, hide_index=True, width='stretch')

with tab_match:
    st.subheader("Batter vs bowler")
    st.caption("All seasons. Small samples mislead: use the minimum-balls filter. "
               "Expected dismissals use the batter's overall dismissal rate.")
    mb = st.slider("Minimum balls in matchup", 6, 60, 20)
    name = st.text_input("Filter by batter or bowler name (optional)")
    m = q("select * from matchups_vs_baseline where balls >= %s order by balls desc", (mb,))
    if name:
        m = m[m.batter.str.contains(name, case=False) | m.bowler.str.contains(name, case=False)]
    st.dataframe(m.head(200), hide_index=True, width='stretch')
