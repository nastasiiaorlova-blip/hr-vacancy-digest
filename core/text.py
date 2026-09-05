"""Сравнение по основам слов, а не по буквам.

Русские слова склоняются, и сравнение подстрокой требует перечислять все формы:
«опыт в подборе» не совпадало с «опыт работы в подборе», «проведение
собеседований» — с «проводить собеседования», «подбор персонала» — с «поиска
персонала». Каждый такой промах приходилось чинить дописыванием ещё одной
строки в список, и список рос бесконечно.

Здесь текст и маркер приводятся к основам, поэтому формы совпадают сами.
Между словами маркера допускается несколько чужих слов: в объявлениях пишут
«опыт работы в подборе», а не «опыт в подборе».
"""

import re
from functools import lru_cache

import snowballstemmer

_STEMMER = snowballstemmer.stemmer("russian")
_WORD = re.compile(r"[0-9a-zа-яё&]+", re.IGNORECASE)

# Служебные слова выбрасываем: они ничего не значат, но ломают совпадение фразы.
FILLER = {
    "в", "во", "на", "по", "для", "с", "со", "и", "от", "до", "к", "ко",
    "о", "об", "при", "за", "из", "у", "же", "ли", "бы", "а", "но", "или",
    "то", "как", "что", "не", "the", "of", "and", "in", "for",
}

# Сколько чужих слов допускается между словами маркера.
MAX_GAP = 2


@lru_cache(maxsize=100_000)
def stem(word: str) -> str:
    """Основа слова, применяем стеммер до устойчивого результата.

    Одного прохода мало: Snowball даёт «опытом» -> «опыт», но «опыт» -> «оп»,
    и одно и то же слово перестаёт совпадать само с собой. Повтор до
    неподвижной точки приводит все формы к общей основе."""
    for _ in range(5):
        stemmed = _STEMMER.stemWord(word)
        if stemmed == word:
            return word
        word = stemmed
    return word


def stems(text: str) -> list[str]:
    """Основы слов текста, без служебных слов."""
    return [stem(w) for w in _WORD.findall(text.lower()) if w not in FILLER]


def phrase_matches(marker: str, text_stems: list[str]) -> bool:
    """Есть ли маркер в тексте: слова по порядку, с зазором не больше MAX_GAP.

    Порядок важен — иначе «при наборе» распалось бы на отдельные слова
    и совпадало почти с любым текстом."""
    needle = stems(marker)
    if not needle:
        return False

    for start in range(len(text_stems)):
        if text_stems[start] != needle[0]:
            continue
        position = start
        for word in needle[1:]:
            found = False
            for offset in range(1, MAX_GAP + 2):
                if position + offset < len(text_stems) and text_stems[position + offset] == word:
                    position += offset
                    found = True
                    break
            if not found:
                break
        else:
            return True
    return False
