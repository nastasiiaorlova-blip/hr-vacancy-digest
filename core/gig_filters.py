"""Фильтры для подработки — отдельные от основного поиска.

Логика здесь обратная. В основном дайджесте мы отбираем узко: вакансия должна
быть про оценку и развитие персонала. Подработку владелец выбирает по
обстоятельствам, поэтому сеть шире: отсекаем только явные «нет», остальное
показываем списком.

Правила собраны из разбора живой выдачи владельцем. Граница тонкая и словами
описывается плохо: расклейщик подходит, а промоутер нет; сборщик заказов
подходит, а работник торгового зала нет. Поэтому список отвергнутого —
не догадка, а прямые ответы, и менять его без спроса нельзя.
"""

import re

from core.models import Vacancy

# Явные «нет». Проверяются по названию, от начала слова.
GIG_STOPWORDS = [
    # продажи и звонки
    "продаж", "продавец", "кассир", "холодн", "телемаркет", "менеджер по работе с клиент",
    # доставка и физический труд
    "курьер", "доставк", "грузчик", "уборщ", "уборк", "клинин", "фасовщ",
    "разнорабоч", "комплектовщ", "мойщ", "дворник", "водител", "сторож",
    # отвергнуто владельцем при разборе выдачи
    "промоутер", "торгов зал", "преподавател", "репетитор", "учител",
    "воспитател", "няня", "сиделк", "охран", "сборщик заявок",
    # рекрутинг — как и в основном поиске
    "рекрутер", "рекрутм", "подбор персонал", "найм",
    # производство и общепит
    "токар", "сварщ", "станк", "повар", "официант", "бариста", "пекар",
]

# Профессиональное ведение мероприятий: владелец готов провести что-то
# несложное, но не выдаёт себя за профи.
PRO_HOST_MARKERS = [
    "тамада", "шоумен", "профессиональн ведущ", "опытный ведущ", "свадьб",
    "ди-джей", "диджей", "аниматор",
]

# Ночные и сменные графики — отвергнуты.
BAD_SCHEDULE_MARKERS = [
    "ночн смен", "ночные смены", "в ночь", "сменный график", "график 2/2",
    "график 1/3", "сутки через", "вахт", "ночная смена",
]

# Признаки частичной занятости. Без них это обычная полная вакансия.
PART_TIME_MARKERS = [
    "подработ", "частичн занятост", "частичная занятость", "неполн день",
    "неполн рабоч", "неполная занятость", "гибкий график", "гибк график",
    "свободный график", "проектн", "разов", "part-time", "парт-тайм",
    "по вечерам", "на выходны", "несколько часов", "почасов",
]

# Адреса, которые владелец считает «рядом с домом». Список задан точно:
# просто «Кузнечиха» и «Советский район» исключены сознательно.
NEAR_HOME_AREAS = ["анкудиновк", "новая кузнечиха", "новой кузнечих", "жк цветы"]

# Названия улиц ищем только рядом со словом «улица»: «медицинская» иначе
# ловит «медицинскую книжку» и «медицинскую консультацию», которых в
# объявлениях полно.
NEAR_HOME_STREETS = ["богородского", "медицинская"]
STREET_PREFIX = re.compile(r"(?:ул|улиц\w*)\.?\s+$", re.IGNORECASE)


def _matches(stem: str, text: str) -> bool:
    """Совпадение основы от начала слова — как в основном фильтре."""
    return all(
        re.search(rf"(?<!\w){re.escape(word)}", text) is not None
        for word in stem.split()
    )


def is_near_home(vacancy: Vacancy) -> bool:
    haystack = f"{vacancy.city or ''} {vacancy.raw_text}".lower()
    if any(marker in haystack for marker in NEAR_HOME_AREAS):
        return True
    for street in NEAR_HOME_STREETS:
        start = 0
        while True:
            idx = haystack.find(street, start)
            if idx < 0:
                break
            if STREET_PREFIX.search(haystack[max(0, idx - 12):idx]):
                return True
            start = idx + 1
    return False


def gig_stopword_filter(vacancies: list[Vacancy]) -> list[Vacancy]:
    result = []
    for v in vacancies:
        title = v.title.lower()
        if any(_matches(stem, title) for stem in GIG_STOPWORDS):
            continue
        if any(_matches(stem, title) for stem in PRO_HOST_MARKERS):
            continue
        result.append(v)
    return result


def schedule_filter(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Отсекает ночные и сменные графики."""
    return [
        v for v in vacancies
        if not any(m in f"{v.title} {v.raw_text}".lower() for m in BAD_SCHEDULE_MARKERS)
    ]


def part_time_filter(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Оставляет только то, что похоже на частичную занятость.

    Заказы с бирж фриланса проходят как есть: они разовые по своей природе."""
    result = []
    for v in vacancies:
        if v.source.startswith("fl:"):
            result.append(v)
            continue
        haystack = f"{v.title} {v.raw_text}".lower()
        if any(marker in haystack for marker in PART_TIME_MARKERS):
            result.append(v)
    return result


def gig_geo_filter(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Удалёнка — откуда угодно. Офлайн — только рядом с домом.

    Это строже, чем в основном поиске: там подходил весь Нижний Новгород,
    здесь только Анкудиновка, Новая Кузнечиха, ЖК Цветы и соседние улицы."""
    return [v for v in vacancies if v.remote or is_near_home(v)]


GIG_STAGES = [
    ("не частичная занятость", part_time_filter),
    ("неподходящее занятие", gig_stopword_filter),
    ("ночной или сменный график", schedule_filter),
    ("далеко от дома", gig_geo_filter),
]


def apply_gig_filters(vacancies: list[Vacancy]) -> list[Vacancy]:
    for _, stage in GIG_STAGES:
        vacancies = stage(vacancies)
    return vacancies
