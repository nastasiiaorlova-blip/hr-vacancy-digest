import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from core.models import Vacancy

API_BASE = "https://api.hh.ru"
USER_AGENT = "hr-vacancy-digest-bot/1.0 (nastasiia.orlova@gmail.com)"

# Направление «оценка и развитие персонала».
SEARCH_QUERIES = [
    "оценка персонала",
    "обучение и развитие",
    "T&D",
    "L&D",
    "корпоративный университет",
    "ассессмент",
    "HRBP",
    "HR бизнес-партнёр",
    "развитие персонала",
    "управление талантами",
    "компетенции",
]

# Порядок важен: сначала пробуем найти город, иначе — область целиком.
TARGET_AREA_NAMES = ["Нижний Новгород", "Нижегородская область"]


def _http_get_json(url: str, params: dict) -> dict:
    # С апреля 2026 /vacancies отдаёт 403 без авторизации приложения.
    # Токен генерируется один раз и берётся из личного кабинета dev.hh.ru/admin.
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("HH_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _find_area_id(names: list[str]) -> str:
    tree = _http_get_json(f"{API_BASE}/areas", {})

    def walk(nodes):
        for node in nodes:
            yield node
            yield from walk(node.get("areas") or [])

    by_name = {}
    for node in walk(tree):
        by_name.setdefault(node["name"], node["id"])

    for name in names:
        if name in by_name:
            return by_name[name]
    raise RuntimeError(f"Не найден ни один регион из {names} в /areas")


def _build_text_query() -> str:
    parts = [f'"{q}"' if " " in q else q for q in SEARCH_QUERIES]
    return " OR ".join(parts)


def _vacancy_id(source: str, url: str) -> str:
    return hashlib.sha1(f"{source}:{url}".encode("utf-8")).hexdigest()


def _format_salary(salary: dict | None) -> str | None:
    if not salary:
        return None
    lo, hi, currency = salary.get("from"), salary.get("to"), salary.get("currency") or ""
    if lo and hi:
        return f"{lo}–{hi} {currency}".strip()
    if lo:
        return f"от {lo} {currency}".strip()
    if hi:
        return f"до {hi} {currency}".strip()
    return None


def _to_vacancy(item: dict) -> Vacancy:
    published_at = None
    if item.get("published_at"):
        published_at = datetime.fromisoformat(item["published_at"])

    area = item.get("area") or {}
    schedule = item.get("schedule") or {}

    return Vacancy(
        id=_vacancy_id("hh", item["alternate_url"]),
        source="hh",
        title=item["name"],
        company=(item.get("employer") or {}).get("name"),
        city=area.get("name"),
        remote=schedule.get("id") == "remote",
        url=item["alternate_url"],
        salary=_format_salary(item.get("salary")),
        published_at=published_at,
        raw_text="",
    )


def _search(params: dict) -> list[dict]:
    items = []
    page = 0
    while True:
        data = _http_get_json(f"{API_BASE}/vacancies", {**params, "page": page, "per_page": 100})
        items.extend(data.get("items", []))
        pages = data.get("pages", 1)
        page += 1
        if page >= pages:
            break
    return items


def fetch() -> list[Vacancy]:
    area_id = _find_area_id(TARGET_AREA_NAMES)
    text_query = _build_text_query()

    raw_items = _search({"text": text_query, "area": area_id, "period": 1})
    raw_items += _search({"text": text_query, "schedule": "remote", "period": 1})

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    vacancies = []
    seen_urls = set()
    for item in raw_items:
        vacancy = _to_vacancy(item)
        if vacancy.url in seen_urls:
            continue
        if vacancy.published_at and vacancy.published_at < cutoff:
            continue
        seen_urls.add(vacancy.url)
        vacancies.append(vacancy)
    return vacancies
