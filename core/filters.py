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


def _load_stopwords() -> list[str]:
    if not STOPWORDS_PATH.exists():
        return []
    stems = []
    for line in STOPWORDS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            stems.append(line.lower())
    return stems


def _stem_matches(stem: str, title: str) -> bool:
    """Стем может состоять из нескольких слов (например "корпоративн университет") —
    тогда каждое слово должно встретиться в названии, не обязательно подряд."""
    return all(word in title for word in stem.split())


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


def apply_filters(vacancies: list[Vacancy]) -> list[Vacancy]:
    return stopword_filter(geo_filter(vacancies))
