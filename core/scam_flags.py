"""Признаки сомнительных объявлений о подработке.

Проверяем текст самого объявления, а не отзывы в интернете: сайты отзывов
закрыты для парсинга, а у половины работодателей в подработке вместо компании
стоит имя физлица, и отзывов о них не существует. Ошибочный ярлык
«мошенники» на честной вакансии вреднее, чем его отсутствие.

Поэтому здесь не приговор, а пометка: вакансия показывается с перечнем того,
что настораживает, а решение остаётся за владельцем.

Признаки собраны на живой выдаче Работа.ру, где все три прошедшие фильтры
вакансии оказались одного покроя: ни слова об обязанностях, «без опыта»,
доход втрое выше рынка и предложение «откликнуться, чтобы узнать детали».
"""

import re

from core.models import Vacancy

# Разделы, которые есть в любом настоящем объявлении.
DUTY_MARKERS = [
    "обязанност", "задачи", "требовани", "что делать", "функционал",
    "чем предстоит", "условия работы", "график работы",
]

# Суть скрыта: подробности обещают только после отклика.
HIDDEN_DETAIL_MARKERS = [
    "узнать детали", "узнать подробности", "подробности при", "детали при",
    "подробности в личн", "пишите в личн", "напишите в телеграм", "жмите",
    "ждем вас", "ждём вас", "все расскажем", "всё расскажем", "расскажем на собеседовании",
]

# Обещания вместо описания работы.
HYPE_MARKERS = [
    "стабильный доход", "идеальная подработка", "без опыта", "всему научим",
    "обучение бесплатн", "предусмотрено обучение", "карьерный рост",
    "высокий доход", "доход без ограничений", "потолка дохода нет",
    "финансовая свобода", "пассивный доход", "быстрый старт",
]

# Просьба вложиться — почти всегда обман.
UPFRONT_PAYMENT_MARKERS = [
    "взнос", "предоплат", "оплатить обучение", "платное обучение",
    "купить набор", "стартовый пакет", "вложени",
]

# Организационно-правовые формы: если их нет, работодатель — физлицо.
COMPANY_FORMS = ["ооо", "оао", "зао", "ао ", "пао", "нко", "ано", "гк ", "фгуп", "мбоу"]

MIN_REAL_AD_LENGTH = 400
HIGH_SALARY = 80000

_MONEY = re.compile(r"(\d[\d\s  ]{4,})")


def _max_money(text: str) -> int:
    """Наибольшая сумма, упомянутая в тексте."""
    values = []
    for chunk in _MONEY.findall(text):
        digits = re.sub(r"\D", "", chunk)
        if digits and len(digits) <= 7:
            values.append(int(digits))
    return max(values) if values else 0


def _is_private_person(company: str | None) -> bool:
    if not company:
        return False
    low = company.lower()
    if any(form in low for form in COMPANY_FORMS):
        return False
    # «Любин Владислав Владимирович», «ИП Казарян Армен Джанибекович»
    words = [w for w in re.split(r"[\s.]+", company) if w and w.lower() != "ип"]
    return len(words) >= 2 and all(w[:1].isupper() for w in words)


def scam_reasons(vacancy: Vacancy) -> list[str]:
    """Возвращает список того, что настораживает. Пустой список — вопросов нет."""
    text = vacancy.raw_text or ""
    low = text.lower()
    reasons = []

    if not any(marker in low for marker in DUTY_MARKERS):
        reasons.append("не описаны обязанности")
    if len(text) < MIN_REAL_AD_LENGTH:
        reasons.append("объявление подозрительно короткое")
    if _is_private_person(vacancy.company):
        reasons.append("работодатель — физлицо, а не компания")
    if any(marker in low for marker in HIDDEN_DETAIL_MARKERS):
        reasons.append("подробности обещают только после отклика")
    if any(marker in low for marker in UPFRONT_PAYMENT_MARKERS):
        reasons.append("упоминаются вложения или платное обучение")

    hype = [m for m in HYPE_MARKERS if m in low]
    if len(hype) >= 2:
        reasons.append(f"обещания вместо описания работы: {', '.join(hype[:3])}")

    # Доход, названный в тексте, выше указанного в поле зарплаты.
    if vacancy.salary:
        in_text, in_field = _max_money(text), _max_money(vacancy.salary)
        if in_field and in_text > in_field * 1.15:
            reasons.append(f"в тексте обещают больше, чем в поле зарплаты ({in_text})")

    if ("без опыта" in low or "всему научим" in low) and _max_money(vacancy.salary or "") >= HIGH_SALARY:
        reasons.append("высокий доход без опыта")

    return reasons


def mark_duplicated_employers(vacancies: list[Vacancy]) -> dict[str, list[str]]:
    """Один и тот же наниматель с несколькими почти одинаковыми объявлениями —
    отдельный признак: так размножают шаблонные вакансии по городам."""
    by_company: dict[str, int] = {}
    for v in vacancies:
        if v.company:
            by_company[v.company] = by_company.get(v.company, 0) + 1
    extra: dict[str, list[str]] = {}
    for v in vacancies:
        if v.company and by_company.get(v.company, 0) >= 2:
            extra.setdefault(v.id, []).append(
                f"у этого нанимателя несколько похожих объявлений ({by_company[v.company]})"
            )
    return extra
