"""Small helpers shared by several modules."""
from __future__ import annotations

import unicodedata


def strip_accents(text: str) -> str:
    """Remove accents: ``"São Paulo"`` -> ``"Sao Paulo"``."""
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def slugify(text: str) -> str:
    """Convert a name to a file-friendly slug: ``"São Paulo"`` -> ``"sao_paulo"``."""
    return "_".join(strip_accents(text).lower().split())
