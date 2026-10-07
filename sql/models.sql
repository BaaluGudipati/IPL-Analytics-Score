-- Marts built on raw_matches / raw_deliveries. Rates are computed from totals (properly weighted).

CREATE OR REPLACE VIEW batter_season AS
SELECT d.batter_id, any_value(d.batter) AS batter, m.season,
       sum(d.runs_batter) AS runs,
       count(*) FILTER (WHERE NOT d.is_wide) AS balls_faced,
       round(100.0 * sum(d.runs_batter) / nullif(count(*) FILTER (WHERE NOT d.is_wide), 0), 2) AS strike_rate,
       count(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
       count(*) FILTER (WHERE d.runs_batter = 4) AS fours
FROM raw_deliveries d JOIN raw_matches m USING (match_id)
GROUP BY d.batter_id, m.season;

CREATE OR REPLACE VIEW bowler_season AS
SELECT d.bowler_id, any_value(d.bowler) AS bowler, m.season,
       sum(d.is_bowler_wicket) AS wickets,
       sum(d.is_legal) AS legal_balls,
       sum(d.runs_total) AS runs_conceded,
       round(6.0 * sum(d.runs_total) / nullif(sum(d.is_legal), 0), 2) AS economy
FROM raw_deliveries d JOIN raw_matches m USING (match_id)
GROUP BY d.bowler_id, m.season;

CREATE OR REPLACE VIEW phase_stats AS
SELECT m.season, d.phase,
       sum(d.runs_total) AS runs, sum(d.is_legal) AS legal_balls,
       sum(d.is_wicket) AS wickets,
       round(6.0 * sum(d.runs_total) / nullif(sum(d.is_legal), 0), 2) AS run_rate
FROM raw_deliveries d JOIN raw_matches m USING (match_id)
GROUP BY m.season, d.phase;

CREATE OR REPLACE VIEW phase_innings_stats AS
SELECT innings, phase,
       count(DISTINCT match_id) AS matches,
       sum(runs_total) AS runs,
       sum(is_legal) AS legal_balls,
       round(6.0 * sum(runs_total) / nullif(sum(is_legal), 0), 2) AS run_rate,
       sum(is_wicket) AS wickets,
       round(sum(is_legal)::DOUBLE / nullif(sum(is_wicket), 0), 1) AS balls_per_wicket
FROM raw_deliveries
GROUP BY innings, phase;

CREATE OR REPLACE VIEW toss_impact AS
SELECT season, count(*) AS matches,
       count(*) FILTER (WHERE toss_winner = winner) AS toss_winner_won,
       round(100.0 * count(*) FILTER (WHERE toss_winner = winner) / count(*), 1) AS toss_win_pct
FROM raw_matches WHERE winner IS NOT NULL GROUP BY season;

CREATE OR REPLACE VIEW toss_stats AS
SELECT season, toss_decision,
       count(*) AS matches,
       sum((toss_winner = winner)::INT) AS toss_winner_won,
       round(100.0 * sum((toss_winner = winner)::INT) / count(*), 1) AS toss_win_pct
FROM raw_matches
WHERE winner IS NOT NULL
GROUP BY season, toss_decision;

CREATE OR REPLACE VIEW venue_stats AS
WITH inn AS (
    SELECT match_id, innings, sum(runs_total) AS runs
    FROM raw_deliveries GROUP BY match_id, innings
)
SELECT m.venue, count(DISTINCT m.match_id) AS matches,
       round(avg(inn.runs) FILTER (WHERE inn.innings = 1), 1) AS avg_1st_inns,
       round(avg(inn.runs) FILTER (WHERE inn.innings = 2), 1) AS avg_2nd_inns
FROM inn JOIN raw_matches m USING (match_id)
GROUP BY m.venue;

CREATE OR REPLACE VIEW chase_stats AS
WITH m AS (
    SELECT match_id, venue, season, winner,
           CASE WHEN toss_decision = 'bat' THEN toss_winner
                WHEN toss_winner = team1 THEN team2
                ELSE team1 END AS bat_first_team
    FROM raw_matches
    WHERE winner IS NOT NULL
)
SELECT venue, count(*) AS matches,
       round(100.0 * sum((winner = bat_first_team)::INT) / count(*), 1) AS bat_first_win_pct,
       round(100.0 * sum((winner <> bat_first_team)::INT) / count(*), 1) AS chase_win_pct
FROM m
GROUP BY venue;
CREATE OR REPLACE VIEW matchups AS
SELECT d.batter_id, any_value(d.batter) AS batter,
       d.bowler_id, any_value(d.bowler) AS bowler,
       count(*) FILTER (WHERE NOT d.is_wide) AS balls,
       sum(d.runs_batter) AS runs,
       sum(d.is_bowler_wicket) AS dismissals,
       round(100.0 * sum(d.runs_batter) / nullif(count(*) FILTER (WHERE NOT d.is_wide), 0), 1) AS strike_rate
FROM raw_deliveries d
GROUP BY d.batter_id, d.bowler_id;
CREATE OR REPLACE VIEW batter_overall AS
SELECT batter_id,
       100.0 * sum(runs_batter) / nullif(count(*) FILTER (WHERE NOT is_wide), 0) AS overall_sr,
       sum(is_bowler_wicket)::DOUBLE / nullif(count(*) FILTER (WHERE NOT is_wide), 0) AS dis_per_ball
FROM raw_deliveries
GROUP BY batter_id;

CREATE OR REPLACE VIEW matchups_vs_baseline AS
SELECT m.batter, m.bowler, m.balls, m.runs, m.dismissals, m.strike_rate,
       round(b.overall_sr, 1) AS batter_overall_sr,
       round(m.strike_rate - b.overall_sr, 1) AS sr_diff,
       round(m.balls * b.dis_per_ball, 2) AS expected_dismissals,
       round(m.dismissals - m.balls * b.dis_per_ball, 2) AS dismissals_vs_expected
FROM matchups m JOIN batter_overall b USING (batter_id);
CREATE OR REPLACE VIEW bowler_vs_expected AS
WITH league AS (
    SELECT phase,
           sum(is_bowler_wicket)::DOUBLE / sum(is_legal) AS wk_rate
    FROM raw_deliveries
    GROUP BY phase
), b AS (
    SELECT bowler_id, any_value(bowler) AS bowler, phase,
           sum(is_legal) AS balls,
           sum(is_bowler_wicket) AS wkts,
           sum(runs_total) AS runs
    FROM raw_deliveries
    GROUP BY bowler_id, phase
)
SELECT b.bowler_id, any_value(b.bowler) AS bowler,
       sum(b.balls) AS balls,
       sum(b.wkts) AS wickets,
       round(sum(b.balls * l.wk_rate), 1) AS expected_wickets,
       round(sum(b.wkts) - sum(b.balls * l.wk_rate), 1) AS wickets_above_expected,
       round(6.0 * sum(b.runs) / sum(b.balls), 2) AS economy
FROM b JOIN league l USING (phase)
GROUP BY b.bowler_id
HAVING sum(b.balls) >= 200;
CREATE OR REPLACE VIEW bowler_vs_expected AS
WITH league AS (
    SELECT phase,
           sum(is_bowler_wicket)::DOUBLE / sum(is_legal) AS wk_rate,
           sum(runs_total)::DOUBLE / sum(is_legal) AS runs_per_ball
    FROM raw_deliveries
    GROUP BY phase
), b AS (
    SELECT bowler_id, any_value(bowler) AS bowler, phase,
           sum(is_legal) AS balls,
           sum(is_bowler_wicket) AS wkts,
           sum(runs_total) AS runs
    FROM raw_deliveries
    GROUP BY bowler_id, phase
)
SELECT b.bowler_id, any_value(b.bowler) AS bowler,
       sum(b.balls) AS balls,
       sum(b.wkts) AS wickets,
       round(sum(b.balls * l.wk_rate), 1) AS expected_wickets,
       round(sum(b.wkts) - sum(b.balls * l.wk_rate), 1) AS wickets_above_expected,
       round(6.0 * sum(b.runs) / sum(b.balls), 2) AS economy,
       round(sum(b.balls * l.runs_per_ball) - sum(b.runs), 1) AS runs_saved
FROM b JOIN league l USING (phase)
GROUP BY b.bowler_id
HAVING sum(b.balls) >= 200;