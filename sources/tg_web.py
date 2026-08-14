"""Чтение публичных Telegram-каналов через веб-превью (t.me/s/<канал>).

Не требует api_id, session string и вообще личного аккаунта: превью — обычная
HTML-страница с последними постами. Каналы, у которых владелец отключил превью,
этим способом недоступны — для них и для чатов нужен Telethon (см. CLAUDE.md).
"""

import hashlib
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from core.models import Vacancy

CHANNELS_CONFIG = Path(__file__).resolve().parent.parent / "config" / "channels.yaml"
USER_AGENT = "Mozilla/5.0 (compatible; hr-vacancy-digest/1.0)"

# Превью отдаёт около 20 последних постов за раз. Если канал успел написать больше
# за сутки, добираем предыдущие страницы — но не бесконечно.
MAX_PAGES = 5

REMOTE_MARKERS = [
    "удалён", "удален", "удалёнк", "удаленк", "remote", "из любой точки",
    "дистанционн", "можно из любого города",
]
# Маркер "нн " не добавлять: слишком широкий, ловит случайные совпадения в тексте.
CITY_MARKERS = ["нижний новгород", "нижнем новгороде", "нижнего новгорода", "нижегородск"]

SALARY_PATTERN = re.compile(
    r"(?:от|до|вилка|доход|зарплата|з/п|оклад)[^\n]{0,40}?"
    r"\d[\d\s  ]{2,}(?:\s*(?:до|[–—-])\s*\d[\d\s  ]{2,})?"
    r"[^\n]{0,15}?(?:руб|₽|rub|тыс)",
    re.IGNORECASE,
)


def _load_sources(config_path: Path = CHANNELS_CONFIG) -> list[str]:
    """Возвращает имена каналов и чатов, которые нужно опрашивать."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    names = []
    for block in ("channels", "chats"):
        for entry in config.get(block) or []:
            if entry.get("enabled", True):
                names.append(entry["name"])
    return names


def _fetch_html(channel: str, before: str | None = None) -> str:
    url = f"https://t.me/s/{channel}"
    if before:
        url = f"{url}?before={before}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


# Строки-приветствия и служебные вставки заголовком не являются.
NOISE_LINE = re.compile(
    r"^(всем\s+)?(привет|добрый\s+(день|вечер|утро)|здравствуйте|коллеги|друзья|"
    r"доброе\s+утро|#\w+|реклама|erid)\b",
    re.IGNORECASE,
)


def _message_text(text_el) -> str:
    """Текст поста с переносами только там, где они есть в оригинале.

    get_text("\\n") разрывал бы строку на каждом вложенном теге, и название
    вакансии распадалось на обрывки вроде «службы заботы /» — в постах жирным
    шрифтом и ссылками размечена середина строки."""
    for br in text_el.find_all("br"):
        br.replace_with("\n")
    lines = [line.strip() for line in text_el.get_text("").splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_title(text: str) -> str:
    """Заголовок — первая содержательная строка, без ведущих эмодзи и разделителей.

    Приветствия и хештеги пропускаем: посты часто начинаются с «Всем привет»
    или «#вакансиямечты», а название вакансии идёт следующей строкой."""
    for line in text.splitlines():
        # Шум проверяем до срезания пунктуации, иначе "#вакансия" превратится
        # в обычное слово и пройдёт проверку.
        if NOISE_LINE.match(line.strip()):
            continue
        cleaned = re.sub(r"^[^\w(]+", "", line).strip()
        if len(cleaned) >= 10:
            return cleaned[:200]
    return text.strip()[:200] or "(без заголовка)"


def _extract_salary(text: str) -> str | None:
    match = SALARY_PATTERN.search(text)
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else None


def _detect_geo(text: str) -> tuple[str | None, bool]:
    """Гео из неструктурированного текста: (город, удалёнка)."""
    lowered = text.lower()
    remote = any(marker in lowered for marker in REMOTE_MARKERS)
    city = "Нижний Новгород" if any(m in lowered for m in CITY_MARKERS) else None
    return city, remote


def _parse_page(html: str, channel: str, cutoff: datetime) -> tuple[list[Vacancy], str | None, bool]:
    """Разбирает страницу превью.

    Возвращает вакансии за нужный период, id самого старого поста на странице
    (для пагинации) и признак того, что страница целиком свежее отсечки."""
    soup = BeautifulSoup(html, "html.parser")
    posts = soup.select("div.tgme_widget_message")

    vacancies = []
    oldest_id = None
    all_fresh = bool(posts)

    for post in posts:
        data_post = post.get("data-post") or ""
        msg_id = data_post.split("/")[-1] if "/" in data_post else None
        if msg_id:
            oldest_id = msg_id if oldest_id is None else min(oldest_id, msg_id, key=int)

        text_el = post.select_one("div.tgme_widget_message_text")
        if not text_el:
            continue
        raw_text = _message_text(text_el)
        if not raw_text:
            continue

        time_el = post.select_one("time[datetime]")
        published_at = None
        if time_el:
            published_at = datetime.fromisoformat(time_el["datetime"])

        if published_at and published_at < cutoff:
            all_fresh = False
            continue

        # Ссылка — всегда на сам пост. Первый http-линк в тексте на практике
        # оказывается контактом рекрутёра или рекламной меткой, а не вакансией;
        # в посте же виден весь текст целиком, включая все ссылки.
        url = f"https://t.me/{data_post}" if data_post else f"https://t.me/{channel}"

        city, remote = _detect_geo(raw_text)
        source = f"tg:{channel}"

        vacancies.append(Vacancy(
            id=hashlib.sha1(f"{source}:{url}".encode("utf-8")).hexdigest(),
            source=source,
            title=_extract_title(raw_text),
            company=None,
            city=city,
            remote=remote,
            url=url,
            salary=_extract_salary(raw_text),
            published_at=published_at,
            raw_text=raw_text,
        ))

    return vacancies, oldest_id, all_fresh


def fetch_channel(channel: str, cutoff: datetime) -> list[Vacancy]:
    vacancies: list[Vacancy] = []
    before = None
    for _ in range(MAX_PAGES):
        html = _fetch_html(channel, before)
        page_vacancies, oldest_id, all_fresh = _parse_page(html, channel, cutoff)
        vacancies.extend(page_vacancies)
        # Добираем предыдущую страницу, только если вся текущая уложилась в период:
        # значит, за сутки постов больше, чем поместилось в одну выдачу.
        if not all_fresh or not oldest_id:
            break
        before = oldest_id
    return vacancies


def fetch() -> list[Vacancy]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    vacancies: list[Vacancy] = []
    failed: list[str] = []

    for channel in _load_sources():
        try:
            vacancies.extend(fetch_channel(channel, cutoff))
        except Exception as exc:
            # Падение одного канала не должно ронять весь запуск.
            print(f"канал {channel} недоступен: {exc}")
            failed.append(channel)

    if failed:
        print(f"недоступны каналы: {', '.join(failed)}")
    return vacancies
