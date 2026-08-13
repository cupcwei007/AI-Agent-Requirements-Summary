"""Deterministic text normalization, tokenization, and chunking."""

from __future__ import annotations

import re
import unicodedata

_WORD = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).lower().split())


def tokens(value: str) -> set[str]:
    """Return Latin words and overlapping CJK bigrams for mixed-language search."""
    normalized = normalize(value)
    result = set(_WORD.findall(normalized))
    cjk = "".join(_CJK.findall(normalized))
    result.update(cjk[index : index + 2] for index in range(len(cjk) - 1))
    if len(cjk) == 1:
        result.add(cjk)
    return result


def chunk_text(value: str, *, max_chars: int = 900, overlap: int = 120) -> list[str]:
    """Split on paragraphs first, then bounded windows while retaining context."""
    if max_chars < 100 or overlap < 0 or overlap >= max_chars:
        raise ValueError("max_chars must be >= 100 and 0 <= overlap < max_chars")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", value) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            step = max_chars - overlap
            chunks.extend(
                paragraph[start : start + max_chars]
                for start in range(0, len(paragraph), step)
                if paragraph[start : start + max_chars]
            )
        elif not current:
            current = paragraph
        elif len(current) + 2 + len(paragraph) <= max_chars:
            current = f"{current}\n\n{paragraph}"
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks
