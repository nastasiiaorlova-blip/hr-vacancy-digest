"""Проверка фильтров на случаях, найденных на живых данных.

Запуск: python tests/test_filters.py

Каждый случай здесь — не выдумка, а реальный пост из телеграм-каналов,
на котором фильтр однажды ошибся. Правило: нашли ошибку — сначала сюда,
потом правим фильтр.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.filters import apply_filters
from core.models import Vacancy
from core.storage import fingerprint

VACANCY_BODY = (
    "Компания: Пример\nЗадачи:\n— вести подбор и адаптацию\n"
    "Требования:\n— опыт от года\nУсловия:\n— удалённо, оклад по итогам интервью\n"
) * 3


def make(title, raw=None, remote=True, city=None):
    return Vacancy(
        id=title, source="tg:test", title=title, company=None, city=city,
        remote=remote, url=f"https://t.me/test/{abs(hash(title)) % 10000}",
        salary=None, published_at=None, raw_text=VACANCY_BODY if raw is None else raw,
    )


# Целевые вакансии. Часть — примеры из CLAUDE.md, часть найдена в каналах.
SHOULD_PASS = [
    "HR Business Partner",
    "ВАКАНСИЯ: HR DIRECTOR / HEAD OF PEOPLE",
    "Аналитик по оценке персонала",
    "Руководитель отдела персонала (подбор и развитие)",
    "Мастер производственного обучения сотрудников",
    "Специалист корпоративного университета",
    "Ведущий специалист по T&D",
    "Специалист по обучению",
    "Менеджер по обучению и развитию",
    "Тренинг-менеджер",
    "Менеджер по развитию персонала",
]

# Ложные срабатывания, каждое реально попадало в дайджест.
SHOULD_DROP = [
    "(#Удаленка) Требуется #ассистент по развитию соцсетей",
    "(#Удаленка) Требуется #эксперт по обучению ИИ в сфере права в Яндекс",
    "ВАКАНСИЯ: КОММЕРЧЕСКИЙ ДИРЕКТОР / ДИРЕКТОР ПО РАЗВИТИЮ в event/театр",
    "Вакансии нет на hh: Финансовый бизнес-партнёр в банк Точка",
    "Менеджер по продажам",
    "Специалист по подбору персонала",
    "Водитель категории C",
    "Бухгалтер",
]

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


passed = {v.title for v in apply_filters([make(t) for t in SHOULD_PASS])}
for title in SHOULD_PASS:
    check(title in passed, f"потеряна целевая вакансия: {title}")

survived = {v.title for v in apply_filters([make(t) for t in SHOULD_DROP])}
for title in SHOULD_DROP:
    check(title not in survived, f"просочилось лишнее: {title}")

# Резюме соискателя, канал jobs_vacancy_cv публикует их вперемешку с вакансиями.
resume = make(
    "Нахожусь в поиске работы на позицию HRD / Head of HR",
    raw="Нахожусь в поиске работы на позицию HRD. Опыт 10 лет, обязанности вела. " * 8,
)
check(not apply_filters([resume]), "резюме соискателя прошло за вакансию")

# Редакционная статья: слово «ищете» когда-то засчитывалось за маркер вакансии.
article = make(
    "Корпорация или стартап: как тип компании меняет всю вашу карьеру в HR",
    raw="Когда вы ищете новое место, то смотрите на должность, зарплату, индустрию. "
        "А зря, потому что корпорация и стартап — это разная профессия. " * 8,
)
check(not apply_filters([article]), "редакционная статья прошла за вакансию")

# Отпечаток: одна вакансия в двух каналах отличается только строкой хештегов.
body = "HR-специалист\nКомпания: DI AUTO TRADING\nЗадачи:\n— Полный цикл подбора.\n" * 4
check(
    fingerprint(make("HR-специалист", raw="#вакансия_удаленка\n" + body))
    == fingerprint(make("HR-специалист", raw=body)),
    "перепечатка в другом канале не распознана как та же вакансия",
)

# Разные вакансии с одинаковым названием схлопывать нельзя.
check(
    fingerprint(make("HR менеджер", raw="Компания: ЭйчарОсы\nОбязанности:\n— поиск. " * 8))
    != fingerprint(make("HR менеджер", raw="Задачи:\n— ведение полного цикла подбора. " * 8)),
    "две разные вакансии с одним названием ошибочно схлопнулись",
)

# Гео: не удалённая вакансия вне Нижегородской области не нужна.
check(
    not apply_filters([make("HR Business Partner", remote=False, city="Москва")]),
    "вакансия из другого города прошла гео-фильтр",
)
check(
    apply_filters([make("HR Business Partner", remote=False, city="Нижний Новгород")]),
    "вакансия из Нижнего Новгорода не прошла гео-фильтр",
)

if failures:
    print(f"ПРОВАЛЕНО ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("Все проверки пройдены.")
