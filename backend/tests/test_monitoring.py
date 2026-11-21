"""Monitoring tab: pending ("Not submitted") status, risk model, SHAP reasons, simulation, alerts, e-mail."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import monitoring as mon
from app import monitoring_api, monitoring_store, notify, sdu_portal
from app.main import app, repo
from app.ml import dataset, model as ml
from app.ml.features import FEATURES

from test_portal import journal_section

client = TestClient(app)


def token(identifier="240103118", password="studymate2026"):
    return client.post("/api/auth/login", json={"identifier": identifier, "password": password}).json()["access_token"]


def auth(value): return {"Authorization": f"Bearer {value}"}


COURSES = [
    {"code": "INF 451", "name": "Databases", "hours": 30, "present": 12, "absent": 6, "permitted": 0, "pending": 4, "remaining": 8},
    {"code": "MAT 101", "name": "Math", "hours": 45, "present": 30, "absent": 2, "permitted": 1, "pending": 0, "remaining": 12},
]


# ─── Stage 1: "Not submitted" is its own status ────────────────────

def test_parser_keeps_not_submitted_hours_as_pending_not_absent():
    today = date(2026, 11, 9)
    rows = [(date(2026, 9, 3), None), (date(2026, 9, 10), "present"), (date(2026, 10, 8), "absent"),
            (date(2026, 11, 12), None)]
    out = sdu_portal.parse_journal_sessions(journal_section("pie01", rows, 4), today=today)
    assert out["pending"] == 1
    assert [s["status"] for s in out["sessions"]] == ["pending", "present", "absent", "upcoming"]


def test_attendance_log_roundtrip_stores_pending_and_replaces_on_resync():
    items = [{"course_code": "INF 451", "sessions": [{"date": "2026-09-03", "status": "pending"},
                                                     {"date": "2026-09-10", "status": "absent"}]}]
    assert monitoring_store.save_attendance_log(repo, "log-student", items) == 2
    items[0]["sessions"][0]["status"] = "present"          # the teacher submitted it
    monitoring_store.save_attendance_log(repo, "log-student", items)
    log = {r["session_date"]: r["status"] for r in monitoring_store.attendance_log(repo, "log-student")}
    assert log == {"2026-09-03": "present", "2026-09-10": "absent"}


# ─── Stage 2: data set + model ─────────────────────────────────────

def test_synthetic_dataset_follows_sdu_rules():
    X, y, gpa = dataset.generate(1000)
    assert X.shape == (1000, len(FEATURES)) and 0.2 < y.mean() < 0.8
    absence = X[:, FEATURES.index("max_absence_pct")]
    assert y[absence >= 30].all()                           # FX: attendance below 70% is always at risk
    assert 0 <= gpa.min() and gpa.max() <= 4


def test_model_is_accurate_and_explains_with_shap():
    bundle = ml.load()
    assert bundle["metrics"]["accuracy"] > 0.8 and bundle["metrics"]["f1"] > 0.75
    result = ml.predict({"max_absence_pct": 24, "pending_hours": 5, "missed_deadlines": 2, "avg_grade": 58, "min_grade": 40})
    assert result["explainer"] == "shap" and 1 <= len(result["reasons"]) <= 3
    assert result["risk"] > ml.predict({"avg_grade": 92, "min_grade": 85})["risk"]


def test_reaching_the_absence_limit_is_always_high_risk():
    f = mon.build_features([{**COURSES[0], "absent": 10}], [90], 1, 0)      # 10 of 30 hours = 33% -> FX
    assert mon.score(f)["fx"] and mon.score(f)["risk_percent"] >= 90


# ─── Safe-to-skip, alerts, simulation ──────────────────────────────

def test_safe_to_skip_counts_hours_before_fx_and_flags_pending():
    items = {c["code"]: c for c in mon.safe_to_skip(COURSES)["items"]}
    assert items["INF 451"]["limit"] == 8 and items["INF 451"]["remaining_skips"] == 2
    assert items["INF 451"]["remaining_if_pending_absent"] == -2 and items["INF 451"]["level"] == "danger"
    assert items["MAT 101"]["limit"] == 13 and items["MAT 101"]["level"] == "safe"


def test_alert_warns_about_not_submitted_hours():
    alerts = mon.build_alerts(COURSES, None)
    assert alerts[0]["type"] == "pending_over_limit"
    assert "4 'Not submitted' in INF 451" in alerts[0]["detail"] and "exceed the limit" in alerts[0]["detail"]


def test_simulation_skipping_more_lowers_gpa_and_raises_risk():
    sim = mon.simulate(COURSES, [75, 70], 0, 0, lectures=2, practices=1, course_code="MAT 101")
    assert sim["skipped_hours"] == 3 and sim["after"]["risk"] >= sim["before"]["risk"]
    assert sim["after"]["predicted_gpa"] <= sim["before"]["predicted_gpa"]
    assert sim["curve"][0]["hours"] == 0 and len(sim["curve"]) >= 11
    big = mon.simulate(COURSES, [75, 70], 0, 0, lectures=12, practices=0, course_code="MAT 101")
    assert "MAT 101" in big["fx_courses"] and "FX" in big["message"]


# ─── Endpoints ─────────────────────────────────────────────────────

@pytest.fixture()
def demo_student():
    session = client.post("/api/sdu/demo-connect", json={}).json()
    tok = session["access_token"]
    client.post("/api/sdu/sync", headers=auth(tok))
    return tok


def test_predict_risk_returns_risk_and_three_reasons(demo_student):
    res = client.post("/api/predict/risk", headers=auth(demo_student))
    assert res.status_code == 200
    body = res.json()
    assert 0 <= body["risk_percent"] <= 100 and len(body["reasons"]) <= 3 and body["model_version"]


def test_simulate_endpoint(demo_student):
    res = client.post("/api/simulate", json={"lectures": 2, "practices": 1}, headers=auth(demo_student))
    assert res.status_code == 200
    body = res.json()
    assert body["skipped_hours"] == 3 and "New predicted GPA" in body["message"] and body["curve"]
    assert client.post("/api/simulate", json={"lectures": 1, "course_code": "NOPE"}, headers=auth(demo_student)).status_code == 404
    assert client.post("/api/simulate", json={"lectures": -1}, headers=auth(demo_student)).status_code == 422


def test_overview_has_every_block(demo_student):
    body = client.get("/api/monitoring/overview", headers=auth(demo_student)).json()
    assert body["has_data"] and body["safe_to_skip"]["items"] and body["risk"]["predicted_gpa"] is not None
    assert "alerts" in body and body["last_synced"]


def test_monitoring_is_student_only_and_needs_login():
    assert client.post("/api/predict/risk").status_code == 401
    teacher = token("teacher@univ.edu", "teacher123")
    assert client.post("/api/simulate", json={"lectures": 1}, headers=auth(teacher)).status_code == 403


def test_teacher_sees_risk_per_student_in_scope():
    body = client.get("/api/teacher/monitoring/students", headers=auth(token("teacher@univ.edu", "teacher123"))).json()
    assert body["items"] == sorted(body["items"], key=lambda r: -r["risk_percent"])


# ─── Stage 4: e-mail alerts ────────────────────────────────────────

def test_curator_email_roundtrip():
    tok = token()
    assert client.put("/api/monitoring/curator", json={"email": "curator@sdu.edu.kz", "name": "Dr. Aidos"}, headers=auth(tok)).status_code == 200
    assert client.get("/api/monitoring/curator", headers=auth(tok)).json()["email"] == "curator@sdu.edu.kz"
    assert client.put("/api/monitoring/curator", json={"email": "nope"}, headers=auth(tok)).status_code == 422
    client.delete("/api/monitoring/curator", headers=auth(tok))
    assert client.get("/api/monitoring/curator", headers=auth(tok)).json()["email"] is None


def test_high_risk_sends_email_to_student_and_curator_once(monkeypatch, no_real_email):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    sent = []
    monkeypatch.setattr(notify, "send_resend", lambda to, subject, text, html=None: (sent.append((to, subject)) or (True, "ok")))
    tok = client.post("/api/sdu/demo-connect", json={}).json()["access_token"]
    me = client.get("/api/me", headers=auth(tok)).json()
    bad = [{**COURSES[0], "absent": 11, "pending": 3}]
    monkeypatch.setattr(monitoring_api, "student_inputs", lambda uid, sid: {
        "courses": bad, "scores": [48], "trend": -4, "missed": 3, "has_data": True, "source": "test",
        "features": mon.build_features(bad, [48], -4, 3)})
    monitoring_store.set_curator(repo, me["student_id"], "curator@sdu.edu.kz")
    first = monitoring_api.send_risk_alert(me["id"], me["student_id"], me["name"])
    again = monitoring_api.send_risk_alert(me["id"], me["student_id"], me["name"])
    assert first["sent"] and "curator@sdu.edu.kz" in first["to"] and len(first["to"]) == 2
    assert not again["sent"] and again["reason"] == "already alerted recently"      # no spam inside the cool-down
    assert [s[0] for s in sent].count("curator@sdu.edu.kz") == 1


def test_low_risk_sends_nothing(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    sent = []
    monkeypatch.setattr(notify, "send_resend", lambda *a, **k: (sent.append(a) or (True, "ok")))
    good = [{**COURSES[1], "absent": 0, "pending": 0}]
    monkeypatch.setattr(monitoring_api, "student_inputs", lambda uid, sid: {
        "courses": good, "scores": [92], "trend": 2, "missed": 0, "has_data": True, "source": "test",
        "features": mon.build_features(good, [92], 2, 0)})
    out = monitoring_api.send_risk_alert("u-student", "s1", "Student")
    assert not out["sent"] and not sent


def test_resend_without_key_does_not_touch_the_network(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert notify.send_resend("a@b.kz", "s", "t") == (False, "RESEND_API_KEY is not set")


def test_forecast_endpoint_lists_hardest_subjects_first(demo_student):
    body = client.get("/api/monitoring/forecast", headers=auth(demo_student)).json()
    scores = [i["current_score"] for i in body["items"]]
    assert scores == sorted(scores) and len(scores) <= 5


def test_predicted_gpa_starts_from_the_real_gpa_and_only_adds_risk_effects():
    clean = mon.build_features([COURSES[1]], [90, 85], 0, 0, current_gpa=3.5)
    out = mon.score(clean)
    assert out["gpa_basis"] == "current" and abs(out["predicted_gpa"] - 3.5) < 0.15      # perfect record: stays at the real GPA
    risky = mon.build_features([{**COURSES[1], "absent": 10, "pending": 3}], [90, 85], 0, 2, current_gpa=3.5)
    assert mon.score(risky)["predicted_gpa"] < out["predicted_gpa"]                       # risks pull it down
    assert mon.score(mon.build_features([COURSES[1]], [90, 85], 0, 0))["gpa_basis"] == "model"


def test_simulation_curve_never_improves_when_skipping_more():
    for gpa in (None, 3.4):
        sim = mon.simulate([{**COURSES[1], "absent": 0}], [92, 88], 1, 0, lectures=3, practices=1, course_code="MAT 101", current_gpa=gpa)
        risks = [p["risk"] for p in sim["curve"]]
        gpas = [p["predicted_gpa"] for p in sim["curve"]]
        assert risks == sorted(risks) and gpas == sorted(gpas, reverse=True)
        assert sim["curve"][0]["risk"] == sim["before"]["risk"]
        assert sim["risk_change"] >= 0 and sim["gpa_change"] <= 0


def test_risk_is_explained_in_words_for_low_and_high_risk():
    low = mon.score(mon.build_features([COURSES[1]], [92, 88], 1, 0, current_gpa=3.5))
    assert low["summary"] and low["helping"] and "no factor is pushing it up" in low["summary"] or low["reasons"]
    assert all(h["impact"] < 0 for h in low["helping"])
    high = mon.add_course_detail(mon.score(mon.build_features(COURSES, [72, 65], -2, 1)), COURSES)
    assert high["summary"].startswith(f"Your risk is {high['risk_percent']}%") and "mainly because" in high["summary"]
    assert "INF 451" in high["summary"] or len(high["reasons"]) > 0
