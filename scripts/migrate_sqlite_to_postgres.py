"""Copy an existing SQLite database into Postgres (Neon).

    DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require \
    python scripts/migrate_sqlite_to_postgres.py backend/data/student_monitoring.db

The backend creates the Postgres schema itself on first start; run it once (or call this script,
which starts it) before copying. Rows that already exist are skipped, so the script can be re-run.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def main(path: str) -> int:
    if not os.getenv("DATABASE_URL"):
        print("Set DATABASE_URL to the Neon connection string first.")
        return 1
    from app import db as dbmod
    from app.repository import SQLiteRepository
    from app import monitoring_store

    repo = SQLiteRepository()           # creates the schema in Postgres
    monitoring_store.ensure(repo)
    source = sqlite3.connect(path)
    source.row_factory = sqlite3.Row
    tables = [r[0] for r in source.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    total = 0
    with repo.connect() as target:
        for table in tables:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            columns = rows[0].keys()
            sql = f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})"
            for row in rows:
                target.execute(sql, tuple(row))
            total += len(rows)
            print(f"{table}: {len(rows)} rows")
        for table in sorted(dbmod.SERIAL_TABLES | {"risk_history"}):   # keep new ids after the copied ones
            target.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                           f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)")
        target.commit()
    print(f"Done: {total} rows copied to {dbmod.describe()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "backend/data/student_monitoring.db"))
