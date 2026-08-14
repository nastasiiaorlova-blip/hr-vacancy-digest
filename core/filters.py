import re
from pathlib import Path

from core.models import Vacancy

STOPWORDS_PATH = Path(__file__).resolve().parent.parent / "config" / "stopwords.txt"

TARGET_CITY_MARKERS = ["нижний новгород", "нижегородск"]

# Вайтлист-исключение: стоп-слово не отсеивает вакансию, если в названии
# одновременно есть один из этих целевых маркеров.
WHITELIST_STEMS = [
    "оценк", "развити", "обучени", "t&d", "l&d", "talent", "hrbp", "бизнес-партнёр",
    "корпоративн университет", "ассессмент", "assessment", "компетенц", "адаптаци",
    "кадровый резерв", "performance",
]

# Фильтр релевантности: вакансия должна относиться к направлению.
# Без него в дайджест попадает любая удалённая работа — Go-разработчики,
# тестировщики, SMM, — потому что стоп-слова их не ловят, а гео пропускает.
RELEVANT_STEMS = WHITELIST_STEMS + [
    "hr", "эйчар", "персонал", "human resources", "people partner", "c&b",
    "обучени", "тренер", "методист", "наставни", "карьерн", "мотиваци",
    "корпоративн культур", "внутренн коммуникац", "директор по персоналу",
]


def _load_stopwords() -> list[str]:
    if not STOPWORDS_PATH.exists():
        return []
    stems = []
    for line in STOPWORDS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            stems.append(line.lower())
    return stems


def _stem_matches(stem: str, text: str) -> bool:
    """Стем — основа слова, совпадение считается от начала слова.

    Без привязки к границе слова короткие латинские основы дают ложные срабатывания:
    "hr" находится внутри "through", "l&d" — внутри ссылок.

    Стем может состоять из нескольких слов (например "корпоративн университет") —
    тогда каждое слово должно встретиться в тексте, не обязательно подряд."""
    return all(
        re.search(rf"(?<!\w){re.escape(word)}", text) is not None
        for word in stem.split()
    )


# Маркеры того, что сообщение вообще является вакансией.
# Изначально задумывались для чатов, но каналы тоже несут рекламу, промо-посты
# и личную переписку, поэтому предфильтр применяется ко всем текстовым источникам.
VACANCY_MARKERS = [
    "вакансия", "#вакансия", "ищем", "в команду", "открыта позиция", "открыт конкурс",
    "зарплата", "вилка", "откликнуться", "резюме на", "требуется", "приглашаем",
    "ищет", "в поиске", "обязанности", "требования", "условия",
]

# Короткие сообщения — почти всегда реплики в обсуждении, а не вакансия.
MIN_VACANCY_LENGTH = 200


def vacancy_marker_filter(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Отсеивает сообщения, не похожие на вакансию.

    Применяется только к источникам с неструктурированным текстом (Telegram):
    у вакансий с сайтов и из API raw_text пустой, их пропускаем как есть."""
    result = []
    for v in vacancies:
        if not v.raw_text:
            result.append(v)
            continue
        if len(v.raw_text) < MIN_VACANCY_LENGTH:
            continue
        lowered = v.raw_text.lower()
        if any(marker in lowered for marker in VACANCY_MARKERS):
            result.append(v)
    return result


def geo_filter(vacancies: list[Vacancy]) -> list[Vacancy]:
    result = []
    for v in vacancies:
        if v.remote:
            result.append(v)
            continue
        city = (v.city or "").lower()
        if any(marker in city for marker in TARGET_CITY_MARKERS):
            result.append(v)
    return result


def stopword_filter(vacancies: list[Vacancy], stopwords: list[str] | None = None) -> list[Vacancy]:
    stopwords = _load_stopwords() if stopwords is None else stopwords
    result = []
    for v in vacancies:
        title = v.title.lower()
        hit_stopword = any(_stem_matches(stem, title) for stem in stopwords)
        if not hit_stopword or any(_stem_matches(stem, title) for stem in WHITELIST_STEMS):
            result.append(v)
    return result


def relevance_filter(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Оставляет только вакансии по направлению «оценка и развитие персонала».

    Маркер ищется строго по названию, как и стоп-слова. По всему тексту поста
    искать нельзя: почти любая вакансия упоминает «обучение» и «мотивацию»
    в разделе условий, и тогда фильтр пропускает вообще всё."""
    result = []
    for v in vacancies:
        title = v.title.lower()
        if any(_stem_matches(stem, title) for stem in RELEVANT_STEMS):
            result.append(v)
    return result


def apply_filters(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Порядок: похоже ли на вакансию → релевантность → гео → стоп-слова → вайтлист."""
    return stopword_filter(geo_filter(relevance_filter(vacancy_marker_filter(vacancies))))
