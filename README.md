# IPL Analytics Engine

Ball-by-ball IPL analytics built on Supabase (Postgres) and SQL, with data-quality checks and a scheduled refresh.
Upgrade of [ipl-2025-analysis](https://github.com/IG-08/ipl-2025-analysis) (one season, Excel/Tableau) into a reproducible pipeline.

**Status:** all IPL seasons 2008-2026 loaded (1,243 matches, ~296k deliveries); dashboard built. Screenshots, findings and publishing still to do (see Roadmap).

## Data

[Cricsheet](https://cricsheet.org) ball-by-ball JSON (`ipl_json.zip`). Credit to Cricsheet.
Check their licence/attribution terms before republishing any data or derived figures.

Players are keyed by the Cricsheet registry ID, so a player who changes name is not split in two.
Season = calendar year of the match date (Cricsheet's '2007/08'-style labels are not used). Super overs are excluded. Venue aliases are normalised (e.g. New Chandigarh -> Mullanpur).

## Pipeline

```
Cricsheet zip -> ingestion/load_cricsheet.py -> Supabase raw_matches / raw_deliveries
              -> sql/models.sql (views) -> checks/run_checks.py -> analysis/ -> dashboard/
```

## Repo layout

| Path | Contents |
|---|---|
| `ingestion/` | Download + load script (also applies `sql/models.sql`) |
| `sql/models.sql` | Marts: season stats, phase stats, toss, venue, chase, matchups, bowler vs expected |
| `checks/` | Data-quality checks (run in CI; non-zero exit on failure) |
| `analysis/` | Expected-runs model and runs-above-expected rankings |
| `dashboard/` | Streamlit app (`streamlit run dashboard/app.py`); reads the Supabase marts |
| `.github/workflows/refresh.yaml` | Weekly reload + checks (Mondays 03:00 UTC) |

## Run it

Copy `.env.example` to `.env` and set `SUPABASE_DB_URL` (CI uses a repo secret of the same name; use the Session pooler URL there, since Actions runners are IPv4-only).

```
pip install -r requirements.txt
python ingestion/load_cricsheet.py            # all seasons; --seasons N keeps the last N, --json-dir PATH uses local files
python checks/run_checks.py
python analysis/expected_runs_model.py
python analysis/runs_above_expected.py        # writes CSVs to analysis/output/ (gitignored)
streamlit run dashboard/app.py
```

## Model: expected runs per ball

Features: innings, over, wickets down, balls bowled so far. Trained on seasons 2008-2025, tested on 2026,
compared against two baselines.

| Model | RMSE | R2 |
|---|---|---|
| Constant (train mean) | 1.8754 | - |
| Average by innings and over | 1.8737 | -0.0146 |
| Gradient boosting | 1.8633 | -0.0033 |

**Result: the model does not beat a constant guess** (R2 is about zero). Runs off a single ball are
mostly noise and these four features explain almost none of it. The RMSE gap to the baselines is under 1%.
This is reported as is, not tuned. A useful model would need batter/bowler quality or match context.
`runs_above_expected.py` scores players against a model fitted on the same data (no holdout), so its
rankings are descriptive, not predictive.

## Data notes

- Match 419155 (2010) has 9 legal balls in one over in the source; it is whitelisted in `checks/run_checks.py`.
- Early seasons had 57-60 matches; the check threshold is 50 per season.

## Roadmap

- [x] Load all seasons from 2008 and re-run checks and model
- [x] Streamlit dashboard
- [ ] Publish dashboard and link it here
- [ ] Findings and screenshots section
- [ ] Confirm Cricsheet licence wording
- [ ] CricketData.org daily refresh (deferred until the next season starts)
