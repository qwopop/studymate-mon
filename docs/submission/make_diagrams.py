"""Draws the three figures used in the project documentation (run: python make_diagrams.py).

architecture.png  system architecture with a legend
er_diagram.png    data model (core tables of the real schema)
ml_pipeline.png   how the AI part is trained and used
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FONT = "DejaVu Sans"
INK, EDGE, QUIET = "#1b1738", "#5b4bc4", "#6b6588"
INTERNAL, DB, EXTERNAL, ML, ACCENT = "#e9e4ff", "#dff3ea", "#fff1dc", "#f7e3ff", "#7138E8"


def box(ax, x, y, w, h, title, lines=(), fc=INTERNAL, ec=EDGE, tsize=10, lsize=8, bold=True, rounding=0.12):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={rounding}", fc=fc, ec=ec, lw=1.3, zorder=2))
    ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="center", fontsize=tsize, fontweight="bold" if bold else "normal", color=INK, family=FONT, zorder=3)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.60 - i * 0.26, line, ha="center", va="center", fontsize=lsize, color=QUIET, family=FONT, zorder=3)


def arrow(ax, p, q, label=None, both=False, dashed=False, color=EDGE, loff=(0, 0.14), lsize=7.5, rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=11, lw=1.3, color=color,
                                 linestyle=(0, (4, 3)) if dashed else "-", connectionstyle=f"arc3,rad={rad}", zorder=1))
    if label:
        ax.text((p[0] + q[0]) / 2 + loff[0], (p[1] + q[1]) / 2 + loff[1], label, ha="center", va="center", fontsize=lsize, color=INK, family=FONT,
                bbox=dict(fc="white", ec="none", pad=1.0), zorder=4)


def new(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=170)
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    return fig, ax


def architecture():
    fig, ax = new(15, 10.2)
    ax.text(0.3, 9.85, "StudyMate: Smart Student Performance Monitoring System, system architecture", fontsize=12.5, fontweight="bold", color=INK, family=FONT)
    # actors
    for x, name in ((2.2, "Student"), (5.6, "Teacher")):
        ax.add_patch(plt.Circle((x, 9.15), 0.2, fc="#fbd5e1", ec=EDGE, lw=1.2, zorder=2))
        ax.plot([x, x], [8.95, 8.65], color=EDGE, lw=1.4); ax.plot([x - 0.22, x + 0.22], [8.85, 8.85], color=EDGE, lw=1.4)
        ax.text(x, 8.45, name, ha="center", fontsize=9, family=FONT, color=INK)
        arrow(ax, (x, 8.3), (x, 8.12), None)
    # client
    ax.add_patch(FancyBboxPatch((0.4, 6.45), 7.4, 1.65, boxstyle="round,pad=0,rounding_size=0.15", fc="none", ec=EDGE, lw=1.4, ls="--", zorder=1))
    ax.text(0.6, 7.88, "Web client (browser)", fontsize=9.5, fontweight="bold", color=EDGE, family=FONT)
    box(ax, 0.6, 6.6, 7.0, 1.05, "React 19 + Vite single-page app", ["Overview · Schedule · Grades · Attendance · Insights · Monitoring · Goals", "Teacher dashboard · Recharts charts"], tsize=9.5, lsize=7.4)
    arrow(ax, (4.0, 6.45), (4.0, 5.95), "HTTPS  <<JSON>>  Bearer token", both=True, loff=(1.75, 0.0))
    # backend
    ax.add_patch(FancyBboxPatch((0.4, 2.55), 10.4, 3.4, boxstyle="round,pad=0,rounding_size=0.15", fc="none", ec=EDGE, lw=1.4, ls="--", zorder=1))
    ax.text(0.6, 5.72, "FastAPI backend (Python)", fontsize=9.5, fontweight="bold", color=EDGE, family=FONT)
    box(ax, 0.6, 4.1, 2.4, 1.3, "Auth and roles", ["PBKDF2 passwords", "signed tokens", "student / teacher"], lsize=7.4)
    box(ax, 3.2, 4.1, 2.4, 1.3, "Academic services", ["grades · forecast", "goals · summaries", "study plan"], lsize=7.4)
    box(ax, 5.8, 4.1, 2.4, 1.3, "REST API", ["75 operations", "OpenAPI at /docs", "JSON over HTTPS"], lsize=7.4)
    box(ax, 8.4, 4.1, 2.2, 1.3, "SDU integration", ["portal scraper", "Moodle iCal", "'Not submitted' = pending"], lsize=7.0)
    box(ax, 0.6, 2.75, 3.9, 1.1, "Absence rules (SDU)", ["limit before FX · cost of a missed hour", "Safe-to-Skip · simulation"], lsize=7.4)
    box(ax, 4.7, 2.75, 3.4, 1.1, "AI module", ["RandomForest + SHAP", "predicted risk and GPA"], fc=ML, lsize=7.4)
    box(ax, 8.3, 2.75, 2.3, 1.1, "Alert job", ["APScheduler · risk ≥ 50 %", "e-mail student + curator"], lsize=7.0)
    # data
    box(ax, 0.6, 0.55, 3.3, 1.2, "Database", ["SQLite (local)", "PostgreSQL on Neon (production)"], fc=DB, lsize=7.4)
    box(ax, 4.3, 0.55, 3.0, 1.2, "Model file", ["risk_model.joblib", "metrics.json"], fc=DB, lsize=7.4)
    arrow(ax, (2.25, 2.55), (2.25, 1.75), "SQL", both=True, loff=(0.3, 0.0))
    arrow(ax, (6.4, 2.75), (5.8, 1.75), "load", loff=(0.35, 0.0))
    # externals
    box(ax, 11.6, 6.6, 3.1, 1.15, "SDU portal", ["my.sdu.edu.kz (attendance, grades)"], fc=EXTERNAL, lsize=7.2)
    box(ax, 11.6, 5.05, 3.1, 1.15, "Moodle calendar", ["deadlines (iCal export)"], fc=EXTERNAL, lsize=7.2)
    box(ax, 11.6, 3.5, 3.1, 1.15, "E-mail service", ["Resend (or Gmail SMTP)"], fc=EXTERNAL, lsize=7.2)
    box(ax, 11.6, 1.95, 3.1, 1.15, "DagsHub / MLflow", ["experiment tracking (training only)"], fc=EXTERNAL, lsize=7.2)
    arrow(ax, (10.6, 5.2), (11.6, 7.0), "HTTPS <<HTML>> + cookies", both=True, loff=(-0.55, 0.55))
    arrow(ax, (10.6, 4.75), (11.6, 5.6), "HTTPS <<iCal>>", both=True, loff=(-0.1, -0.38))
    arrow(ax, (10.6, 3.2), (11.6, 4.05), "HTTPS <<JSON>>", loff=(-0.1, -0.38))
    arrow(ax, (10.8, 2.75), (11.6, 2.5), "training", dashed=True, loff=(-0.1, -0.3))
    # legend
    ax.add_patch(FancyBboxPatch((8.0, 0.3), 6.7, 1.4, boxstyle="round,pad=0,rounding_size=0.1", fc="white", ec="#9b95b8", lw=1.0, zorder=1))
    ax.text(8.2, 1.48, "LEGEND", fontsize=8.5, fontweight="bold", family=FONT, color=INK)
    for i, (fc, txt) in enumerate(((INTERNAL, "Internal component"), (ML, "AI / machine-learning component"), (DB, "Database or file store"), (EXTERNAL, "External system"))):
        yy = 1.2 - (i % 2) * 0.36; xx = 8.2 + (i // 2) * 3.3
        ax.add_patch(FancyBboxPatch((xx, yy - 0.12), 0.38, 0.24, boxstyle="round,pad=0,rounding_size=0.05", fc=fc, ec=EDGE, lw=1.0))
        ax.text(xx + 0.5, yy, txt, fontsize=7.4, va="center", family=FONT, color=INK)
    arrow(ax, (8.2, 0.5), (9.0, 0.5), None)
    ax.text(9.1, 0.5, "synchronous call (protocol  <<message type>>)", fontsize=7.4, va="center", family=FONT, color=INK)
    fig.savefig("img/architecture.png", bbox_inches="tight", facecolor="white"); plt.close(fig)


TABLES = {
    "login_identifiers": ["identifier  PK", "user_id  FK → users"],
    "users": ["id  PK", "name · role", "student_id · teacher_id", "password_salt · password_hash"],
    "sdu_connections": ["user_id  PK, FK", "access_token (encrypted)", "expires_at · scope", "updated_at"],
    "sdu_snapshots": ["user_id  PK", "kind  PK", "data_json · updated_at"],
    "teacher_scope": ["teacher_id  PK", "student_id  PK, FK"],
    "students": ["id  PK", "name · cohort", "attendance", "missing_assignments"],
    "curators": ["student_id  PK", "name · email"],
    "risk_alert_log": ["student_id  PK", "risk · sent_at"],
    "interventions": ["id  PK", "student_id  FK", "teacher_id · action_type", "notes · created_at"],
    "grades": ["id  PK", "student_id  FK", "semester · course · code", "credits · components_json"],
    "attendance_log": ["student_id · course_code", "session_date   (PK)", "status: present | absent |", "permitted | pending | upcoming"],
    "risk_history": ["id  PK", "student_id", "risk · predicted_gpa", "created_at"],
    "notifications": ["id  PK", "student_id  FK", "type · title · detail", "read · created_at"],
    "assessment_items": ["id  PK", "grade_id  FK → grades", "name · score · max_score", "weight"],
    "attendance_sessions": ["id  PK", "student_id  FK", "course_code · session_date", "status (present|excused|absent)"],
}
POS = {  # (column, row) on a grid; row 0 = top
    "login_identifiers": (0, 0), "users": (1, 0), "sdu_connections": (2, 0), "sdu_snapshots": (3, 0),
    "teacher_scope": (0, 1), "students": (1, 1), "grades": (1, 2), "assessment_items": (1, 3),
    # everything below carries a student_id column and is drawn inside one labelled group
    "curators": (2, 1), "risk_alert_log": (3, 1), "attendance_log": (2, 2), "risk_history": (3, 2),
    "attendance_sessions": (2, 3), "notifications": (3, 3), "interventions": (2, 4),
}
GROUP = ["curators", "risk_alert_log", "attendance_log", "risk_history", "attendance_sessions", "notifications", "interventions"]


def er():
    BW, BH, gx, gy = 3.3, 1.55, 4.3, 2.5
    W, H = 0.35 + 3 * gx + BW + 0.35, 1.7 + 5 * gy + 0.3
    fig, ax = new(W, H)
    ax.text(0.3, H - 0.4, "Data model: core tables of the StudyMate database (SQLite / PostgreSQL)", fontsize=12.5, fontweight="bold", color=INK, family=FONT)
    xy = {n: (0.35 + c * gx, H - 1.7 - r * gy - BH) for n, (c, r) in POS.items()}

    # group frame for the per-student tables
    gxl, gxr = xy["curators"][0] - 0.3, xy["risk_alert_log"][0] + BW + 0.3
    gyb, gyt = xy["interventions"][1] - 0.3, xy["curators"][1] + BH + 0.6
    ax.add_patch(FancyBboxPatch((gxl, gyb), gxr - gxl, gyt - gyb, boxstyle="round,pad=0,rounding_size=0.15", fc="#faf9ff", ec=EDGE, lw=1.3, ls="--", zorder=0))
    ax.text((gxl + gxr) / 2, gyt - 0.3, "Per-student records (each table has a student_id column)", ha="center", fontsize=8.6, fontweight="bold", color=EDGE, family=FONT)

    for n, (x, y) in xy.items():
        ax.add_patch(FancyBboxPatch((x, y), BW, BH, boxstyle="round,pad=0,rounding_size=0.08", fc=INTERNAL if n != "attendance_log" else "#ffe8c7", ec=EDGE, lw=1.2, zorder=2))
        ax.add_patch(FancyBboxPatch((x, y + BH - 0.42), BW, 0.42, boxstyle="round,pad=0,rounding_size=0.08", fc="#d4cbff", ec=EDGE, lw=1.2, zorder=3))
        ax.text(x + BW / 2, y + BH - 0.21, n, ha="center", va="center", fontsize=9, fontweight="bold", color=INK, family=FONT, zorder=4)
        for i, line in enumerate(TABLES[n]):
            ax.text(x + 0.14, y + BH - 0.68 - i * 0.255, line, ha="left", va="center", fontsize=7.4, color=INK, family=FONT, zorder=4)

    def cx(n): return xy[n][0] + BW / 2
    def cy(n): return xy[n][1] + BH / 2
    def top(n): return xy[n][1] + BH
    def bot(n): return xy[n][1]
    def left(n): return xy[n][0]
    def right(n): return xy[n][0] + BW

    def line(pts, label=None, lpos=None, arrow_end=False):
        for a, b in zip(pts[:-1], pts[1:]):
            ax.plot([a[0], b[0]], [a[1], b[1]], color=EDGE, lw=1.3, zorder=1)
        if arrow_end:
            ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=13, lw=1.3, color=EDGE, zorder=1))
        if label:
            ax.text(*lpos, label, fontsize=7.4, ha="center", va="center", color=INK, family=FONT, bbox=dict(fc="white", ec="none", pad=0.8), zorder=5)

    # authentication cluster
    line([(left("users"), cy("users")), (right("login_identifiers"), cy("login_identifiers"))], "1 : *", ((left("users") + right("login_identifiers")) / 2, cy("users") + 0.22))
    line([(right("users"), cy("users")), (left("sdu_connections"), cy("sdu_connections"))], "1 : 0..1", ((right("users") + left("sdu_connections")) / 2, cy("users") + 0.22))
    yup = top("users") + 0.5
    line([(cx("users") + 0.9, top("users")), (cx("users") + 0.9, yup), (cx("sdu_snapshots"), yup), (cx("sdu_snapshots"), top("sdu_snapshots"))], "1 : *", ((cx("users") + cx("sdu_snapshots")) / 2 + 0.4, yup))
    # users -> students -> grades -> assessment items, students -> teachers
    line([(cx("users"), bot("users")), (cx("users"), top("students"))], "* : 0..1", (cx("users") + 0.55, (bot("users") + top("students")) / 2))
    line([(cx("students"), bot("students")), (cx("grades"), top("grades"))], "1 : *", (cx("students") + 0.35, (bot("students") + top("grades")) / 2))
    line([(cx("grades"), bot("grades")), (cx("assessment_items"), top("assessment_items"))], "1 : *", (cx("grades") + 0.35, (bot("grades") + top("assessment_items")) / 2))
    line([(left("students"), cy("students")), (right("teacher_scope"), cy("teacher_scope"))], "* : *", ((left("students") + right("teacher_scope")) / 2, cy("students") + 0.22))
    # one link from students to the whole group
    line([(right("students"), cy("students")), (gxl, cy("students"))], "1 : *", ((right("students") + gxl) / 2, cy("students") + 0.25), arrow_end=True)
    # legend in the free area under teacher_scope
    lx, ly = 0.35, xy["assessment_items"][1] + 0.0
    ax.add_patch(FancyBboxPatch((lx, ly), 3.3 * 1.0 + 0.4, 3.6, boxstyle="round,pad=0,rounding_size=0.08", fc="white", ec="#9b95b8", lw=1.0))
    ax.text(lx + 0.2, ly + 3.32, "LEGEND", fontsize=8.5, fontweight="bold", family=FONT, color=INK)
    notes = ["1 : * , * : *  relation cardinality", "users.student_id links an account", "to its student record", "", "Orange table: attendance_log keeps", "the 'pending' (Not submitted) status", "of every class hour", "", "Group: the tables inside the dashed", "frame are linked to students.id by", "student_id (some without a constraint)"]
    for i, t in enumerate(notes):
        ax.text(lx + 0.2, ly + 2.95 - i * 0.26, t, fontsize=7.1, family=FONT, color=INK)
    fig.savefig("img/er_diagram.png", bbox_inches="tight", facecolor="white"); plt.close(fig)


def pipeline():
    fig, ax = new(15, 4.6)
    ax.text(0.3, 4.25, "AI pipeline: training once, scoring at every request", fontsize=12.5, fontweight="bold", color=INK, family=FONT)
    box(ax, 0.3, 2.2, 2.6, 1.3, "Public data set", ["UCI Student Performance", "1,044 real students"], fc=EXTERNAL, lsize=7.6)
    box(ax, 3.4, 2.2, 2.6, 1.3, "Mapping", ["grades, trend, absences", "label: final < 60 %"], lsize=7.6)
    box(ax, 6.5, 2.2, 2.6, 1.3, "Training (train.py)", ["RandomForest classifier", "+ GPA regressor"], fc=ML, lsize=7.6)
    box(ax, 9.6, 2.2, 2.6, 1.3, "Model file", ["risk_model.joblib", "metrics.json"], fc=DB, lsize=7.6)
    box(ax, 12.3, 2.2, 2.4, 1.3, "DagsHub / MLflow", ["runs and metrics"], fc=EXTERNAL, lsize=7.6)
    for a, b in ((2.9, 3.4), (6.0, 6.5), (9.1, 9.6), (12.2, 12.3)):
        arrow(ax, (a, 2.85), (b, 2.85))
    box(ax, 0.3, 0.3, 2.6, 1.3, "Student's data", ["synced attendance, grades,", "deadlines (SDU)"], fc=EXTERNAL, lsize=7.4)
    box(ax, 3.4, 0.3, 2.6, 1.3, "Absence rules", ["allowed absences per course", "'Not submitted' = ½ absence"], lsize=7.4)
    box(ax, 6.5, 0.3, 2.6, 1.3, "Model inference", ["risk, GPA, SHAP reasons"], fc=ML, lsize=7.4)
    box(ax, 9.6, 0.3, 2.6, 1.3, "Combine", ["model risk + rule risk", "FX limit forces ≥ 90 %"], lsize=7.4)
    box(ax, 12.3, 0.3, 2.4, 1.3, "Monitoring tab", ["risk, GPA, alerts,", "simulation"], fc=DB, lsize=7.4)
    for a, b in ((2.9, 3.4), (6.0, 6.5), (9.1, 9.6), (12.2, 12.3)):
        arrow(ax, (a, 0.95), (b, 0.95))
    arrow(ax, (10.9, 2.2), (7.8, 1.6), "load", dashed=True, loff=(0.0, 0.0), rad=0.15)
    fig.savefig("img/ml_pipeline.png", bbox_inches="tight", facecolor="white"); plt.close(fig)


if __name__ == "__main__":
    architecture(); er(); pipeline()
    print("figures written to img/")
