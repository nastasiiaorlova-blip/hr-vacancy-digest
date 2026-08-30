import os
import sys

from core.digest import build_digest
from core.filters import apply_filters
from core.models import Vacancy
from core.sender import send_digest
from core.storage import filter_unseen, mark_seen
from core.gig_filters import apply_gig_filters
from sources import fl, sites, tg_web


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
SOURCES = [
    ("telegram", tg_web.fetch),
    ("site:rabota", sites.fetch_rabota),
    ("site:global52", sites.fetch_global52),
]

# Подработка — отдельный поток: свои источники, свои фильтры, своё сообщение.
# Смешивать нельзя: там отбор узкий по направлению, здесь широкий с отсевом
# явных «нет».
GIG_SOURCES = [
    ("подработка:rabota", sites.fetch_rabota_gigs),
    ("подработка:fl", fl.fetch),
    ("подработка:global52", sites.fetch_global52),
]


def collect(days: int, sources=None) -> tuple[list[Vacancy], list[str]]:
    vacancies: list[Vacancy] = []
    errors: list[str] = []
    for name, fetch in (SOURCES if sources is None else sources):
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
    # `or` вместо значения по умолчанию: при запуске по расписанию GitHub
    # подставляет в inputs пустую строку, и int("") уронил бы весь прогон.
    days = int(os.environ.get("DIGEST_DAYS") or 1)
    vacancies, errors = collect(days)
    vacancies = apply_filters(vacancies)
    vacancies = filter_unseen(vacancies)
    send_digest(build_digest(vacancies, errors))
    mark_seen(vacancies)

    # Второе сообщение — подработка. Отправляется даже пустым: молчание
    # неотличимо от поломки.
    gigs, gig_errors = collect(days, GIG_SOURCES)
    gigs = apply_gig_filters(gigs)
    gigs = filter_unseen(gigs)
    send_digest(build_digest(gigs, gig_errors, header="Подработка"))
    mark_seen(gigs)


if __name__ == "__main__":
    main()
