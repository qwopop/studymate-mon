"""Builds the project documentation (Word + PDF) from the repository itself.

    python collect_evidence.py     # run every test suite, store the real numbers
    python make_diagrams.py        # figures
    python build_docs.py           # writes "Project#4 documentation - practice group#X.docx" and .pdf

Code excerpts are cut from the real source files, test results come from evidence.json, so nothing is retyped.
"""
import ast, inspect, json, re, subprocess, sys, textwrap
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import os
os.environ.setdefault("STUDYMATE_SKIP_DOTENV", "1")
from app import academics, deadlines, goals, main as app_main, monitoring, monitoring_api, repository, sdu_portal, summaries  # noqa: E402
from app.ml import model as ml_model  # noqa: E402

EV = json.loads((HERE / "evidence.json").read_text())
BE, FE = EV["backend"], EV["frontend"]
FONT = "Times New Roman"
IMG = HERE / "img"
OUT = HERE / "Project#4 documentation - practice group#X"

doc = Document()


# ───────────────────────── formatting helpers ─────────────────────────
def set_font(style_or_run, size=None, bold=None, italic=None, name=FONT, color=None):
    f = style_or_run.font
    f.name = name
    el = style_or_run.element if hasattr(style_or_run, "element") else style_or_run._element
    rpr = el.get_or_add_rPr() if hasattr(el, "get_or_add_rPr") else el.rPr
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts"); rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)
    if size: f.size = Pt(size)
    if bold is not None: f.bold = bold
    if italic is not None: f.italic = italic
    if color is not None: f.color.rgb = RGBColor(*color)


sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Cm(2.5), Cm(2.0), Cm(2.0), Cm(2.0)
for name, size, bold in (("Normal", 12, False), ("Heading 1", 14, True), ("Heading 2", 12, True), ("Heading 3", 12, True)):
    st = doc.styles[name]
    set_font(st, size, bold, color=(0, 0, 0))
    st.paragraph_format.line_spacing = 1.0
    st.paragraph_format.space_after = Pt(6)
    if name != "Normal":
        st.paragraph_format.space_before = Pt(10); st.paragraph_format.keep_with_next = True
doc.styles["Heading 3"].font.italic = True


def run(p, text, bold=None, italic=None, size=None, mono=False, highlight=False):
    r = p.add_run(text)
    set_font(r, size, bold, italic, name="Courier New" if mono else FONT)
    if highlight: r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return r


def para(text="", bold=None, italic=None, size=None, align=None, after=None, keep=False):
    p = doc.add_paragraph()
    add_rich(p, text, bold, italic, size)
    if align == "center": p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if after is not None: p.paragraph_format.space_after = Pt(after)
    if keep: p.paragraph_format.keep_with_next = True
    return p


def add_rich(p, text, bold=None, italic=None, size=None):
    """**bold**, `code` and [[placeholder]] markers inside a string."""
    for part in re.split(r"(\*\*.+?\*\*|`.+?`|\[\[.+?\]\])", text):
        if not part: continue
        if part.startswith("**"): run(p, part[2:-2], True, italic, size)
        elif part.startswith("`"): run(p, part[1:-1], bold, italic, (size or 12) - 1, mono=True)
        elif part.startswith("[["): run(p, "[" + part[2:-2] + "]", bold, italic, size, highlight=True)
        else: run(p, part, bold, italic, size)


def bullets(items, size=None):
    for t in items:
        p = doc.add_paragraph(style="List Bullet")
        add_rich(p, t, size=size); p.paragraph_format.space_after = Pt(2)
        for r in p.runs: set_font(r, r.font.size and r.font.size.pt or size or 12, r.font.bold, r.font.italic, name=r.font.name or FONT)


def h1(text):
    p = doc.add_heading(text, 1); p.paragraph_format.page_break_before = True
    for r in p.runs: set_font(r, 14, True, color=(0, 0, 0))
    return p


def h2(text):
    p = doc.add_heading(text, 2)
    for r in p.runs: set_font(r, 12, True, color=(0, 0, 0))


def h3(text):
    p = doc.add_heading(text, 3)
    for r in p.runs: set_font(r, 12, True, True, color=(0, 0, 0))


def shade(cell, fill):
    tcpr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill); tcpr.append(shd)


def repeat_header(row):
    trpr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader"); el.set(qn("w:val"), "true"); trpr.append(el)


def no_split(row):
    trpr = row._tr.get_or_add_trPr(); el = OxmlElement("w:cantSplit"); el.set(qn("w:val"), "true"); trpr.append(el)


def fill_cell(cell, content, size=11, bold=None):
    cell.text = ""
    items = content if isinstance(content, list) else [content]
    first = True
    for it in items:
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        p.paragraph_format.space_after = Pt(1); p.paragraph_format.line_spacing = 1.0
        add_rich(p, str(it), bold=bold, size=size)


def table(header, rows, widths, size=11, header_fill="D9D9D9", split=False):
    t = doc.add_table(rows=1, cols=len(header)); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, h in enumerate(header):
        fill_cell(t.rows[0].cells[i], h, size, bold=True); shade(t.rows[0].cells[i], header_fill)
    repeat_header(t.rows[0])
    for r in rows:
        row = t.add_row()
        if not split: no_split(row)
        if isinstance(r, tuple) and len(r) == 2 and r[0] == "__band__":
            m = row.cells[0].merge(row.cells[-1]); fill_cell(m, r[1], size, bold=True); shade(m, "EDEDED"); continue
        for i, c in enumerate(r): fill_cell(row.cells[i], c, size)
    layout = OxmlElement("w:tblLayout"); layout.set(qn("w:type"), "fixed"); t._tbl.tblPr.append(layout)   # honour the column widths
    for i, w in enumerate(widths): t.columns[i].width = Cm(w)
    for row in t.rows:
        for i, w in enumerate(widths):
            if i < len(row.cells): row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def figure(path, width_cm, caption):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    c = para(caption, italic=True, size=10, align="center", after=8)


def code(text, size=8):
    for chunk in [text]:
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(6); p.paragraph_format.line_spacing = 1.0
        ppr = p._p.get_or_add_pPr(); shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "F3F3F3"); ppr.append(shd)
        lines = chunk.rstrip("\n").split("\n")
        for i, line in enumerate(lines):
            r = p.add_run(line.replace("\t", "    ")); set_font(r, size, name="Courier New")
            if i < len(lines) - 1: r.add_break()


def add_page_number_footer():
    p = sec.footer.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(p, "Project #4: Smart Student Performance Monitoring System        Page ", size=10)
    r = p.add_run(); set_font(r, 10)
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), tag); r._r.append(fc)
        else:
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = text; r._r.append(it)


def source(obj, max_lines=None, strip_doc=False):
    s = textwrap.dedent(inspect.getsource(obj))
    lines = s.rstrip("\n").split("\n")
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines] + ["    ..."]
    return "\n".join(lines)


def file_slice(rel, start_pat, end_pat):
    text = (ROOT / rel).read_text()
    a = text.index(start_pat); b = text.index(end_pat, a)
    return text[a:b].rstrip() + "\n"


# ───────────────────────── content: user stories ─────────────────────────
# id, actor, "I want ...", brief definition, problem, functional requirement, api/ui, usability: (goal, inputs, assumptions, steps, success)
S = "Student"
STORIES = [
 ("US-22", S, "sign in with my SDU account and keep my attendance and grades up to date",
  "Sign in with the SDU portal account and synchronise data.", "Data lives only in the SDU portal; no tool can analyse it without a safe way to read it.",
  "Sign in with student number, password and the e-mailed code; read attendance, grades, schedule and transcript; keep only encrypted session cookies, never the password; Sync button shows the last sync time. `POST /api/sdu/portal/login`, `/verify`, `POST /api/sdu/sync`, `GET /api/sdu/status`.",
  ("Connect SDU and sync", "Student number, password, e-mailed code", "SDU portal reachable (demo data used otherwise)", ["Open the site", "Enter student number and password", "Enter the e-mailed code", "Press Sync with SDU"], "Dashboard shows own courses and 'Last synced: just now'")),
 ("US-05", S, "get alerts when a grade, my absences or a deadline need attention",
  "Alerts for low grades, absence near or over the FX limit, low overall attendance and missed deadlines.", "SDU shows numbers but never warns, so students notice problems too late.",
  "After each sync create a notification only for real changes: grade below 60 %, a course crossing 25 % or 30 % absence, overall attendance below 70 %, a missed deadline; list with unread count; mark as read. `GET /api/student/notifications`, `POST /api/student/notifications/{id}/read`.",
  ("Read and clear alerts", "Synced account with an alert", "At least one alert exists", ["Open the bell or Alerts page", "Read the newest alert", "Open it / mark it as read"], "Unread count goes down by one")),
 ("US-06", S, "see which of my subjects are weakest",
  "Weak-subject detection: courses ranked from weakest to strongest.", "It is hard to see which course is in trouble among many.",
  "Rank the current courses by score; flag every course below 60 % as weak; show the weakest topic when a breakdown exists. `GET /api/student/insights`.",
  ("Find the weakest subject", "Synced account", "At least one graded course", ["Open Insights", "Read the ranking"], "Student names the weakest course correctly")),
 ("US-14", S, "compare my subjects with my term average",
  "Subject comparison chart with the term average.", "Single grades say little without a reference point.",
  "Show every graded course as a bar with the term average line. `GET /api/student/insights` (field `average`).",
  ("Compare subjects", "Synced account", "At least two graded courses", ["Open Insights", "Read the Subject comparison chart"], "Student tells which courses are above and below the average")),
 ("US-15", S, "see my strongest subjects",
  "Strengths: the best courses above 85 %.", "Students focus on problems and miss what they do well.",
  "List up to two top subjects at or above the strength threshold, strongest first, never padded. `GET /api/student/insights` (field `strengths`).",
  ("See strengths", "Synced account", "A course at or above 85 %", ["Open Insights", "Read Academic strengths"], "Strengths shown match the best grades")),
 ("US-16", S, "get study resources for a weak subject",
  "Lecture videos, a practice set and a library search for a weak course.", "Students do not know where to start when a course goes badly.",
  "For each weak course return links to lecture videos, practice material and a library search. Implemented in `academics.study_resources`, shown in the study plan.",
  ("Open resources for a weak course", "Account with a weak course", "A course below 60 %", ["Open Insights", "Find the weak course", "Open a resource link"], "A relevant resource opens")),
 ("US-07", S, "get a concrete study plan for each weak subject",
  "Three actions per weak course, built from real course data, that can be ticked off.", "Advice like 'study more' is not actionable.",
  "Generate three concrete tasks per weak course (review the weakest topic, redo practice, ask the instructor); allow ticking tasks; show completion rate. `GET /api/student/insights`, `POST /api/student/study-tasks/{id}`.",
  ("Follow the study plan", "Account with a weak course", "A study plan exists", ["Open Insights", "Read the three tasks", "Tick one task"], "Task is saved as done and completion rises")),
 ("US-10", S, "see how each assessment counts and what score I need to reach a target grade",
  "Grade breakdown per course and the What-if planner.", "SDU shows only a total, so students cannot plan the final exam.",
  "Show every assessment with its weight and score; the What-if planner computes the score needed on one component for a target final grade and says whether it is reachable. `GET /api/student/grades/breakdown`, `POST /api/student/grades/whatif`.",
  ("Find the score needed in the final exam", "Course, target 85", "Weights add up to 100 %", ["Open What-if planner", "Choose the course", "Enter weights and scores", "Enter the target", "Press Calculate"], "Needed score shown with a verdict")),
 ("US-17", S, "see a forecast of my final grade",
  "Final-grade forecast with a 95 % range.", "Students only know the grade so far, not where they are heading.",
  "Once 70 % of the coursework is graded, project the final percent with a 95 % interval; otherwise say why there is no forecast. `GET /api/student/forecast`.",
  ("Read the forecast", "Course with a breakdown", "At least 70 % of the course graded", ["Open Grades", "Find Final grade forecast"], "Predicted grade and range shown, or a clear reason")),
 ("US-12", S, "see my upcoming deadlines",
  "Upcoming and overdue deadlines from the Moodle calendar.", "Deadlines are spread over several course pages.",
  "Connect the Moodle calendar export; list assignments due in the next days and overdue ones. `POST /api/sdu/moodle/connect`, `GET /api/sdu/deadlines`.",
  ("See deadlines this week", "Moodle calendar link", "Moodle connected", ["Open Overview", "Read Deadlines this week"], "All deadlines of the week listed with dates")),
 ("US-13", S, "be warned when I missed a deadline",
  "Urgent alert for each past-due, not submitted assignment.", "A missed submission is noticed only after the grade drops.",
  "On sync, create one urgent alert per assignment that is past due and explicitly not submitted, once only.",
  ("Notice a missed deadline", "Overdue assignment", "Moodle connected", ["Sync", "Open alerts"], "Alert 'Missed deadline' appears once")),
 ("US-18", S, "set goals and see whether they are still reachable",
  "GPA, attendance and course targets with a feasibility check.", "Goals without a reality check cause stress or false hope.",
  "Save targets; for each, compute the maximum still achievable and the score required; mark it on track, behind or unachievable. `GET/PUT /api/student/goals`, `GET /api/student/goals/plan`.",
  ("Set an attendance goal", "Target 80 %", "Synced attendance", ["Open Goals", "Enter target attendance", "Save"], "Goal saved with a feasibility status")),
 ("US-19", S, "track my goals and be told when one is at risk",
  "Goal progress and alerts when a goal becomes unachievable.", "Students forget goals after setting them.",
  "After each sync re-evaluate saved goals and alert when a goal is behind or unachievable. Implemented with `goals.evaluate_attendance_course` and the goal alert job.",
  ("See goal progress", "Saved goal", "Goal exists", ["Open Goals", "Read the progress bar and status"], "Progress and status shown")),
 ("US-09", S, "look at my attendance in an earlier semester",
  "Attendance of previous terms.", "SDU shows only the current term at a glance.",
  "Return attendance of a term N semesters back. `GET /api/sdu/attendance?terms_back=N`.",
  ("Open last semester's attendance", "Semester picker", "Earlier terms exist", ["Open Overview", "Pick an earlier semester"], "Earlier term's courses shown")),
 ("US-20", S, "get a weekly summary of my progress",
  "Weekly summary of attendance, new marks, deadlines and goals; can be e-mailed.", "Progress is invisible week by week.",
  "Build a 7-day summary from stored sync history; show a headline; send it by e-mail on request. `GET /api/student/summary?period=week`, `POST /api/student/summary/email`.",
  ("Read the weekly summary", "Week period", "At least two syncs", ["Open Progress summary", "Choose This week"], "Headline and changes shown")),
 ("US-21", S, "get a monthly summary of my progress",
  "Monthly summary with an archive of past months.", "Long-term trends are lost.",
  "Build a 30-day summary and keep a monthly archive. `GET /api/student/summary?period=month`.",
  ("Read the monthly summary", "Month period", "Sync history exists", ["Open Progress summary", "Choose This month"], "Monthly figures shown")),
 ("US-23", S, "see my predicted academic risk and why",
  "AI risk percentage, predicted GPA and the reasons (SHAP).", "A single risk number without reasons cannot be trusted or acted on.",
  "Score risk 0 to 100 % and predicted GPA with a trained model; return the top reasons that raise it and the factors that help, with SHAP impacts and a plain-language summary. `POST /api/predict/risk`, `GET /api/monitoring/overview`.",
  ("Understand my risk", "Synced account", "Attendance and grades available", ["Open Monitoring", "Read AI risk assessment"], "Student can say what raises and lowers the risk")),
 ("US-24", S, "know how many classes I can still miss",
  "Safe-to-Skip bars: allowed absences per course.", "Students do not know the limit or how far they are from it.",
  "For each course show the absence limit before FX, hours missed, hours left and a green, yellow or red level; 'Not submitted' hours are shown separately. `GET /api/monitoring/overview`.",
  ("Find how many classes I can miss", "Synced account", "Class-hour counts available", ["Open Monitoring", "Read Safe to skip"], "Remaining skips named correctly for a course")),
 ("US-25", S, "simulate what skipping classes does to my risk and GPA",
  "What-if simulation of skipped lectures and practices.", "The effect of one absence is unknown until it is too late.",
  "Sliders for lectures and practices and a course choice; show the new predicted GPA and risk, the cost of one missed hour in that course, and a curve; mark the FX zone. `POST /api/simulate`.",
  ("Simulate skipping", "2 lectures, 1 practice, one course", "Monitoring data available", ["Open Monitoring", "Move the sliders", "Choose a course", "Read the result and chart"], "New GPA, risk and FX warning shown at once")),
 ("US-26", S, "see a feed of warnings, most serious first",
  "Alert feed with severity.", "Warnings are scattered across pages.",
  "List alerts (limit exceeded, 'Not submitted' over limit, close to limit, missed deadlines, high AI risk) sorted by severity. `GET /api/monitoring/alerts`.",
  ("Read the alert feed", "Synced account", "At least one warning", ["Open Monitoring", "Read Alerts"], "Most serious alert is first")),
 ("US-27", S, "get an e-mail when my risk is high, and let my curator know",
  "E-mail alerts to the student and an optional curator.", "Students do not open the app every day; curators never see the risk.",
  "At risk of 50 % or more send one e-mail to the student and one to the saved curator; at most once per 24 hours unless the risk jumps by 15 points; background job and after every sync. `PUT/GET/DELETE /api/monitoring/curator`, `POST /api/monitoring/notify`.",
  ("Add a curator and receive an alert", "Curator e-mail", "E-mail service configured", ["Open Monitoring", "Enter curator e-mail and Save", "Press Email me this"], "Student and curator both receive the message")),
 ("T-1", "Teacher", "see my students with their risk signals",
  "List of assigned students with attendance and risk factors; student card.", "Teachers cannot see who needs support without opening each record.",
  "Show only students in the teacher's scope with attendance and risk factors; open one student for courses and details; other students return 404. `GET /api/teacher/students`, `GET /api/teacher/students/{id}`.",
  ("Find a student at risk", "Teacher account", "Students assigned", ["Sign in as teacher", "Read the Watchlist", "Open a student"], "Student card opens with attendance and signals")),
 ("T-2", "Teacher", "record an intervention for a student",
  "Notes and actions history per student.", "Support actions are not recorded anywhere.",
  "Store an action type and notes per student and list the history. `POST/GET /api/teacher/students/{id}/interventions`.",
  ("Add a note for a student", "Type and note", "Student card open", ["Open a student", "Choose a type", "Write a note", "Save"], "Note appears in the history")),
 ("T-3", "Teacher", "see how attendance relates to performance in my group",
  "Attendance vs grade chart with correlation.", "Teachers lack evidence for the link between absence and results.",
  "Return one point per student and the correlation, with a note that it does not prove causation. `GET /api/teacher/analytics/attendance-performance`.",
  ("Read the attendance vs grade chart", "Group", "At least three students", ["Open the teacher dashboard", "Read the chart"], "Chart and correlation shown")),
]
AREAS = [
 ("1. Student: signing in and keeping data up to date", ["US-22"]),
 ("2. Student: understanding grades", ["US-06", "US-14", "US-15", "US-16", "US-07", "US-10", "US-17"]),
 ("3. Student: alerts and deadlines", ["US-05", "US-12", "US-13", "US-26"]),
 ("4. Student: planning goals", ["US-18", "US-19"]),
 ("5. Student: attendance and AI monitoring", ["US-09", "US-23", "US-24", "US-25", "US-27"]),
 ("6. Student: progress reports", ["US-20", "US-21"]),
 ("7. Teacher: supporting students", ["T-1", "T-2", "T-3"]),
]
BY_ID = {s[0]: s for s in STORIES}
ACTOR_TASK = {s[0]: i + 1 for i, s in enumerate(STORIES)}


# ───────────────────────── title page ─────────────────────────
add_page_number_footer()
para("Project #4 documentation, practice group #[[group number]]", bold=True, size=16, align="center", after=14)
para("Smart Student Performance Monitoring System", bold=True, size=20, align="center", after=16)
table(["Item", "Description"], [
    ["Project title", "Smart Student Performance Monitoring System (product name: StudyMate)"],
    ["Brief description", "Design an information system that analyzes academic data to identify students who may require additional academic support."],
    ["Main AI/IS functionality", "Predictive analytics, performance trends, risk indicators, dashboards and alerts."],
    ["Users", "Students and teachers of SDU (two roles)."],
    ["Source code", "https://github.com/qwopop/studymate-mon (branch `main`: stable; branch `dev`: new design)"],
    ["Working system", "[[link to the deployed system: add after deployment]]"],
    ["UI mock-ups", "[[public link to the mock-up repository (Figma or similar)]]"],
    ["Document version", date.today().strftime("%d %B %Y")],
], [4.2, 12.3])
para("Team members and roles", bold=True, keep=True)
table(["#", "Full name", "Role in the project"], [["1", "[[name]]", "[[role]]"], ["2", "[[name]]", "[[role]]"], ["3", "[[name]]", "[[role]]"]], [1.0, 7.0, 8.5])
para("Contents", bold=True, keep=True)
for t in ["1. Project requirements specification", "2. Project main functions (features, tasks)", "3. Project system architecture", "4. Project data modeling",
          "5. Project UI design", "6. Project software development code", "7. Project software testing", "8. Project software maintenance"]:
    para(t, after=1)
para("")
para("Fields shown in [[yellow brackets]] must be filled in by the team (group number, names, links); they are not known to the author of this draft.", italic=True, size=11)


# ───────────────────────── 1. requirements ─────────────────────────
h1("1. Project requirements specification")
para("The requirements follow the four required parts: user requirements (user stories), functional requirements, non-functional requirements and implementation/transition requirements. User and functional requirements cover all %d user stories of the project (%d for the student, 3 for the teacher). Numbers in the column Related to point to the requirement that a row serves." % (len(STORIES), len(STORIES) - 3))
rows = [["1", "User/Stakeholder", "", ""]]
for i, s in enumerate(STORIES, start=1):
    rows.append([f"1.{i}", "", f"{s[0]}: As a {s[1].lower()} I want to {s[2]}.", s[1]])
rows.append(["2", "Functional", "", ""])
for i, s in enumerate(STORIES, start=1):
    rows.append([f"2.{i}", "", s[5], f"User/Stakeholder (1.{i})"])
NFR = [
 ("Performance", "The API answers dashboard, risk and simulation requests in under 100 ms on a development machine. Measured: 30 to 60 ms per request; a 30-hour simulation curve in about 64 ms."),
 ("Efficiency", "Moving a simulation slider updates the screen within one frame. Measured: 17 ms; page scrolling stays at about 15 ms per frame (60 frames per second) after the visual redesign."),
 ("Security", "Passwords are stored only as salted PBKDF2-HMAC-SHA256 hashes (120,000 rounds); requests carry signed tokens; every SQL value is a bound parameter; the SDU password is never stored (a test searches every table for it); secrets live in environment variables."),
 ("Privacy / access control", "A student can read only their own data; a teacher only the students assigned to them; student-only and teacher-only routes answer 403 to the other role (tested)."),
 ("Reliability", "A failure of the SDU portal, Moodle or the e-mail service must not break the application: the error is reported to the user and the last synchronised data stay available."),
 ("Usability", "A new student completes the main tasks (read risk, find allowed absences, simulate skipping) without hints. To be verified by the usability tests in section 7."),
 ("Explainability", "Every AI score is shown with the reasons that raise or lower it (SHAP) and a one-sentence summary; the part that comes from SDU rules rather than from the model is labelled as a rule."),
 ("Portability", "Runs in current desktop and mobile browsers; layout adapts from 390 px phones to desktop (checked at 390, 1000 and 1280 px); light and dark themes."),
 ("Scalability", "Stateless API with a connection pool to PostgreSQL (Neon) selected by DATABASE_URL. Target: 200 concurrent users. No load test has been run yet."),
 ("Integrity / interoperability", "All functions and data are exposed through a documented REST API with an OpenAPI description (%d operations)." % 75),
 ("Availability", "Target 24/7 once deployed. The system is not deployed yet, so this is a target, not a measurement."),
 ("Maintainability", "%d automated tests (%d backend, %d frontend unit, %d component, %d end-to-end), %d%% backend coverage; modules separated by responsibility; documentation in the repository." % (BE["passed"] + FE["unit"] + FE["component"] + FE["e2e"], BE["passed"], FE["unit"], FE["component"], FE["e2e"], BE["coverage_total"])),
 ("Accessibility", "Visible keyboard focus, reduced-motion setting respected, status never shown by colour alone (each status also has text)."),
]
rows.append(["3", "Non-functional", "", ""])
for i, (cat, text) in enumerate(NFR, start=1):
    rows.append([f"3.{i}", "", text, cat])
IMPL = [
 "Backend: Python 3.12 or newer (3.13 tested), FastAPI; frontend: Node.js 20 or newer, React 19 and Vite.",
 "Database: SQLite file by default; PostgreSQL (for example Neon) when the environment variable DATABASE_URL is set; the same code runs on both.",
 "Configuration through environment variables or a `.env` file: DATABASE_URL, AUTH_SECRET, RESEND_API_KEY, RESEND_FROM, RISK_ALERT_THRESHOLD, MLFLOW_TRACKING_URI.",
 "The trained model file `backend/models/risk_model.joblib` is delivered with the code; retraining is one command (`python -m app.ml.train`).",
 "Deployment files are included: Dockerfile, render.yaml, railway.json, vercel.json.",
 "Transition: `scripts/migrate_sqlite_to_postgres.py` moves existing local data to PostgreSQL; the model can be retrained on SDU records with `--csv` once at least 200 students with known outcomes exist.",
 "The system reads SDU data with the student's own credentials and permission; it must be used only for the student's own account.",
]
rows.append(["4", "Implementation / Transition", "", ""])
for i, text in enumerate(IMPL, start=1):
    rows.append([f"4.{i}", "", text, ""])
table(["#", "TypeOfReq", "Definition", "Related to"], rows, [1.2, 2.8, 9.7, 2.8], size=10.5, split=False)


# ───────────────────────── 2. main functions ─────────────────────────
h1("2. Project main functions (features, tasks)")
para("The main functions are written as an annotated task list, one entry per user story, grouped by work area.")
rows = []
for title, ids in AREAS:
    rows.append(("__band__", f"Work area: {title}"))
    for sid in ids:
        s = BY_ID[sid]
        rows.append([[f"**{s[0]}:** As a {s[1].lower()} I want to {s[2]}.", f"Brief definition: {s[3]}", f"Problem: {s[4]}"]])
table(["Annotated task list"], rows, [16.5], size=11, split=False)


# ───────────────────────── 3. architecture ─────────────────────────
h1("3. Project system architecture")
para("The system is a web application with a React client and a Python (FastAPI) backend. The backend reads SDU data, applies the absence rules, runs the trained model and sends alerts. Data are stored in SQLite (local) or PostgreSQL (production). Figure 1 shows the architecture with a legend; the table below explains every element.")
figure(IMG / "architecture.png", 16.3, "Figure 1. System architecture diagram")
table(["Element", "Technology", "Responsibility", "Interfaces"], [
    ["Web client", "React 19, Vite, Recharts", "Pages for students and teachers, charts, sliders, light and dark theme", "HTTPS + JSON with a Bearer token"],
    ["Auth and roles", "FastAPI, PBKDF2, signed tokens", "Registration, sign-in, role checks (student / teacher)", "Used by every route"],
    ["Academic services", "Python modules `academics`, `goals`, `summaries`", "Grades, forecast, goals, summaries, study plan", "REST routes, database"],
    ["SDU integration", "httpx, BeautifulSoup, Fernet", "Portal sign-in and scraping, Moodle calendar, 'Not submitted' = pending; stores encrypted cookies", "HTTPS (HTML, iCal)"],
    ["Absence rules", "Python module `monitoring`", "Allowed absences per course, cost of a missed hour, Safe-to-Skip, simulation", "Called by REST routes"],
    ["AI module", "scikit-learn, SHAP, joblib", "Predicts risk and GPA, explains the score", "Loads the model file"],
    ["Alert job", "APScheduler, Resend", "Sends e-mail when risk is 50 % or more, with a 24-hour cool-down", "HTTPS (JSON)"],
    ["REST API", "FastAPI, OpenAPI", "75 operations, interactive documentation at /docs", "HTTPS + JSON"],
    ["Database", "SQLite / PostgreSQL (Neon)", "Users, students, grades, attendance, predictions, alerts", "SQL with bound parameters"],
    ["Model file", "joblib", "Trained RandomForest models and their metrics", "File"],
    ["DagsHub / MLflow", "MLflow", "Experiment tracking while training", "HTTPS (training only)"],
], [2.6, 3.6, 6.7, 3.6], size=10.5)
h2("Remarks on the architecture")
bullets([
    "**Protocols.** Browser and backend talk HTTPS with JSON; the backend talks to the SDU portal over HTTPS (HTML pages), to Moodle over HTTPS (iCal export), to the e-mail service over HTTPS (JSON) and to the database with SQL.",
    "**One database layer.** `backend/app/db.py` translates the SQLite SQL dialect to PostgreSQL, so one code path serves both; the whole backend test suite passes on both.",
    "**No password storage.** The SDU password exists only inside the sign-in request; only the portal session cookies are kept, encrypted.",
    "**AI and rules are separate.** The model is trained offline (Figure 2); at request time the rule layer for absences is applied to its output and then combined (model risk + rule risk, with at least 90 % at the FX limit).",
])
figure(IMG / "ml_pipeline.png", 16.3, "Figure 2. AI pipeline: training once, scoring at every request")


# ───────────────────────── 4. data model ─────────────────────────
h1("4. Project data modeling")
para("Figure 3 shows the core tables of the real database schema (created by `SQLiteRepository` and `monitoring_store.py`). Tables are grouped: the authentication cluster at the top, the student record in the middle, and the per-student tables, which all carry a student_id column, in the dashed frame.")
figure(IMG / "er_diagram.png", 15.8, "Figure 3. Data model (entity-relationship diagram)")
h2("Notes about non-trivial entities")
bullets([
    "**users and login_identifiers:** one account can sign in with several names (e-mail or student number); passwords are stored only as salt and PBKDF2 hash.",
    "**sdu_connections:** the SDU session of an account. `access_token` holds the portal cookies sealed with Fernet encryption; the SDU password is never stored.",
    "**sdu_snapshots:** the last good copy of each kind of synchronised data (transcript, schedule, attendance_detail, grade_components, goal alerts, progress history), one row per user and kind, so pages still work when SDU is slow.",
    "**students and teacher_scope:** the student record and the many-to-many link that says which teacher may see which student.",
    "**grades and assessment_items:** a course of a student with its credits and the weighted parts (midterm, final) as JSON and as rows.",
    "**attendance_log:** one row per class hour with its status: present, absent, permitted, **pending** (a past hour the teacher has not marked, shown by SDU as 'Not submitted') or upcoming. Pending is not an absence; the model and the alerts treat it separately.",
    "**attendance_sessions:** older table with present, excused and absent only (demo data).",
    "**risk_history:** one row per risk check (risk 0 to 1, predicted GPA, time); gives the risk trend.",
    "**curators and risk_alert_log:** the optional curator e-mail of a student and the time of the last e-mail alert, used for the 24-hour cool-down.",
    "**notifications and interventions:** in-app alerts of a student and the teacher's notes about a student.",
    "**Access:** plain SQL with bound parameters (no ORM); the SQL text never contains user input.",
])


# ───────────────────────── 5. UI design ─────────────────────────
h1("5. Project UI design")
para("The prototypes below are the screens of the working interface (light theme is the default; a dark theme is available). Under each screen the user tasks it supports are listed. Public link to the mock-up repository: [[link to Figma or other mock-up repository]].")
SCREENS = [
 ("ui_login.png", "Sign in", ["T1. Sign in with student number, teacher username or e-mail and password (and the e-mailed code).", "T2. Create an account.", "T3. Recover a forgotten password.", "T4. Switch between light and dark theme."], "US-22"),
 ("ui_overview.png", "Overview", ["T1. See GPA, attendance and credits for a semester.", "T2. See the predicted GPA and risk and open Monitoring.", "T3. See the next class and the deadlines of the week.", "T4. See what needs attention."], "US-05, US-09, US-12, US-23"),
 ("ui_overview_dark.png", "Overview in the dark theme", ["T1. Same tasks as the light Overview.", "T2. Switch theme with the moon / sun button."], "All"),
 ("ui_schedule.png", "Schedule", ["T1. Choose a day of the week.", "T2. See time, course, room, lesson type, periods, teacher and code of each class.", "T3. See which class is next."], "US-22"),
 ("ui_grades.png", "Grades", ["T1. See courses and grades per semester.", "T2. Open the grade breakdown of a course.", "T3. Read the final-grade forecast."], "US-10, US-17"),
 ("ui_whatif.png", "What-if planner", ["T1. Choose a course.", "T2. Enter weights and scores of assessments.", "T3. Enter a target grade and calculate the score needed."], "US-10"),
 ("ui_attendance.png", "Attendance", ["T1. See absence per course against the 30 % FX limit.", "T2. Press Sync with SDU and read the last sync time."], "US-09, US-22"),
 ("ui_insights.png", "Insights", ["T1. Compare subjects and read the strengths.", "T2. Read the weakest subjects and tick study-plan tasks.", "T3. Read the forecast for difficult subjects."], "US-06, US-07, US-14, US-15, US-16, US-17"),
 ("ui_monitoring.png", "Monitoring (AI)", ["T1. Read Safe to skip: allowed absences per course.", "T2. Read the AI risk, predicted GPA and reasons.", "T3. Move the sliders and read the simulation.", "T4. Read the alerts and press Email me this.", "T5. Save a curator e-mail."], "US-23, US-24, US-25, US-26, US-27"),
 ("ui_goals.png", "Goals", ["T1. Set GPA, attendance and course targets.", "T2. Read whether each target is still reachable."], "US-18, US-19"),
 ("ui_summary.png", "Progress summary", ["T1. Switch between this week and this month.", "T2. Read attendance, marks and deadlines.", "T3. Press Email me."], "US-20, US-21"),
 ("ui_profile.png", "Profile", ["T1. See the connected SDU account and last sync.", "T2. Refresh data or disconnect SDU.", "T3. Set a StudyMate password."], "US-22"),
 ("ui_support.png", "Help and support", ["T1. Send a support request.", "T2. Read the replies."], "Support"),
 ("ui_teacher.png", "Teacher: class overview", ["T1. See the number of students, how many are at risk and the average attendance.", "T2. Search or filter the watchlist.", "T3. Read the attendance vs grade chart."], "T-1, T-3"),
 ("ui_teacher_student.png", "Teacher: student card", ["T1. See attendance, risk signals and courses of one student.", "T2. Add a note or intervention."], "T-1, T-2"),
]
for i, (img, title, tasks, stories) in enumerate(SCREENS, start=1):
    para(f"**Screen {i}. {title}** (user stories: {stories})", keep=True, after=3)
    figure(IMG / img, 13.2, f"Figure {i + 3}. {title}")
    para("User tasks:", bold=True, after=1, keep=True)
    bullets(tasks)


# ───────────────────────── 6. code ─────────────────────────
h1("6. Project software development code")
h2("Tools, platforms, language and environment")
table(["Area", "Tools and platforms"], [
    ["Programming languages", "Python 3.13 (backend, machine learning), JavaScript / JSX (frontend), SQL, CSS"],
    ["Backend", "FastAPI, Uvicorn, Pydantic, httpx, BeautifulSoup, cryptography (Fernet), APScheduler, psycopg"],
    ["Machine learning", "scikit-learn (RandomForest), SHAP, joblib, NumPy; public data set UCI Student Performance (1,044 students)"],
    ["Frontend", "React 19, Vite, Recharts"],
    ["Database", "SQLite (development), PostgreSQL on Neon (production)"],
    ["Services", "SDU portal (read-only, with the student's own account), Moodle calendar export, Resend (e-mail), DagsHub / MLflow (experiment tracking)"],
    ["Testing", "pytest, pytest-cov, FastAPI TestClient, httpx MockTransport, Vitest, React Testing Library, Playwright, node:test"],
    ["Development environment", "Git and GitHub, Visual Studio Code or any editor, Linux container and Windows 11 for running, Chromium for end-to-end tests"],
], [4.0, 12.5], size=11)
h2("How to run the system (configuration details)")
code("""git clone https://github.com/qwopop/studymate-mon.git
cd studymate-mon/backend
python -m pip install -r requirements.txt
set ENABLE_DEMO_MODE=1            (Windows;  export ENABLE_DEMO_MODE=1 on Linux or macOS; demo data, no SDU account needed)
python -m uvicorn app.main:app --port 8000

cd ../frontend
npm install
npm run dev                       (open http://localhost:5173; API documentation at http://localhost:8000/docs)

Optional settings (backend/.env): DATABASE_URL (Neon), RESEND_API_KEY, MLFLOW_TRACKING_URI ...""", size=8.5)
para("Link to the working system: [[http:// ... add the link after deployment; the system must load immediately after clicking it]]", italic=True)
h2("Important elements of the code, by user story")
para("Excerpts are cut from the real source files. Each excerpt is followed by a description of its purpose.")

SNIPPETS = [
 ("US-22: sign-in and 'Not submitted' (pending) status", "backend/app/sdu_portal.py", sdu_portal.login, None,
  "`login` signs in to my.sdu.edu.kz with the student's own number and password. The password is used only inside this request; afterwards only the portal cookies are kept, and they are stored encrypted. If SDU asks for the e-mailed code, a sealed pending state is returned instead."),
 (None, "backend/app/sdu_portal.py", sdu_portal.parse_journal_sessions, None,
  "`parse_journal_sessions` reads one course's attendance journal. Every class hour gets its own status; a past hour that the teacher has not marked is stored as `pending` ('Not submitted') and not as an absence. The statuses are written to the table `attendance_log` on every sync."),
 ("US-05: alerts for absences", "backend/app/repository.py", repository.SQLiteRepository._notify_absence_changes, None,
  "After a sync the new absence percentages are compared with the previous snapshot. A notification is created only when a course crosses the warning level (25 %) or the FX limit (30 %), and once for overall attendance below 70 %, so students are not flooded with repeats."),
 ("US-06, US-14, US-15, US-07: weak subjects and study plan", "backend/app/main.py", app_main.student_insights, None,
  "`student_insights` ranks the graded courses of the term from weakest to strongest, flags every course below 60 % as weak, finds the weakest topic when a breakdown exists, and attaches three study tasks to every weak course."),
 (None, "backend/app/main.py", app_main.study_task_texts, None,
  "`study_task_texts` builds the three concrete tasks of the study plan from real course data (course name and weakest topic), so advice is specific."),
 ("US-10: What-if planner", "backend/app/main.py", app_main.solve_whatif, None,
  "`solve_whatif` checks that component names are unique and weights add up to 100 %, then computes the score needed on one component to reach the target final grade: (target minus the weighted score of the other components) divided by the component's weight."),
 ("US-12, US-13: deadlines", "backend/app/deadlines.py", deadlines.missed, None,
  "`missed` returns the past-due items that the Moodle payload explicitly marks as not submitted; each produces exactly one urgent alert."),
 ("US-16: study resources", "backend/app/academics.py", academics.study_resources, None,
  "`study_resources` returns lecture videos, a practice set and a library search link for one weak course."),
 ("US-17: final-grade forecast", "backend/app/academics.py", academics.forecast, None,
  "`forecast` needs at least 70 % of a course graded. It expects the remaining work to follow this term's form (70 %) pulled slightly towards past results (30 %) and returns a 95 % interval that narrows as more of the course is graded."),
 ("US-18, US-19: goals and feasibility", "backend/app/goals.py", goals.evaluate_attendance_course, 45,
  "`evaluate_attendance_course` applies the SDU rule that absence is missed hours divided by all scheduled hours and excused hours do not count. Attendance can only fall, so the current value is also the maximum still achievable; the function states whether a target is reachable and how many hours may still be missed."),
 ("US-20, US-21: summaries", "backend/app/summaries.py", summaries.attendance_between, None,
  "`attendance_between` compares two stored sync points and reports the class hours attended and missed in between (SDU counts excused hours as attended); the weekly and monthly summaries are built from it."),
 ("US-23: AI risk and explanation", "backend/app/ml/model.py", ml_model.predict, None,
  "`predict` scores one student with the trained RandomForest, anchors the GPA to the real current GPA, and explains the score with SHAP: the factors that raise the risk and the factors that keep it low, each with its effect in percentage points."),
 (None, "backend/app/monitoring.py", monitoring.score, None,
  "`score` runs the model and then the SDU absence rule: the rule adds risk and lowers the GPA as allowed absences are used up, a named reason is added, and reaching the FX limit forces at least 90 % risk."),
 ("US-24: Safe to skip", "backend/app/monitoring.py", monitoring.course_status, None,
  "`course_status` computes, per course, the allowed absences before FX (`ceil(hours x 30 %) - 1`), the hours left, the level (safe, warning, danger), and the share of the allowance one missed hour costs."),
 ("US-25: simulation", "backend/app/monitoring.py", monitoring.course_pressures, None,
  "`course_pressures` expresses, for each course, how much of its allowance is used up (a 'Not submitted' hour counts as half an absence). A course with few weekly lessons has a small allowance, so one missed hour weighs more."),
 (None, "backend/app/monitoring.py", monitoring._pressure_effect, None,
  "`_pressure_effect` turns the pressures into extra risk and lost GPA: smooth and rising, a jump when the limit is passed; the worst course counts fully and every other course adds a part, so absences in several courses add up."),
 ("US-26: alert feed", "backend/app/monitoring.py", monitoring.build_alerts, 34,
  "`build_alerts` builds the warning feed: limit exceeded, 'Not submitted' hours that could push a course over the limit, courses close to the limit, missed deadlines and a high AI risk, sorted from critical to info."),
 ("US-27: e-mail alerts", "backend/app/monitoring_api.py", monitoring_api.send_risk_alert, None,
  "`send_risk_alert` sends one e-mail to the student and one to the saved curator when the risk is at the threshold, and not again within the cool-down unless the risk rises by 15 points."),
 ("T-1: teacher risk signals", "backend/app/main.py", app_main.risks, None,
  "`risks` lists the explainable risk factors of one student (low grades, low attendance, missed assignments) shown in the teacher's watchlist."),
 (None, "backend/app/main.py", app_main.teacher_students, None,
  "`teacher_students` returns only the students in the teacher's scope together with their attendance and risk factors."),
 ("T-3: attendance vs performance", "backend/app/main.py", app_main.attendance_performance, None,
  "`attendance_performance` pairs each student's attendance with their average grade and computes the Pearson correlation, with a note that correlation does not prove causation; with fewer than three students it says there is not enough data."),
]
for title, path, obj, limit, desc in SNIPPETS:
    if title: h3(title)
    para(f"File `{path}`", size=11, after=2, keep=True)
    code(source(obj, limit))
    para("**Description:** " + desc)

h3("Front-end code (React, JavaScript, CSS)")
para("Front-end technology: React 19 with Vite, Recharts for charts, plain CSS with design tokens for the light and dark themes.")
para("File `frontend/src/theme.css`: the design tokens of the light (default) theme.", size=11, after=2, keep=True)
code(file_slice("frontend/src/theme.css", ":root {", "/* ─── Dark theme"), 8)
para("**Description:** the whole look of the application comes from these tokens (colours, radii, shadows); the dark theme overrides the same names, so every page switches theme without changing its own styles.")
para("File `frontend/src/monitoring.js`: the simulation card computes its numbers locally.", size=11, after=2, keep=True)
code(file_slice("frontend/src/monitoring.js", "/** Everything the simulation card shows", "/** Why one missed hour weighs"), 8)
para("**Description:** the server sends the whole risk and GPA curve once per course; moving a slider only reads this curve, so the answer appears at once without a new request (measured: 17 ms).")
para("File `frontend/src/Monitoring.jsx`: loading the curve and deriving the chart rows.", size=11, after=2, keep=True)
code(file_slice("frontend/src/Monitoring.jsx", "const CURVE_HOURS", "const here ="), 8)
para("**Description:** one request per course loads the curve; `useMemo` derives the view and the visible part of the chart from the slider values.")


# ───────────────────────── 7. testing ─────────────────────────
h1("7. Project software testing")
total_tests = BE["passed"] + FE["unit"] + FE["component"] + FE["e2e"]
para(f"The project was tested at four levels: usability testing, unit and integration tests, component and end-to-end tests, and customer acceptance (QA) tests. All automated tests were run together for this document on {date.today().strftime('%d %B %Y')}: **{total_tests} automated tests, 0 failed**.")
h2("7.1 Types of testing, tools and platforms")
table(["Type of testing", "Purpose", "Tools and platforms"], [
    ["Usability testing (mandatory)", "Can real students complete every user task without help?", "Task scripts and forms in 7.2; real users; the system in a browser"],
    ["Unit tests (mandatory)", "Individual functions: grade points, forecast, goals, absence rules, model features", "Python 3.13, pytest, pytest-cov; Node.js `node:test`"],
    ["Integration tests", "API endpoints with a real database and authorization", "FastAPI TestClient, SQLite and PostgreSQL 16"],
    ["Mocking", "SDU parsers without contacting the university", "httpx MockTransport serving made-up portal pages; pytest monkeypatch for e-mail"],
    ["Component tests", "React components with given data", "Vitest, React Testing Library, jsdom"],
    ["End-to-end tests", "Sign in, Monitoring, sliders and Sync in a real browser", "Playwright with Chromium, real backend, demo data"],
    ["Customer acceptance (QA) tests (mandatory)", "Given / When / Then scenario for every user story", "pytest scenarios (7.5), run against the real HTTP API"],
    ["Other", "Security (password not stored), performance, database parity", "Search of all tables, timing scripts, test run on PostgreSQL 16"],
], [4.0, 6.4, 6.1], size=10.5)

h2("7.2 Usability testing")
para("Method: task-based, think-aloud sessions. **Participants:** undergraduate students of SDU who use my.sdu.edu.kz at least weekly (the target profile), at least five students, and one or two teachers for the teacher tasks. Each participant receives one task at a time without hints; the observer records success, time, errors and comments. **Usability tests are provided for all user tasks (user stories).** The sessions have not been carried out yet: the forms below are ready to be filled in and the results table must be completed after the sessions.", after=6)
rows = []
for s in STORIES:
    goal, inputs, assume, steps, success = s[6]
    rows.append([s[0], goal, inputs, assume, [f"{i}. {t}" for i, t in enumerate(steps, 1)], success])
table(["Task", "Goal / output", "Inputs", "Assumptions", "Steps", "Success criteria"], rows, [1.3, 2.9, 2.5, 2.6, 4.2, 3.0], size=9.5)
h3("Analysis form for the usability results")
table(["User ID", "Category", "Task", "Problem", "Tag 1", "Tag 2"],
      [["1", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"], ["2", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"], ["3", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"], ["4", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"], ["5", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"]],
      [1.4, 2.6, 3.2, 5.0, 2.1, 2.2], size=10.5)
table(["Measure", "Target", "Result"], [
    ["Task completion rate (all participants, all tasks)", "at least 90 %", "[[to fill after sessions]]"],
    ["Average time to read the AI risk and the allowed absences", "under 60 seconds", "[[to fill after sessions]]"],
    ["Errors per task (wrong clicks, help requests)", "at most 1", "[[to fill after sessions]]"],
    ["Satisfaction (SUS questionnaire, 0 to 100)", "at least 75", "[[to fill after sessions]]"],
], [8.0, 3.5, 5.0], size=10.5)
para("Analysis: [[after the sessions, write which tasks failed, the most frequent problem tags, the changes made and whether the system is usable enough]]", italic=True)

h2("7.3 Unit and integration tests")
para("Unit tests check single functions; integration tests call the API endpoints through the real application with a database and authorization. Every user story has unit or integration tests (table below). The SDU parsers are tested with a **fake portal**, so no test sends a request to the university.")
pf = BE["per_file"]
table(["Test module", "What it tests", "User stories", "Tests"], [
    ["test_academics.py", "Grade points, GPA, subject ranking, strengths, study resources, forecast, goal progress", "US-06, 14, 15, 16, 17, 18", pf.get("test_academics")],
    ["test_goals.py", "Feasibility of GPA, attendance and course goals; class-hour counts; goal alerts", "US-18, 19", pf.get("test_goals")],
    ["test_summaries.py", "Sync history, attendance between two points, weekly and monthly summaries", "US-20, 21", pf.get("test_summaries")],
    ["test_api.py", "Authentication, ownership, teacher scope, dashboard, grades, deadlines, tutoring, support, notifications, what-if", "US-05, 06, 07, 09, 10, 12, 13, T-1, T-2, T-3", pf.get("test_api")],
    ["test_portal.py, test_pms_portal.py, test_moodle_calendar.py", "SDU sign-in and parsers against a fake portal; password not stored", "US-22, 12", (pf.get("test_portal") or 0) + (pf.get("test_pms_portal") or 0) + (pf.get("test_moodle_calendar") or 0)],
    ["test_db_translate.py", "SQLite to PostgreSQL SQL translation", "database layer", pf.get("test_db_translate")],
    ["test_monitoring.py", "Features, absence rules, risk model, simulation, alerts, e-mail, public-data import", "US-23 to US-27", pf.get("test_monitoring")],
    ["test_acceptance.py", "Given / When / Then scenarios (see 7.5)", "all", pf.get("test_acceptance")],
    ["frontend unit tests (node:test)", "GPA, schedule, goals and Monitoring helper functions", "US-10, 18, 24, 25", FE["unit"]],
], [4.2, 6.4, 3.6, 1.6], size=10.5)
h3("Results of the unit and integration tests")
code(f"backend:  {BE['passed']} passed, {BE['failed']} failed in {BE['seconds']:.1f} s   (pytest)\n"
     f"coverage: {BE['coverage_total']} % of {BE['statements']} statements   (pytest-cov)\n"
     f"frontend: {FE['unit']} passed (node --test)", 9)
rows = [[m[0].replace("\\", "/"), m[1], m[2], m[3]] for m in BE["modules"]]
table(["Module", "Statements", "Missed", "Coverage"], rows, [8.0, 2.8, 2.8, 2.9], size=9.5)

h2("7.4 Component and end-to-end tests")
bullets([
    f"**Component tests ({FE['component']} passed, Vitest and React Testing Library).** The Monitoring tab shows the allowed-absence line and colours per level; explains the risk with reasons for and against; lists the 'Not submitted' warning; syncs and reloads; loads the curve once per course and answers the sliders locally; explains the cost of one missed hour; shows a clear error; the sync bar, the Predicted GPA widget and the forecast chart. A deliberate code change was used to prove that the tests fail when they should.",
    f"**End-to-end tests ({FE['e2e']} passed, Playwright).** Student signs in with the form (e-mail account, so the real university is never contacted); the Monitoring page shows Safe to skip, AI risk, simulation and alerts; sliders update without a new request; Sync updates 'Last synced'; the Overview widget opens Monitoring.",
])

h2("7.5 Customer acceptance tests (QA tests)")
para("The scenarios are written in the Given / When / Then form and run automatically through the real HTTP API (pytest, file `backend/tests/test_acceptance.py`). Each scenario is named after its user story. A special BDD tool such as Cucumber was not used; the pytest scenarios have the same structure and a pass / fail result.")
tree = ast.parse((ROOT / "backend/tests/test_acceptance.py").read_text())
result = {c["name"]: c["status"] for c in BE["cases"] if c["file"] == "test_acceptance"}
for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]:
    docstr = ast.get_docstring(fn) or ""
    lines = [l.strip() for l in docstr.splitlines() if l.strip()]
    sid = re.match(r"test_([A-Z]+\d*[A-Za-z]?\d*(?:_[A-Z]+\d+)*)", fn.name)
    outcome = [v for k, v in result.items() if k.startswith(fn.name)]
    status = "Passed" if outcome and all(o == "passed" for o in outcome) else ("Skipped" if outcome and "skipped" in outcome else "Check")
    rows = []
    for l in lines:
        m = re.match(r"(Given|When|Then|And)\s+(.*)", l)
        rows.append([m.group(1), m.group(2)] if m else ["", l])
    title = fn.name[5:].replace("_", " ")
    t = table(["Scenario", title], [[k, v] for k, v in rows] + [["Result", f"**{status}**"]], [3.0, 13.5], size=10)

h2("7.6 Analysis of the test results and their adequacy")
table(["Measure", "Result"], [
    ["Automated tests", f"{total_tests} run, 0 failed ({BE['passed']} backend, {FE['unit']} frontend unit, {FE['component']} component, {FE['e2e']} end-to-end)"],
    ["Acceptance scenarios", f"{len(result)} scenarios for all {len(STORIES)} user stories, all passed"],
    ["Backend code coverage", f"{BE['coverage_total']} %"],
    ["Database parity", "The whole backend suite also passed on PostgreSQL 16"],
    ["Security check", "The SDU password is found in no table after sign-in and sync"],
    ["Performance (development machine)", "API 30 to 60 ms; 30-hour simulation curve 64 ms; slider to screen 17 ms; scrolling 15 ms per frame"],
], [5.0, 11.5], size=10.5)
para("**Readiness.** All automated and acceptance tests pass, so the implemented functions behave as specified and the system is ready for acceptance on the tested paths. The coverage is high (%d %%); the least covered modules are optional or external-facing code: the MLflow upload (`ml/tracking.py`), the training command line (`ml/train.py`), the public-data download (`ml/public_data.py`), the old OAuth client (`sdu_client.py`) and the database translator branches for PostgreSQL-only paths." % BE["coverage_total"])
para("**What is not proven.** (1) Usability with real users is still to be done (7.2). (2) The SDU scraper is tested against a fake portal, not systematically against the live portal. (3) E-mail delivery and Neon were tested with stand-ins (mocks and a local PostgreSQL 16). (4) No load test has been run. These limits are listed again in the maintenance plan.")


# ───────────────────────── 8. maintenance ─────────────────────────
h1("8. Project software maintenance")
para("Three planned activities for maintenance and the next releases follow. The expected results are targets, to be measured after each activity.")
table(["#", "Problem / Activity", "Solution", "Expected results"], [
    ["1", "The risk model is trained on a public data set (Portuguese schools), not on SDU data, and it learned almost nothing about absences or 'Not submitted' hours, which are covered by rules.",
     ["Collect consented SDU history (grades, attendance, final outcome) of at least 200 students, 20 or more per outcome.", "Retrain with `python -m app.ml.train --csv students.csv`, compare runs on DagsHub and deploy the better model file."],
     ["Accuracy and F1 on SDU hold-out students reported and not lower than now (0.97 on the public data).", "Absence and pending effects learned from data, so the rule layer can be reduced.", "The documentation states the new data source."]],
    ["2", "The system is not deployed; there is no working-system link and no measured availability.",
     ["Deploy the backend (Render or Railway) and the frontend (Vercel) with Neon PostgreSQL; set DATABASE_URL and e-mail keys as environment variables.", "Add health checks (`/health`), daily database backups and error alerts."],
     ["The system loads from a public link at any time (availability target 99 % per month).", "Real e-mail alerts to students and curators.", "A load test shows 200 concurrent users are served."]],
    ["3", "The SDU portal pages can change without notice and break the scraper.",
     ["Keep the fake-portal contract tests current and add a daily live smoke check of sign-in and journal parsing with a test account.", "Alert the team when a parser returns no data; show students their last good data meanwhile."],
     ["A layout change is detected within one day and fixed within two working days.", "Students never see an empty dashboard because of a parser failure."]],
], [0.8, 4.4, 6.0, 5.3], size=10.5)
h2("Next releases (prospective)")
bullets([
    "Show the AI risk and predicted GPA to teachers in the class overview (the API already ranks students by risk).",
    "Push notifications and a mobile app on top of the same API.",
    "Per-course risk forecast for the rest of the term, and recommendations for the best classes to attend.",
    "Group usability findings into a quarterly improvement cycle.",
])

doc.core_properties.title = "Project 4 documentation: Smart Student Performance Monitoring System"
doc.core_properties.author = "Project team"
doc.save(str(OUT) + ".docx")
print("saved", str(OUT) + ".docx")
subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(HERE), str(OUT) + ".docx"], capture_output=True)
print("pdf", (Path(str(OUT) + ".pdf")).exists())
