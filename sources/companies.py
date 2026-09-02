"""Карьерные сайты компаний, которые владелец назвал интересными.

Все три отдают список вакансий прямо в HTML, поэтому парсер общий:
берём страницу HR-направления, вытаскиваем ссылки на вакансии и текст рядом.
Город и формат работы у всех вписаны в текст ссылки, поэтому гео определяется
обычными правилами из core/geo.py.

Проверены и не подключены:
- ВТБ (rabota-vtb.ru) — в HTML только навигация, список рисуется скриптами;
- Альфа-банк (job.alfabank.ru) — то же самое, плюс сертификат российского УЦ,
  которого нет в наборе доверенных: 637 КБ страницы при 1000 символах текста.

Объём маленький — единицы вакансий на компанию, — поэтому пагинации нет.
"""

import hashlib
import re
import time
import urllib.parse

from bs4 import BeautifulSoup

from core.geo import looks_remote, looks_target_city
from core.models import Vacancy
from sources.sites import PAUSE_BETWEEN_REQUESTS, _get

# url — страница HR-направления, link — образец ссылки на вакансию.
COMPANIES = [
    {
        "source": "company:avito",
        "url": "https://career.avito.com/vacancies/hr/",
        "base": "https://career.avito.com",
        "link": 'a[href*="/vacancies/hr/"]',
    },
    {
        "source": "company:severstal",
        "url": "https://career.severstal.com/vacancies/?direction=office&tag%5B%5D=office__hr",
        "base": "https://career.severstal.com",
        "link": 'a[href*="/vacancies/"]',
    },
    {
        "source": "company:vk",
        "url": "https://team.vk.company/vacancy/",
        "base": "https://team.vk.company",
        "link": 'a[href*="/vacancy/"]',
    },
]

MIN_TITLE_LENGTH = 12
MAX_TITLE_LENGTH = 160

# Служебные ссылки, которые выглядят как вакансии.
SERVICE_LINKS = ["смотреть вакансии", "ещё вакансии", "еще вакансии", "все вакансии",
                 "вакансии", "показать ещё", "фильтры"]


def _looks_like_title(text: str) -> bool:
    low = text.lower().strip()
    if not (MIN_TITLE_LENGTH < len(text) < MAX_TITLE_LENGTH):
        return False
    return not any(low.startswith(s) or low == s for s in SERVICE_LINKS)


def _fetch_company(company: dict) -> list[Vacancy]:
    soup = BeautifulSoup(_get(company["url"]), "html.parser")
    seen: dict[str, str] = {}
    for link in soup.select(company["link"]):
        text = link.get_text(" ", strip=True)
        href = link.get("href") or ""
        if not href or not _looks_like_title(text):
            continue
        seen.setdefault(urllib.parse.urljoin(company["base"], href), text)

    vacancies = []
    for url, text in seen.items():
        # Город и формат работы дописаны в конец текста ссылки:
        # «Координатор по обучению и развитию Москва, Гибрид».
        vacancies.append(Vacancy(
            id=hashlib.sha1(f"{company['source']}:{url}".encode("utf-8")).hexdigest(),
            source=company["source"],
            title=re.sub(r"\s+", " ", text)[:MAX_TITLE_LENGTH],
            company=company["source"].split(":")[1],
            city="Нижний Новгород" if looks_target_city(text) else None,
            remote=looks_remote(text),
            url=url,
            salary=None,
            published_at=None,
            raw_text=text,
        ))
    return vacancies


def fetch(days: int = 1) -> list[Vacancy]:
    """days не используется: дат публикации на этих страницах нет,
    от повторов защищает хранилище."""
    vacancies: list[Vacancy] = []
    failed = []
    for company in COMPANIES:
        try:
            vacancies.extend(_fetch_company(company))
            time.sleep(PAUSE_BETWEEN_REQUESTS)
        except Exception as exc:
            print(f"карьерный сайт {company['source']} недоступен: {exc}")
            failed.append(company["source"])
    if failed and not vacancies:
        raise RuntimeError(f"ни один карьерный сайт не прочитан: {failed}")
    return vacancies
