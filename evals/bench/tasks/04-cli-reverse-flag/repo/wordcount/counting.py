import re
from collections import Counter

WORD = re.compile(r"[a-z']+")


def count_words(text: str) -> Counter:
    return Counter(WORD.findall(text.lower()))
