"""Парсеры сайтов с вакансиями.

Работают по одному разу в сутки. Каждый сайт — отдельный источник в main.py,
поэтому падение одного не роняет остальные и попадает строкой в дайджест.

SuperJob не поддерживается: публичный API отвечает 403 без ключа приложения,
а страницы поиска отдают капчу. Обходить защиту не будем — см. CLAUDE.md.
"""

import hashlib
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from core.filters import relevance_filter
from core.geo import looks_remote, looks_target_city
from core.models import Vacancy

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = 25
PAUSE_BETWEEN_REQUESTS = 1.5

# Запросы по направлению «оценка и развитие персонала».
SEARCH_QUERIES = [
    "HR",
    "обучение и развитие персонала",
    "оценка персонала",
    "HR бизнес-партнёр",
    "корпоративный университет",
    "управление талантами",
]

# Признаки удалёнки и региона — в core/geo.py, общие для всех источников.

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def _get(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.9"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8", errors="replace")


def _vacancy_id(source: str, url: str) -> str:
    return hashlib.sha1(f"{source}:{url}".encode("utf-8")).hexdigest()


def _detect_remote(*texts: str) -> bool:
    return looks_remote(*texts)


def _detect_city(*texts: str) -> str | None:
    return "Нижний Новгород" if looks_target_city(*texts) else None


# Глобал52 пишет это вместо пустого поля.
EMPTY_FIELD_VALUES = {"не заполнено", "не указано", "-", ""}


def _clean(value: str | None) -> str | None:
    if value is None or value.strip().lower() in EMPTY_FIELD_VALUES:
        return None
    return value.strip()


def _text(node, selector: str) -> str:
    found = node.select_one(selector)
    return found.get_text(" ", strip=True) if found else ""


# ---------------------------------------------------------------- Работа.ру

RABOTA_BASE = "https://nn.rabota.ru"


def fetch_rabota(days: int = 1) -> list[Vacancy]:
    """Нижегородский поддомен Работа.ру, поиск по ключевым словам.

    Дата публикации в карточке не выводится, поэтому `days` здесь не влияет:
    отсев повторов делает хранилище. На первом запуске придёт всё, что сейчас
    висит по запросам, дальше — только новое."""
    return _fetch_rabota_by_queries(SEARCH_QUERIES, "site:rabota", enrich=True)


def _fetch_rabota_by_queries(queries: list[str], source: str,
                            enrich: bool = False) -> list[Vacancy]:
    vacancies: list[Vacancy] = []
    seen_urls: set[str] = set()

    failed_queries = []
    for query in queries:
        url = f"{RABOTA_BASE}/vacancy?query={urllib.parse.quote(query)}"
        try:
            soup = BeautifulSoup(_get(url), "html.parser")
            time.sleep(PAUSE_BETWEEN_REQUESTS)
        except Exception as exc:
            # Таймаут по одному запросу не должен терять остальные.
            print(f"Работа.ру: запрос «{query}» не прошёл: {exc}")
            failed_queries.append(query)
            continue

        for card in soup.select(".vacancy-preview-card__wrapper"):
            link = card.select_one('a[href^="/vacancy/"]')
            if not link:
                continue
            path = link["href"].split("?")[0]
            vacancy_url = urllib.parse.urljoin(RABOTA_BASE, path)
            if vacancy_url in seen_urls:
                continue
            seen_urls.add(vacancy_url)

            title = _text(card, ".vacancy-preview-card__title")
            if not title:
                continue
            description = _text(card, ".vacancy-preview-card__short-description")
            company = _text(card, ".vacancy-preview-card__company-name")
            location = _text(card, ".vacancy-preview-location__address-text")
            salary = _text(card, ".vacancy-preview-card__salary")

            vacancies.append(Vacancy(
                id=_vacancy_id(source, vacancy_url),
                source=source,
                title=title,
                company=_clean(company),
                city=_detect_city(location),
                remote=_detect_remote(location, description, title),
                url=vacancy_url,
                salary=_clean(salary),
                published_at=None,
                # Адрес обязательно в тексте: по нему отбирается подработка
                # рядом с домом, а поле city хранит только город.
                raw_text=f"{title}\n{location}\n{description}",
            ))
    if failed_queries and not vacancies:
        # Ни один запрос не прошёл — это отказ источника, а не пустая выдача.
        raise RuntimeError(f"ни один поисковый запрос не выполнен: {failed_queries}")
    return _enrich_rabota(vacancies) if enrich else vacancies


def _enrich_rabota(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Догружает описание с самой страницы вакансии.

    В карточке списка лежит рекламная аннотация без обязанностей, и фильтр
    по ручному подбору на ней слеп. Догружаем только прошедшие по направлению —
    иначе это шесть десятков лишних запросов в сутки."""
    relevant = {v.url for v in relevance_filter(vacancies)}
    for vacancy in vacancies:
        if vacancy.url not in relevant:
            continue
        try:
            soup = BeautifulSoup(_get(vacancy.url), "html.parser")
            time.sleep(PAUSE_BETWEEN_REQUESTS)
        except Exception:
            continue  # страница недоступна — останемся с аннотацией из карточки
        body = soup.select_one(".vacancy-card") or soup.select_one("main")
        if body:
            vacancy.raw_text = body.get_text("\n", strip=True)
    return vacancies


GIG_QUERIES = [
    # общие
    "подработка", "частичная занятость", "неполный день",
    # офлайн рядом с домом
    "расклейщик", "сборщик заказов",
    # удалённая частичная занятость: без отдельных запросов она попадала
    # в выдачу только случайно, если слово «удалённо» встречалось в тексте
    "удаленная подработка", "оператор удаленно", "модерация контента",
    "разметка данных", "менеджер интернет-магазина", "оператор чата",
    "ассистент удаленно",
    # разовое по профилю
    "квиз", "ведущий мероприятий",
]


def fetch_rabota_gigs(days: int = 1) -> list[Vacancy]:
    """Подработка на Работа.ру — отдельный поток со своими запросами.

    Отбор делают фильтры из core/gig_filters.py: здесь только сбор."""
    return _fetch_rabota_by_queries(GIG_QUERIES, "site:rabota-gig")


# ---------------------------------------------------------------- Глобал52

GLOBAL52_BASE = "https://global52.ru"
GLOBAL52_LIST = f"{GLOBAL52_BASE}/vacancy"
# Страховка от разрастания: список короткий, но окно поиска бывает широким.
GLOBAL52_MAX_DETAILS = 60


def _parse_global52_date(text: str) -> datetime | None:
    """«30 августа» → дата. Год не указан, берём текущий; если получилось
    будущее, значит объявление прошлогоднее."""
    match = re.search(r"(\d{1,2})\s+([а-я]+)", text.lower())
    if not match or match.group(2) not in MONTHS:
        return None
    now = datetime.now(timezone.utc)
    day, month = int(match.group(1)), MONTHS[match.group(2)]
    try:
        parsed = datetime(now.year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
    if parsed > now + timedelta(days=1):
        parsed = parsed.replace(year=now.year - 1)
    return parsed


def _parse_global52_detail(html: str) -> dict:
    """Страница вакансии — набор подписей и значений подряд."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("article, main") or soup.body
    text = body.get_text("\n", strip=True) if body else ""

    # Страница вакансии продолжается лентой соседних объявлений. Без обрезки
    # в raw_text попадает чужой текст, и фильтры видят слова из другой вакансии.
    for boundary in ("Отправить отклик", "Читать далее"):
        cut = text.find(boundary)
        if cut > 0:
            text = text[:cut]
            break

    fields = {}
    lines = text.split("\n")
    for i, line in enumerate(lines[:-1]):
        label = line.rstrip(":").strip().lower()
        if label in ("организация", "район", "зарплата", "график работы", "вакантная должность"):
            fields[label] = lines[i + 1].strip()
    return {"text": text, "fields": fields}


def fetch_global52(days: int = 1) -> list[Vacancy]:
    """Нижегородский бизнес-портал. Объём маленький, поиска по словам нет —
    берём общий список и отбираем по дате обновления."""
    soup = BeautifulSoup(_get(GLOBAL52_LIST), "html.parser")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    candidates: dict[str, datetime | None] = {}
    for block in soup.select(".vacancy-feed__item, .vacancy-feed__main > *"):
        link = block.select_one('a[href*="/vacancy/id/"]')
        if not link:
            continue
        url = urllib.parse.urljoin(GLOBAL52_BASE, link["href"])
        published_at = _parse_global52_date(block.get_text(" ", strip=True).split("Обновлено:")[-1])
        if published_at and published_at < cutoff:
            continue
        candidates.setdefault(url, published_at)

    vacancies = []
    for url, published_at in list(candidates.items())[:GLOBAL52_MAX_DETAILS]:
        detail = _parse_global52_detail(_get(url))
        time.sleep(PAUSE_BETWEEN_REQUESTS)
        fields = detail["fields"]
        title = fields.get("вакантная должность")
        if not title:
            continue
        schedule = fields.get("график работы", "")
        district = fields.get("район", "")

        vacancies.append(Vacancy(
            id=_vacancy_id("site:global52", url),
            source="site:global52",
            title=title,
            company=_clean(fields.get("организация")),
            city=_detect_city(district) or _clean(district),
            remote=_detect_remote(schedule, title),
            url=url,
            salary=_clean(fields.get("зарплата")),
            published_at=published_at,
            raw_text=detail["text"],
        ))
    return vacancies
