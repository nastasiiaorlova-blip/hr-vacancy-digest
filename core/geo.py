"""Признаки удалённой работы и целевого региона — общие для всех источников.

Раньше списки были продублированы в каждом адаптере и разъезжались.
Из-за этого «работа из дома» не считалась удалёнкой, и подработка,
которую владелец просил присылать, молча отсеивалась как «далеко от дома».
"""

REMOTE_MARKERS = [
    "удалён", "удален", "удалёнк", "удаленк", "remote", "дистанционн",
    # Частые формулировки в объявлениях о подработке.
    "из дома", "на дому", "из любой точки", "можно из любого города",
    "home office", "хоум-офис", "работа онлайн", "полностью онлайн",
]

CITY_MARKERS = [
    "нижний новгород", "нижнем новгороде", "нижнего новгорода", "нижегородск",
]


def looks_remote(*texts: str) -> bool:
    haystack = " ".join(t for t in texts if t).lower()
    return any(marker in haystack for marker in REMOTE_MARKERS)


def looks_target_city(*texts: str) -> bool:
    haystack = " ".join(t for t in texts if t).lower()
    return any(marker in haystack for marker in CITY_MARKERS)
