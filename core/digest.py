from collections import defaultdict
from datetime import datetime

from core.models import Vacancy
from core.sender import TELEGRAM_MESSAGE_LIMIT

NOTHING_FOUND_TEXT = "За сутки ничего нового не найдено."


def _format_line(vacancy: Vacancy) -> str:
    title = vacancy.title.strip()
    parts = [f'<a href="{vacancy.url}">{title}</a>']
    if vacancy.company:
        parts.append(vacancy.company)
    parts.append("удалённо" if vacancy.remote else (vacancy.city or "—"))
    if vacancy.salary:
        parts.append(vacancy.salary)
    return " · ".join(parts)


def build_digest(vacancies: list[Vacancy], errors: list[str] | None = None,
                 header: str | None = None) -> list[str]:
    """Собирает текст дайджеста. Возвращает список сообщений
    (может быть больше одного, если превышен лимит Telegram)."""
    if not vacancies:
        blocks = [NOTHING_FOUND_TEXT]
    else:
        by_source: dict[str, list[Vacancy]] = defaultdict(list)
        for vacancy in vacancies:
            by_source[vacancy.source].append(vacancy)

        blocks = []
        for source in sorted(by_source):
            group = sorted(
                by_source[source],
                key=lambda v: v.published_at or datetime.min,
                reverse=True,
            )
            lines = [f"<b>{source}</b>"] + [_format_line(v) for v in group]
            blocks.append("\n".join(lines))

    if header:
        blocks.insert(0, f"<b>{header}</b>")

    if errors:
        blocks.append("\n".join(f"⚠️ источник {name} недоступен" for name in errors))

    return _pack_blocks(blocks)


def _pack_blocks(blocks: list[str]) -> list[str]:
    """Упаковывает блоки в сообщения по лимиту Telegram, не разрывая блок пополам."""
    messages: list[str] = []
    current = ""
    for block in blocks:
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= TELEGRAM_MESSAGE_LIMIT:
            current = candidate
        else:
            if current:
                messages.append(current)
            current = block
    if current:
        messages.append(current)
    return messages or [NOTHING_FOUND_TEXT]
