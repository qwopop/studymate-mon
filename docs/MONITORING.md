# Smart monitoring: setup guide

How the project meets the brief — *predictive analytics, performance trends, risk indicators, dashboards and alerts* — and how to switch on each free service. Nothing here changes existing behaviour: every feature is additive and the app still runs on SQLite with no keys.

| Brief requirement | Where it lives |
|---|---|
| Predictive analytics | `backend/app/ml/` (RandomForest risk + GPA models), `POST /api/predict/risk`, "Predicted GPA" widget on Overview |
| Performance trends | risk history (`risk_history` table), "Risk over time" chart, difficult-subjects forecast on Insights |
| Risk indicators | SHAP top-3 reasons, FX rule (absence ≥ 30%), `GET /api/teacher/monitoring/students` |
| Dashboards | **Monitoring** tab: Safe-to-Skip, AI risk, AI impact simulation, Alerts |
| Alerts | in-app alert feed + e-mail via Resend to the student and curator |

## Stage 1 · Data

### 1.1 Neon (free PostgreSQL)
The backend already switches to Postgres when `DATABASE_URL` is set (`backend/app/db.py`); no code change is needed.

1. Create a project on <https://neon.tech> and copy the connection string.
2. Set it where the backend runs (Render / Railway / your shell):
   `DATABASE_URL=postgresql://USER:PASSWORD@ep-xxxx.neon.tech/neondb?sslmode=require`
3. Start the backend once: it creates the schema, including the new monitoring tables.
4. Optional, to bring existing local data along:
   `DATABASE_URL=… python scripts/migrate_sqlite_to_postgres.py backend/data/student_monitoring.db`

The whole test-suite also passes on Postgres: `TEST_DATABASE_URL=postgresql://… python -m pytest` (this wipes that database, use a throw-away one).

### 1.2 SDU sync (scraper)
`backend/app/sdu_portal.py` signs in with the student's own number and password (plus the portal's e-mailed code), reads Attendance and Grades from `my.sdu.edu.kz`, and **never stores the password**: only the encrypted portal cookies are kept.

New: the attendance journal is now read hour by hour (`parse_journal_sessions`). A past hour the teacher has not marked ("Not submitted") is stored with its own status **`pending`**: it is not counted as an absence and not as attendance. Every class hour lands in the `attendance_log` table (`present`, `absent`, `permitted`, `pending`, `upcoming`) on each sync, and the model sees `pending_hours` as a separate feature.

## Stage 2 · Machine learning

* **Data**: `backend/app/ml/dataset.py` generates 1000 synthetic students from SDU rules (absence ≥ 30% → FX → at risk; every missed deadline lowers GPA; "Not submitted" hours add risk). Replace it with real history when you have it; the feature list is in `ml/features.py`.
* **Models**: `RandomForestClassifier` (`is_at_risk`) and `RandomForestRegressor` (predicted GPA on the SDU 4.0 scale), compared with a `LogisticRegression` baseline. Saved with `joblib` to `backend/models/risk_model.joblib`; metrics in `backend/models/metrics.json`. If the file is missing or from another scikit-learn version, the backend retrains in about a second on first use.
* **Retrain**: `cd backend && python -m app.ml.train [--rows 5000]`
* **Public real data (current model)**: `python -m app.ml.train --public` trains on the UCI *Student Performance* data set (Cortez & Silva, 2008, CC BY 4.0): 1044 real students with absences and grades G1, G2, G3. Not SDU data, so rows are mapped to our factors (`ml/public_data.py` lists every assumption): average/minimum/trend of G1 and G2, absences as a share of a 45-hour SDU term, "at risk" = final grade below 60%. Result on held-out students: accuracy 0.97, F1 0.97, ROC-AUC 0.99.
  * What this model learned: **grades dominate**. In this data absences barely change the outcome and there is nothing like "Not submitted" hours or deadlines, so those two factors are constant (0) and the model ignores them. Their effect comes from the SDU rules instead: the 30% FX guard, the Safe-to-Skip limits and the alerts.
  * `python -m app.ml.train` (no flag) goes back to the synthetic SDU-rules model, which does learn attendance, "Not submitted" and deadlines but from made-up data.
* **Retrain on real students**: put one row per past student in a CSV and run `python -m app.ml.train --csv students.csv` (`--template` prints the header). Columns: the nine features in `ml/features.py`, `is_at_risk` (0/1: failed a course with FX or needed support), and optionally `gpa` (final term GPA). It needs at least 200 rows with 20+ of each outcome; the metrics file records `data_source` so the DagsHub run shows whether a model was trained on real or synthetic data.
* **Explainable AI**: SHAP `TreeExplainer` returns the top-3 reasons, e.g. *"4 'Not submitted' hours that the teacher may still mark as absences, mostly in INF 451"*. If SHAP is unavailable, a simple occlusion explanation is used instead.
* **Predicted GPA** starts from your real current GPA (SDU scale, weighted by credits). The model then adds only the effect of risk factors (absences, "Not submitted" hours, missed deadlines, grade trend), so perfect attendance leaves it unchanged and it never invents a lower GPA than your grades give. Without grades it falls back to the model's own estimate (`gpa_basis` in the response says which).
* The SDU rule is also applied directly: when a course reaches the absence limit the risk is at least 90%, whatever the model says.

### Endpoints (student login required)
| Method | Path | What it does |
|---|---|---|
| POST | `/api/predict/risk` | risk %, level, predicted GPA, top-3 reasons |
| POST | `/api/simulate` | body `{"lectures": 2, "practices": 1, "course_code": "INF 451"}` → new GPA, new risk, FX courses, curve for the chart |
| GET | `/api/monitoring/overview` | everything the Monitoring tab needs in one call |
| GET | `/api/monitoring/alerts` | alert feed |
| GET | `/api/monitoring/forecast` | hardest subjects with forecast range |
| GET/PUT/DELETE | `/api/monitoring/curator` | curator e-mail for alerts |
| POST | `/api/monitoring/notify` | send the risk e-mail now |
| GET | `/api/teacher/monitoring/students` | teacher: risk ranking of the students in scope |

One skipped lecture or practice counts as one class hour; change with `LECTURE_HOURS` / `PRACTICE_HOURS` if your timetable differs. Hours allowed to miss in a course: `ceil(hours × 30%) − 1`.

## Stage 3 · Frontend
New **Monitoring** tab (`frontend/src/Monitoring.jsx`): Safe-to-Skip bars (green / yellow / red, striped part = "Not submitted" hours), AI risk with SHAP reasons, simulation sliders with a GPA/risk curve, alerts feed. Also: *Predicted GPA* widget on Overview, a *Sync with SDU* bar with "Last synced: 5 mins ago" on Attendance and Monitoring, and a forecast chart for difficult subjects on Insights.

## Stage 4 · E-mail alerts (Resend)
1. Create a key on <https://resend.com> (free: 3000 e-mails/month, 100/day).
2. Set `RESEND_API_KEY` and `RESEND_FROM` (the shared `onboarding@resend.dev` sender only delivers to your own Resend account address, so verify a domain for real students).
3. A background job (APScheduler, every `ALERT_INTERVAL_MINUTES`, default 360) and every SDU sync check the risk. At **≥ 50%** (`RISK_ALERT_THRESHOLD`) the student gets an e-mail, and so does the curator when one is saved. Nobody is mailed twice within 24 h unless the risk jumps by 15 points. Without `RESEND_API_KEY` nothing is sent and the scheduler stays off.

## Stage 5 · DagsHub (MLflow)
1. Create a repo on <https://dagshub.com> (connect this GitHub repo) → *Remote → Experiments* shows the MLflow URL.
2. `pip install -r backend/requirements-mlops.txt`
3. ```bash
   export MLFLOW_TRACKING_URI=https://dagshub.com/<user>/<repo>.mlflow
   export MLFLOW_TRACKING_USERNAME=<dagshub user>
   export MLFLOW_TRACKING_PASSWORD=<dagshub access token>
   cd backend && python -m app.ml.train
   ```
Each run logs parameters, accuracy / F1 / precision / recall / ROC-AUC / GPA error, and uploads `risk_model.joblib` and `metrics.json` as artifacts. Open the experiment page for the defense: one row per training run, comparable side by side.

## Tests
`cd backend && python -m pytest` (monitoring: `tests/test_monitoring.py`) · `cd frontend && npm test`.
