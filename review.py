"""Прогон для настройки фильтров.

Ничего не отправляет и ничего не записывает в seen.db — только показывает,
что прошло и что каждый фильтр отсеял, с указанием шага.

Смотреть нужно прежде всего на отбракованное: ложные срабатывания видно сразу
в дайджесте, а потерянные вакансии не видно вообще никак.

    python review.py            за последние сутки
    python review.py 14         за последние 14 дней
    python review.py 7 --all    показать все отсеянные, а не только спорные
"""

import sys

from core import filters
from core.models import Vacancy
from sources import tg_web

# Шаги в том же порядке, в каком их применяет apply_filters.
STAGES = [
    ("не похоже на вакансию", filters.vacancy_marker_filter),
    ("резюме соискателя", filters.resume_filter),
    ("не по направлению", filters.relevance_filter),
    ("не тот регион", filters.geo_filter),
    ("стоп-слово в названии", filters.stopword_filter),
]


def classify(vacancies: list[Vacancy]) -> tuple[list[Vacancy], dict[str, list[Vacancy]]]:
    """Прогоняет вакансии по шагам, запоминая, на каком каждая отсеялась."""
    survivors = vacancies
    dropped: dict[str, list[Vacancy]] = {}
    for name, stage in STAGES:
        after = stage(survivors)
        kept_ids = {v.id for v in after}
        dropped[name] = [v for v in survivors if v.id not in kept_ids]
        survivors = after
    return survivors, dropped


def main() -> None:
    days = 1
    show_all = "--all" in sys.argv
    for arg in sys.argv[1:]:
        if arg.isdigit():
            days = int(arg)

    print(f"Собираю посты за последние {days} сут...\n")
    vacancies = tg_web.fetch(days)
    survivors, dropped = classify(vacancies)

    print(f"{'ВСЕГО ПОСТОВ':<28} {len(vacancies)}")
    for name, _ in STAGES:
        print(f"  отсеяно «{name}»{'':<{max(0, 8 - len(name))}} {len(dropped[name])}")
    print(f"{'ПРОШЛО ВСЁ':<28} {len(survivors)}\n")

    print("=" * 70)
    print("ПРОШЛИ ФИЛЬТРЫ")
    print("=" * 70)
    for v in survivors:
        print(f"  [{v.source}] {v.title[:90]}")
        print(f"       {v.url}")

    # Отсеянное на раннем шаге — почти всегда очевидный мусор, его не показываем
    # без --all. Интересны те, что дошли до содержательных фильтров.
    interesting = ["резюме соискателя", "не по направлению", "не тот регион", "стоп-слово в названии"]
    shown = STAGES if show_all else [(n, s) for n, s in STAGES if n in interesting]

    for name, _ in shown:
        items = dropped[name]
        if not items:
            continue
        print()
        print("=" * 70)
        print(f"ОТСЕЯНО: {name} ({len(items)})")
        print("=" * 70)
        for v in items:
            print(f"  [{v.source}] {v.title[:90]}")


if __name__ == "__main__":
    main()
