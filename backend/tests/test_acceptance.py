"""Customer acceptance (QA) tests: one Given / When / Then scenario per user story, run through the real HTTP API.

Each test name starts with the story id (US-05 ... US-27, T-1 ... T-3) and its docstring is the scenario, so the
`pytest -v` output reads as the acceptance report. The data is the built-in demo student (no SDU account needed)."""
import pytest
from fastapi.testclient import TestClient

from app import monitoring_api, monitoring_store, notify
from app import monitoring as mon
from app.main import app, repo

client = TestClient(app)


def auth(token): return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def student():
    """Given a student who connected the demo SDU account and synced."""
    session = client.post("/api/sdu/demo-connect", json={}).json()
    token = session["access_token"]
    assert client.post("/api/sdu/sync", headers=auth(token)).json()["synced"] is True
    return {"token": token, "user": session["user"]}


@pytest.fixture(scope="module")
def weak_student():
    """Given a student whose courses include one failing course (45 %) and one good course (88 %) this term."""
    import json
    user = repo.create_user(name="Weak Subject Student", identifier="acc-weak@univ.edu", password="acceptance-1", role="student")
    with repo.connect() as db:
        for course, code, score in (("Operating Systems", "CSS 301", 45), ("Databases", "INF 210", 88)):
            db.execute("INSERT INTO grades (student_id, semester, course, code, credits, components_json) VALUES (?, 'spring-2026', ?, ?, 6, ?)",
                       (user["student_id"], course, code, json.dumps([{"name": "Final Grade", "score": score, "weight": 1.0}])))
        db.commit()
    token = client.post("/api/auth/login", json={"identifier": "acc-weak@univ.edu", "password": "acceptance-1"}).json()["access_token"]
    return {"token": token, "user": user}


@pytest.fixture(scope="module")
def teacher():
    """Given a teacher with an assigned group of students."""
    return client.post("/api/auth/login", json={"identifier": "teacher@univ.edu", "password": "teacher123"}).json()["access_token"]


# ─── Access and synchronisation ─────────────────────────────────────

def test_US22_student_signs_in_and_syncs_sdu_data(student):
    """Given a student with an SDU account
    When they connect it and press Sync
    Then the account is connected as a student and the last-sync time is stored."""
    status = client.get("/api/sdu/status", headers=auth(student["token"])).json()
    assert status["connected"] is True
    assert client.get("/api/me", headers=auth(student["token"])).json()["role"] == "student"
    assert client.get("/api/monitoring/overview", headers=auth(student["token"])).json()["last_synced"]


def test_US22_requests_without_a_login_are_refused_and_roles_are_kept_apart(student):
    """Given nobody is signed in / a student is signed in
    When they ask for protected data / the teacher area
    Then the answer is 401 / 403."""
    assert client.get("/api/student/dashboard").status_code == 401
    assert client.get("/api/teacher/students", headers=auth(student["token"])).status_code == 403


# ─── Existing academic stories ──────────────────────────────────────

def test_US05_student_gets_alerts_and_can_mark_them_read(student):
    """Given a sync produced alerts (missed deadline, grade or absence limits)
    When the student opens the alerts
    Then each alert is listed with its type, and marking one as read lowers the unread count."""
    data = client.get("/api/student/notifications", headers=auth(student["token"])).json()
    assert data["items"] and data["unread_count"] >= 1 and all(n["type"] for n in data["items"])
    first = next(n for n in data["items"] if not n["read"])
    assert client.post(f"/api/student/notifications/{first['id']}/read", headers=auth(student["token"])).status_code == 200
    assert client.get("/api/student/notifications", headers=auth(student["token"])).json()["unread_count"] == data["unread_count"] - 1


def test_US06_US14_courses_are_ranked_weakest_first_and_weak_ones_flagged(student):
    """Given graded courses this term
    When the student opens Insights
    Then courses are ranked from weakest to strongest, with the term average, and every weak course is below the threshold."""
    ins = client.get("/api/student/insights", headers=auth(student["token"])).json()
    scores = [c["score"] for c in ins["ranked"]]
    assert scores == sorted(scores) and ins["average"] is not None
    assert all(w["score"] < ins["threshold"] for w in ins["weak_subjects"])


def test_US15_strengths_are_the_courses_above_the_strength_threshold(student):
    """Given graded courses
    When the student opens Insights
    Then the strengths are exactly the best courses at or above the strength threshold."""
    ins = client.get("/api/student/insights", headers=auth(student["token"])).json()
    assert ins["strengths"] and all(s["score"] >= ins["strength_threshold"] for s in ins["strengths"])


def test_US06_the_failing_course_is_flagged_as_weak(weak_student):
    """Given a student with a 45 % course among their courses
    When they open Insights
    Then only that course is flagged weak, it is ranked first, and the (at most two) strengths are above the strength threshold."""
    ins = client.get("/api/student/insights", headers=auth(weak_student["token"])).json()
    assert [w["course"] for w in ins["weak_subjects"]] == ["Operating Systems"]
    assert ins["ranked"][0]["course"] == "Operating Systems"
    assert 0 < len(ins["strengths"]) <= 2 and all(s["score"] >= ins["strength_threshold"] for s in ins["strengths"])


def test_US07_study_plan_has_concrete_tasks_that_can_be_ticked_off(weak_student):
    """Given the failing course produced study tasks
    When the student ticks one
    Then it is saved as done and the completion rate rises."""
    plan = client.get("/api/student/insights", headers=auth(weak_student["token"])).json()["study_plan"]
    assert plan["tasks"] and plan["done"] == 0
    task = plan["tasks"][0]
    assert client.post(f"/api/student/study-tasks/{task['id']}", json={"done": True}, headers=auth(weak_student["token"])).status_code == 200
    after = client.get("/api/student/insights", headers=auth(weak_student["token"])).json()["study_plan"]
    assert after["done"] == 1 and after["completion_rate"] > plan["completion_rate"]


def test_US16_study_resources_are_offered_for_a_weak_course():
    """Given a course below the pass threshold
    When resources are requested for it
    Then links for that course are returned."""
    from app import academics
    resources = academics.study_resources("Operating Systems")
    assert resources and all(r["url"].startswith("http") for r in resources)


def test_US09_attendance_of_the_previous_semester_can_be_opened(student):
    """Given the student has earlier semesters
    When they ask for attendance one term back
    Then the earlier term's courses are returned."""
    data = client.get("/api/sdu/attendance?terms_back=1", headers=auth(student["token"])).json()
    assert data["attendance"] and all("lesson" in a for a in data["attendance"])


def test_US10_grade_breakdown_shows_each_assessment_of_a_course(student):
    """Given a course with a syllabus breakdown
    When the student opens its grade breakdown
    Then the weighted parts and the weighted score are shown."""
    course = client.get("/api/student/grades", headers=auth(student["token"])).json()["items"][0]["course"]
    body = client.get("/api/student/grades/breakdown", params={"course": course}, headers=auth(student["token"])).json()
    assert body["components"] and "weighted_score" in body


def test_US12_US13_upcoming_and_overdue_deadlines_are_listed(student):
    """Given Moodle deadlines for the student
    When they open the deadlines
    Then upcoming and overdue assignments are listed separately."""
    data = client.get("/api/sdu/deadlines?days=7", headers=auth(student["token"])).json()
    assert data["available"] and isinstance(data["upcoming"], list) and isinstance(data["overdue"], list)


def test_US17_final_grade_forecast_is_given_per_course_with_a_status(student):
    """Given the current term's courses
    When the student opens the forecast
    Then every course has a forecast status (predicted, final, not enough data or no breakdown)."""
    items = client.get("/api/student/forecast", headers=auth(student["token"])).json()["items"]
    assert items and all(i["forecast"]["status"] in ("predicted", "final", "insufficient_data", "no_breakdown") for i in items)


def test_US18_US19_goals_are_saved_and_checked_for_feasibility(student):
    """Given the student sets a GPA and an attendance target
    When the goals are saved and opened
    Then the goal is stored and its feasibility status is tracked."""
    saved = client.put("/api/student/goals", json={"target_attendance": 80}, headers=auth(student["token"]))
    assert saved.status_code == 200
    data = client.get("/api/student/goals", headers=auth(student["token"])).json()
    assert data["goal"]["target_attendance"] == 80 and data["tracking"] is not None


@pytest.mark.parametrize("period", ["week", "month"])
def test_US20_US21_weekly_and_monthly_progress_summaries(student, period):
    """Given synced data
    When the student opens the weekly or monthly summary
    Then the period, attendance, GPA and new marks are reported."""
    data = client.get("/api/student/summary", params={"period": period}, headers=auth(student["token"])).json()
    assert data["period"] == period and {"attendance", "gpa", "new_marks"} <= set(data)


# ─── Predictive analytics, risk indicators, dashboards and alerts ───

def test_US23_ai_risk_is_scored_and_explained(student):
    """Given synced attendance and grades
    When the student asks for their risk
    Then a risk 0-100 %, a predicted GPA and up to three reasons with SHAP impacts are returned."""
    body = client.post("/api/predict/risk", headers=auth(student["token"])).json()
    assert 0 <= body["risk_percent"] <= 100 and 0 <= body["predicted_gpa"] <= 4
    assert len(body["reasons"]) <= 3 and body["summary"] and body["explainer"] in ("shap", "occlusion")


def test_US24_safe_to_skip_shows_how_many_classes_can_still_be_missed(student):
    """Given class-hour counts per course
    When the student opens Monitoring
    Then each course shows its absence limit, hours missed and the hours left, with a green, yellow or red level."""
    items = client.get("/api/monitoring/overview", headers=auth(student["token"])).json()["safe_to_skip"]["items"]
    assert items and all({"limit", "absent", "remaining_skips", "level", "cost_per_hour_pct"} <= set(c) for c in items)
    assert all(c["level"] in ("safe", "warning", "danger") for c in items)


def test_US25_skipping_more_classes_never_improves_the_outcome(student):
    """Given the student chooses a course and moves the sliders
    When more lectures and practices are skipped
    Then the predicted risk only rises, the predicted GPA only falls, and reaching the limit is marked as FX."""
    body = client.post("/api/simulate", json={"lectures": 0, "practices": 0, "max_hours": 60}, headers=auth(student["token"])).json()
    risks = [p["risk"] for p in body["curve"]]
    gpas = [p["predicted_gpa"] for p in body["curve"]]
    assert risks == sorted(risks) and gpas == sorted(gpas, reverse=True)
    assert any(p["fx"] for p in body["curve"]) and body["course_cost"]["cost_per_hour_pct"] >= 1


def test_US25_a_missed_hour_costs_more_in_a_course_with_fewer_weekly_lessons():
    """Given one course with 1 lesson a week and another with 3 lessons a week
    When one hour is skipped in each
    Then the 1-lesson course loses a much larger share of its allowed absences and shows the higher risk."""
    def course(hours): return [{"code": "X", "name": "X", "hours": hours, "present": hours // 3, "absent": 0, "permitted": 0, "pending": 0, "remaining": hours * 2 // 3}]
    one, three = (mon.simulate(course(h), [75], 0, 0, 1, 0, "X", current_gpa=2.67, max_hours=10) for h in (15, 45))
    assert one["course_cost"]["cost_per_hour_pct"] > three["course_cost"]["cost_per_hour_pct"] and one["risk_change"] > three["risk_change"]


def test_US26_alert_feed_lists_warnings_most_severe_first(student):
    """Given absences, grades and deadlines
    When the student opens the alert feed
    Then warnings are listed with a severity, the most severe first."""
    items = client.get("/api/monitoring/alerts", headers=auth(student["token"])).json()["items"]
    order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    assert items and [order[a["severity"]] for a in items] == sorted(order[a["severity"]] for a in items)


def test_US27_high_risk_sends_one_e_mail_to_the_student_and_one_to_the_curator(student, monkeypatch):
    """Given the student saved a curator e-mail and the risk reaches 50 %
    When the alert check runs twice in a row
    Then the student and the curator each get one e-mail, and the second run sends nothing (cool-down)."""
    sent = []
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setattr(notify, "send_resend", lambda to, subject, text, html=None: (sent.append(to) or (True, "ok")))
    user = student["user"]
    bad = [{"code": "X", "name": "X", "hours": 30, "present": 10, "absent": 8, "permitted": 0, "pending": 4, "remaining": 8}]
    monkeypatch.setattr(monitoring_api, "student_inputs", lambda uid, sid: {
        "courses": bad, "scores": [48], "trend": -4, "missed": 3, "has_data": True, "source": "test",
        "features": mon.build_features(bad, [48], -4, 3, 1.0)})
    assert client.put("/api/monitoring/curator", json={"email": "curator@sdu.edu.kz"}, headers=auth(student["token"])).status_code == 200
    with repo.connect() as db:                                                      # make sure the student has an address on file
        db.execute("INSERT OR IGNORE INTO login_identifiers (identifier, user_id) VALUES (?, ?)", ("student.demo@sdu.edu.kz", user["id"]))
        db.commit()
    try:
        first = monitoring_api.send_risk_alert(user["id"], user["student_id"], user["name"])
        second = monitoring_api.send_risk_alert(user["id"], user["student_id"], user["name"])
        assert first["sent"] and "curator@sdu.edu.kz" in sent and len(sent) == 2
        assert second["sent"] is False and len(sent) == 2
    finally:                                                                       # leave the shared demo student as we found it
        monitoring_store.delete_curator(repo, user["student_id"])
        with repo.connect() as db:
            db.execute("DELETE FROM risk_alert_log WHERE student_id = ?", (user["student_id"],))
            db.execute("DELETE FROM login_identifiers WHERE identifier = ?", ("student.demo@sdu.edu.kz",))
            db.commit()


# ─── Teacher stories ────────────────────────────────────────────────

def test_T1_teacher_sees_only_their_students_with_risk_factors(teacher):
    """Given a teacher with an assigned group
    When they open the student list or ask for a student outside the group
    Then they see their students with risk factors, and the outsider is not found."""
    items = client.get("/api/teacher/students", headers=auth(teacher)).json()["items"]
    assert items and all("risk_factors" in s for s in items)
    assert client.get("/api/teacher/students/not-in-my-group", headers=auth(teacher)).status_code == 404


def test_T2_teacher_records_an_intervention_and_it_appears_in_the_history(teacher):
    """Given a student in the teacher's group
    When the teacher records an intervention
    Then it is stored with the action and notes and listed in the student's history."""
    sid = client.get("/api/teacher/students", headers=auth(teacher)).json()["items"][0]["id"]
    made = client.post(f"/api/teacher/students/{sid}/interventions", json={"action_type": "meeting", "notes": "Discuss attendance plan"}, headers=auth(teacher))
    assert made.status_code in (200, 201)
    history = client.get(f"/api/teacher/students/{sid}/interventions", headers=auth(teacher)).json()
    assert any(i["notes"] == "Discuss attendance plan" for i in (history["items"] if isinstance(history, dict) else history))


def test_T3_teacher_sees_how_attendance_relates_to_performance(teacher):
    """Given the group's attendance and grades
    When the teacher opens the analytics
    Then points per student and a correlation (with a note that it is not causation) are returned."""
    data = client.get("/api/teacher/analytics/attendance-performance", headers=auth(teacher)).json()
    assert data["points"] and "causation" in data["note"]
