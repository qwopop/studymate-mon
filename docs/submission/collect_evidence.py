"""Runs every test suite once and stores the real numbers in evidence.json (used by build_docs.py).

    python collect_evidence.py          (set CHROMIUM_PATH if Playwright needs an existing Chromium)
"""
import json, os, re, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"


def run(cmd, cwd, env=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    return r.stdout + r.stderr


def main():
    junit = Path("/tmp/studymate-junit.xml")
    out = run([sys.executable, "-m", "pytest", "-q", "--cov=app", "--cov-report=term", f"--junitxml={junit}"], BACKEND, {"STUDYMATE_SKIP_DOTENV": "1"})
    summary = re.search(r"(\d+) passed(?:, (\d+) failed)?[^\n]* in ([\d.]+)s", out)
    modules = [(m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)) for m in re.finditer(r"^(app[\\/][\w\\/.]+\.py)\s+(\d+)\s+(\d+)\s+(\d+%)", out, re.M)]
    total = re.search(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%", out, re.M)
    cases = []
    for tc in ET.parse(junit).getroot().iter("testcase"):
        status = "failed" if tc.find("failure") is not None or tc.find("error") is not None else ("skipped" if tc.find("skipped") is not None else "passed")
        cases.append({"file": tc.get("classname").split(".")[-1], "name": tc.get("name"), "status": status})
    per_file = {}
    for c in cases:
        per_file[c["file"]] = per_file.get(c["file"], 0) + 1

    unit = run(["npm", "run", "test:unit"], FRONTEND)
    comp = run(["npx", "vitest", "run"], FRONTEND)
    e2e_env = {"CHROMIUM_PATH": os.environ["CHROMIUM_PATH"]} if os.environ.get("CHROMIUM_PATH") else {}
    e2e = run(["npx", "playwright", "test"], FRONTEND, e2e_env)
    num = lambda pattern, text: int(m.group(1)) if (m := re.search(pattern, text)) else None
    evidence = {
        "backend": {"passed": int(summary.group(1)), "failed": int(summary.group(2) or 0), "seconds": float(summary.group(3)),
                    "coverage_total": int(total.group(3)), "statements": int(total.group(1)), "missed": int(total.group(2)),
                    "modules": modules, "per_file": per_file, "cases": cases},
        "frontend": {"unit": num(r"# pass (\d+)", unit), "component": num(r"Tests\s+(\d+) passed", comp), "e2e": num(r"(\d+) passed", e2e)},
    }
    Path(__file__).with_name("evidence.json").write_text(json.dumps(evidence, indent=1))
    print(json.dumps({k: v for k, v in evidence["backend"].items() if k not in ("modules", "cases")}, indent=1), evidence["frontend"])


if __name__ == "__main__":
    main()
