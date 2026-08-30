"""Проверка фильтров подработки.

Случаи взяты из разбора живой выдачи владельцем — это прямые ответы,
а не догадки. Граница тонкая: расклейщик подходит, промоутер нет;
сборщик заказов подходит, работник торгового зала нет.

Запуск: python tests/test_gig_filters.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.gig_filters import apply_gig_filters, is_near_home
from core.models import Vacancy

PART_TIME = "Подработка, гибкий график, несколько часов в день. "
NEAR = "г Нижний Новгород, ул Богородского, 8. "
FAR = "г Нижний Новгород, ул Коминтерна, 100. "


def make(title, raw="", remote=False):
    return Vacancy(
        id=title, source="site:rabota-gig", title=title, company=None, city=None,
        remote=remote, url=f"https://example.org/{abs(hash(title)) % 9999}",
        salary=None, published_at=None, raw_text=raw,
    )


failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


# Владелец сказал «присылай»
for title in ["Расклейщик объявлений", "Сборщик заказов", "Менеджер интернет-магазина"]:
    check(apply_gig_filters([make(title, PART_TIME + NEAR)]),
          f"подходящая подработка отсеяна: {title}")

# Владелец сказал «нет»
for title in [
    "Преподаватель английского языка", "Работник торгового зала",
    "Агент-промоутер (подработка)", "Сборщик заявок на подключение интернета",
    "Пеший курьер", "Уборщик/ца", "Фасовщик/фасовщица", "Охранник",
    "Менеджер по продажам", "Специалист по подбору персонала",
    "Оператор колл-центра (удаленно)", "Оператор call-центра",
    "Специалист контакт-центра",
]:
    check(not apply_gig_filters([make(title, PART_TIME + NEAR)]),
          f"отвергнутая подработка прошла: {title}")

# Ночные и сменные графики
check(not apply_gig_filters([make("Оператор", PART_TIME + NEAR + "График 2/2, ночные смены.")]),
      "ночной график прошёл")

# Полная занятость — не подработка
check(not apply_gig_filters([make("Менеджер интернет-магазина", NEAR + "Полный день, оформление по ТК.")]),
      "вакансия с полной занятостью прошла за подработку")

# Гео: офлайн только рядом с домом, удалёнка откуда угодно
check(not apply_gig_filters([make("Сборщик заказов", PART_TIME + FAR)]),
      "офлайн-подработка вдали от дома прошла")
check(apply_gig_filters([make("Менеджер по обработке данных", PART_TIME, remote=True)]),
      "удалённая подработка отсеяна")

# Адреса: тонкие случаи
check(is_near_home(make("x", "ЖК Новая Кузнечиха")), "Новая Кузнечиха не распознана")
check(not is_near_home(make("x", "мкр Кузнечиха-2")),
      "обычная Кузнечиха распознана как дом — владелец её исключил")
check(not is_near_home(make("x", "Нужна медицинская книжка")),
      "«медицинская книжка» принята за улицу Медицинскую")
check(is_near_home(make("x", "г Нижний Новгород, ул. Медицинская, 3")),
      "улица Медицинская не распознана")

# Профессиональное ведение мероприятий — не наш случай
check(not apply_gig_filters([make("Ведущий-тамада на свадьбу", PART_TIME + NEAR)]),
      "профессиональное ведение прошло")

if failures:
    print(f"ПРОВАЛЕНО ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("Все проверки пройдены.")
