# Defense guide: Testing, AI, Database

Everything here is checked against the code. Where a common claim would be **false for this project** it says so; use the honest version.

## 0 · One-minute story
StudyMate reads a student's attendance and grades from the SDU portal and warns them early. A **RandomForest model trained on 1,044 real students** (public UCI *Student Performance* data) estimates the risk of falling below 60% and predicts GPA; **SHAP** explains every score; **SDU's own rules** (30% absence = FX, "Not submitted" hours) are applied exactly as rules. E-mail alerts go out through Resend above 50% risk.

## 1 · Testing

| Level | What | Tool | Count | Run |
|---|---|---|---|---|
| Unit (backend) | GPA, forecast, goals, parsers, risk maths, model features | pytest | in the 210 | `cd backend && python -m pytest -v` |
| Integration (backend) | every API endpoint through the real app and a real database | pytest + `fastapi.testclient.TestClient` | in the 210 | same |
| Coverage | | pytest-cov | **83 %** of `app/` | `python -m pytest --cov=app --cov-report=term-missing` |
| Unit (frontend) | GPA, schedule, goals, monitoring helpers | `node --test` | 24 | `cd frontend && npm run test:unit` |
| Component (frontend) | Monitoring tab, sync bar, GPA widget, forecast chart | Vitest + React Testing Library | 13 | `npm run test:component` |
| End-to-end | log in → Monitoring → sliders → Sync, in a real browser against the real backend | Playwright | 4 | `npx playwright install chromium` once, then `npm run test:e2e` |

`npm test` runs the unit and component tests together.

**Mocking (important).** No test touches the university. The SDU parser is tested against a **fake portal**: `sdu_portal.TRANSPORT` is swapped for an `httpx.MockTransport` that serves made-up HTML in the portal's real markup (`tests/test_portal.py`, `tests/test_pms_portal.py`). E-mails are captured by an autouse fixture (`tests/conftest.py`) so no real address is ever mailed, and the Resend client is replaced in tests with `monkeypatch`. (This project uses `httpx.MockTransport` and pytest's `monkeypatch`, not `unittest.mock`.) The E2E servers run with `ENABLE_PORTAL_LOGIN=0` and the portal address pointed at a dead local port.

Tests that show care for the risky parts: `test_sdu_password_is_found_nowhere_in_the_database` (security), `test_simulation_curve_never_improves_when_skipping_more` (the what-if can never say skipping helps), `test_reaching_the_absence_limit_is_always_high_risk` (FX rule), the whole suite also passes on PostgreSQL.

## 2 · AI

* **Training script**: `backend/app/ml/train.py` (`python -m app.ml.train --public`). Data mapping: `ml/public_data.py`. Features: `ml/features.py`. Synthetic generator (earlier version, still available): `ml/dataset.py`.
* **Model file**: `backend/models/risk_model.joblib`, loaded once into memory by `ml/model.py` for inference. Metrics: `backend/models/metrics.json`.
* **What it is**: `RandomForestClassifier` (at risk = final grade below 60%) and `RandomForestRegressor` (GPA), compared with a `LogisticRegression` baseline. On held-out real students: accuracy ≈ 0.97, F1 ≈ 0.97, ROC-AUC ≈ 0.99.
* **Features**: attendance %, worst-course absence %, missed hours, "Not submitted" hours, average grade, weakest grade, grade trend, missed deadlines, courses below 60%.
* **Explainable AI**: `shap.TreeExplainer` in `ml/model.py`. Each score comes with the top reasons that raise it and the factors that keep it low, with their effect in percentage points, plus a plain-language summary.
* **Live demo**: `uvicorn app.main:app --reload`, open `http://localhost:8000/docs`, *Authorize* with an `access_token`, run `POST /api/predict/risk`.

### Be honest about these (a strict examiner will find them)
1. **Do not say "1000 synthetic records".** The current model is trained on **real public data**, not on SDU data. It is a stand-in until SDU records are available (`--csv` retrains on them, 200+ students).
2. **Do not say "no hardcoded rules".** The 30% FX limit, the Safe-to-Skip limits and the alert wording are deliberate **rules**, because SDU's regulations are rules. The model handles the part that is genuinely statistical.
3. **The model mostly learned grades; absences come from a rule.** The simulator's response to skipped classes is an SDU-rule layer on top of the model (`attendance_pressure`, with "Not submitted" hours counting as half an absence), shown in the explanation as "Absence limit used". Say so.
   Earlier note, kept for context: **The model mostly learned grades.** In the public data, absences barely change the outcome and there is nothing like "Not submitted" hours or deadlines, so those two factors are constant (0) and the model ignores them. Their effect comes from the rule layer. (The earlier synthetic model did use them, but on made-up data.)
4. The public data is from Portuguese secondary schools; rows are mapped with documented assumptions (`ml/public_data.py` header).
5. High scores are partly expected: the early-period grades (G1, G2) predict the final grade well. G3 is never a feature.

## 3 · Database
See `docs/DATABASE.md` (ERD, the `pending` status, name mapping, security). In short: SQLite locally, PostgreSQL on Neon through `DATABASE_URL`; plain parameterized SQL (no ORM, say so); `attendance_log.status` stores `pending`; `risk_history` is the prediction history; SDU passwords are never stored and a test proves it.

## 4 · Demo script (10 minutes)
1. `cd backend && python -m pytest -q --cov=app` → 210 green, 83 %.
2. `cd frontend && npm test` → 24 + 13 green. Optionally `npm run test:e2e`.
3. Start backend, open `/docs`, *Authorize*, run `POST /api/predict/risk` and `POST /api/simulate` (`{"lectures":2,"practices":1}`).
4. Open the app → Monitoring: Safe-to-Skip bars, risk explanation, simulation chart, alerts, Sync.
5. Show `backend/app/ml/train.py`, `models/metrics.json`, the SHAP code in `ml/model.py`.
6. Show the database (Neon SQL editor or DB Browser): `attendance_log` with `pending`, `risk_history`, `sdu_connections` (opaque token, no password).

## 5 · Questions to expect
* *Why RandomForest?* Handles mixed scales and interactions with little tuning, works with `TreeExplainer` for exact, fast SHAP values; a logistic baseline scores about the same here, so the choice is justified by explainability, not by accuracy.
* *Isn't 97% suspiciously high?* Grades during the term strongly predict the final grade; that is the real signal and we never use the final grade as an input. It would be lower for "will they drop out" which we do not claim.
* *Is it SDU data?* No. Say so, and show the `--csv` path that retrains on SDU data.
* *What happens with no data?* `409` with a clear message until the first sync; the UI shows an invite to connect.
* *What if SHAP is unavailable?* An occlusion-based explanation takes over (`explainer` field says which).
* *How do you avoid hitting the real SDU in tests?* The mocking paragraph above.
