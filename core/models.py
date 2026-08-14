from dataclasses import dataclass
from datetime import datetime


@dataclass
class Vacancy:
    id: str            # sha1 от source + url (или от source + title + company)
    source: str        # "hh" | "tg:hrhubvacancy" | "site:superjob"
    title: str
    company: str | None
    city: str | None
    remote: bool
    url: str
    salary: str | None
    published_at: datetime | None
    raw_text: str      # для телеграм-каналов — весь текст поста
