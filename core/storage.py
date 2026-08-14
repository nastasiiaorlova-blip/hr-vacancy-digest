import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from core.models import Vacancy

DB_PATH = Path(__file__).resolve().parent.parent / "seen.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
)
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def filter_unseen(vacancies: list[Vacancy], db_path: Path = DB_PATH) -> list[Vacancy]:
    if not vacancies:
        return []
    with closing(_connect(db_path)) as conn:
        ids = [v.id for v in vacancies]
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(f"SELECT id FROM seen WHERE id IN ({placeholders})", ids).fetchall()
        seen_ids = {row[0] for row in rows}
    return [v for v in vacancies if v.id not in seen_ids]


def mark_seen(vacancies: list[Vacancy], db_path: Path = DB_PATH) -> None:
    """Вызывать только после успешной отправки дайджеста —
    иначе непоказанные вакансии будут потеряны навсегда."""
    if not vacancies:
        return
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect(db_path)) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen (id, source, title, url, first_seen_at) VALUES (?, ?, ?, ?, ?)",
            [(v.id, v.source, v.title, v.url, now) for v in vacancies],
        )
        conn.commit()
