import re


def _normalize(text: str) -> str:
    # str.split() splits on every run of Unicode whitespace, no-break spaces included.
    return " ".join(text.casefold().split())


def contains_phrase(text: str, phrase: str) -> bool:
    # Not part of a longer word or number, so "3" matches neither "30" nor "13".
    pattern = rf"(?<!\w){re.escape(_normalize(phrase))}(?!\w)"
    return re.search(pattern, _normalize(text)) is not None
