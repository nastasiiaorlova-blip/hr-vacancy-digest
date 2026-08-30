"""FL.ru — биржа фриланса, разовые заказы.

Поиск по ключевому слову через адрес не работает: параметр игнорируется,
выдача остаётся общей. Поэтому берём разделы, где встречается подходящее,
и отбираем по словам уже у себя.

Заказы здесь по своей природе разовые, поэтому проверку на частичную
занятость они не проходят — она их пропускает по источнику.
"""

import hashlib
import re
import time
import urllib.parse

from bs4 import BeautifulSoup

from core.models import Vacancy
from sources.sites import PAUSE_BETWEEN_REQUESTS, _get

BASE = "https://www.fl.ru"

# Разделы, где попадается интересное владельцу.
CATEGORIES = {
    "teksty": "Тексты",
    "konsalting": "Аутсорсинг и консалтинг",
    "audio-video-photo": "Аудио/Видео/Фото",
}

# Сильные слова: сами по себе означают подходящий заказ.
STRONG_KEYWORDS = [
    "квиз", "викторин", "интеллектуальн игр", "ассессмент", "деловая игра",
    "деловые игры", "тренинг", "подкаст", "оценка персонала", "hr-",
    "корпоративное обучение", "корпоративный университет",
]

# Слабые: значат что-то только рядом с контекстом. Без этого разделения
# «сценарий» ловил сценарии для ютуба про World of Warcraft, а «обучение» —
# помощь в магистратуре по экономике.
WEAK_KEYWORDS = ["сценари", "обучени", "ведущ", "модерац", "вопрос", "игра", "игры"]

CONTEXT_KEYWORDS = [
    "квиз", "викторин", "тренинг", "мероприят", "персонал", "сотрудник",
    "корпоратив", "команд", "hr", "бизнес-игр", "подкаст",
]

PROJECT_LINK = re.compile(r"/projects/(\d{5,})")


def _looks_relevant(title: str) -> bool:
    low = title.lower()
    if any(k in low for k in STRONG_KEYWORDS):
        return True
    weak = any(k in low for k in WEAK_KEYWORDS)
    context = any(k in low for k in CONTEXT_KEYWORDS)
    return weak and context


def fetch(days: int = 1) -> list[Vacancy]:
    """days не используется: на странице раздела дат нет, от повторов
    защищает хранилище."""
    vacancies: list[Vacancy] = []
    seen_ids: set[str] = set()
    failed = []

    for slug, human_name in CATEGORIES.items():
        url = f"{BASE}/projects/category/{slug}/"
        try:
            soup = BeautifulSoup(_get(url), "html.parser")
            time.sleep(PAUSE_BETWEEN_REQUESTS)
        except Exception as exc:
            print(f"FL.ru: раздел «{human_name}» не прочитан: {exc}")
            failed.append(human_name)
            continue

        titles: dict[str, tuple[str, str]] = {}
        for link in soup.select("a[href]"):
            match = PROJECT_LINK.search(link.get("href") or "")
            text = link.get_text(" ", strip=True)
            if not match or len(text) < 12 or text == "Откликнуться":
                continue
            titles.setdefault(match.group(1), (text, urllib.parse.urljoin(BASE, link["href"])))

        for project_id, (title, project_url) in titles.items():
            if project_id in seen_ids or not _looks_relevant(title):
                continue
            seen_ids.add(project_id)
            source = f"fl:{slug}"
            vacancies.append(Vacancy(
                id=hashlib.sha1(f"{source}:{project_url}".encode("utf-8")).hexdigest(),
                source=source,
                title=title,
                company=None,
                city=None,
                remote=True,  # биржа фриланса — работа удалённая по определению
                url=project_url,
                salary=None,
                published_at=None,
                raw_text=title,
            ))

    if failed and not vacancies:
        raise RuntimeError(f"ни один раздел не прочитан: {failed}")
    return vacancies
