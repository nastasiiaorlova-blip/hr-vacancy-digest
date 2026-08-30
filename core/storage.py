import hashlib
import re
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
    first_seen_at TEXT NOT NULL,
    fingerprint TEXT
)
"""

# Сколько символов нормализованного текста берём в отпечаток. Хвост не трогаем:
# перепечатки часто дописывают в конец подпись канала и приглашение подписаться.
FINGERPRINT_WINDOW = 200

_URL = re.compile(r"https?://\S+")
_HASHTAG = re.compile(r"[#@][\w_]+")
_NOT_WORD = re.compile(r"[^0-9a-zа-яё ]+")
_SPACES = re.compile(r"\s+")


def fingerprint(vacancy: Vacancy) -> str:
    """Отпечаток вакансии по содержимому, не зависящий от канала.

    Одна и та же вакансия расходится по нескольким каналам почти дословно,
    отличаясь строкой хештегов сверху и подписью канала снизу. Поэтому текст
    нормализуем, хештеги и ссылки выбрасываем и берём начало.

    По названию сравнивать нельзя: «HR менеджер» — это разные вакансии
    у разных компаний, проверено на живых данных."""
    base = vacancy.raw_text or f"{vacancy.title} {vacancy.company or ''}"
    # Неразрывные пробелы и эмодзи вычистит _NOT_WORD.
    text = base.lower()
    text = _URL.sub(" ", text)
    text = _HASHTAG.sub(" ", text)
    text = _NOT_WORD.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    return hashlib.sha1(text[:FINGERPRINT_WINDOW].encode("utf-8")).hexdigest()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    # Миграция баз, созданных до появления отпечатков. У старых записей
    # он останется пустым — они и так отсеиваются по id.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(seen)")}
    if "fingerprint" not in columns:
        conn.execute("ALTER TABLE seen ADD COLUMN fingerprint TEXT")
        conn.commit()
    return conn


def filter_unseen(vacancies: list[Vacancy], db_path: Path = DB_PATH) -> list[Vacancy]:
    """Оставляет вакансии, которых владелец ещё не видел.

    Отсекает по двум признакам: по id (тот же пост) и по отпечатку содержимого
    (та же вакансия, перепечатанная в другом канале). Дубли внутри одной выдачи
    схлопываются здесь же — иначе перепечатка пришла бы дважды в одном письме."""
    if not vacancies:
        return []
    with closing(_connect(db_path)) as conn:
        ids = [v.id for v in vacancies]
        placeholders = ",".join("?" * len(ids))
        seen_ids = {
            row[0] for row in
            conn.execute(f"SELECT id FROM seen WHERE id IN ({placeholders})", ids)
        }
        prints = [fingerprint(v) for v in vacancies]
        placeholders = ",".join("?" * len(prints))
        seen_prints = {
            row[0] for row in
            conn.execute(
                f"SELECT fingerprint FROM seen WHERE fingerprint IN ({placeholders})",
                prints,
            )
        }

    result = []
    batch_prints: set[str] = set()
    for vacancy, print_ in zip(vacancies, prints):
        if vacancy.id in seen_ids or print_ in seen_prints or print_ in batch_prints:
            continue
        batch_prints.add(print_)
        result.append(vacancy)
    return result


def mark_seen(vacancies: list[Vacancy], db_path: Path = DB_PATH) -> None:
    """Вызывать только после успешной отправки дайджеста —
    иначе непоказанные вакансии будут потеряны навсегда."""
    if not vacancies:
        return
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect(db_path)) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen (id, source, title, url, first_seen_at, fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(v.id, v.source, v.title, v.url, now, fingerprint(v)) for v in vacancies],
        )
        conn.commit()
