from __future__ import annotations

import re
import unicodedata


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", "", normalized)


def has_meaningful_text(value: str) -> bool:
    return any(character.isalnum() for character in value)
