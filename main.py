import os
import sys

from core.digest import build_digest
from core.filters import apply_filters
from core.models import Vacancy
from core.sender import send_digest
from core.storage import filter_unseen, mark_seen
from sources import tg_web


def _load_dotenv(path: str = ".env") -> None:
    """Локальный запуск: подхватить секреты из .env, если он есть.
    В GitHub Actions секреты приходят как настоящие env vars, файла нет — функция no-op."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# hh.ru закрыл соискательский API 15.12.2025 — адаптер оставлен на случай,
# если доступ вернут, но из конвейера исключён: иначе дайджест каждый день
# сообщал бы о недоступном источнике.
SOURCES = [("telegram", tg_web.fetch)]


def collect(days: int) -> tuple[list[Vacancy], list[str]]:
    vacancies: list[Vacancy] = []
    errors: list[str] = []
    for name, fetch in SOURCES:
        try:
            vacancies.extend(fetch(days))
        except Exception as exc:
            print(f"источник {name} недоступен: {exc}", file=sys.stderr)
            errors.append(name)
    return vacancies, errors


def main() -> None:
    _load_dotenv()
    # DIGEST_DAYS нужен для первого запуска: даёт посмотреть выдачу за две
    # недели вместо суток. В обычном режиме переменная не задаётся.
    days = int(os.environ.get("DIGEST_DAYS", "1"))
    vacancies, errors = collect(days)
    vacancies = apply_filters(vacancies)
    vacancies = filter_unseen(vacancies)
    messages = build_digest(vacancies, errors)
    send_digest(messages)
    mark_seen(vacancies)


if __name__ == "__main__":
    main()
