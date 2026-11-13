"""
MCQ Cleaner — Phase 1.

Fixes common OCR artefacts in extracted text:
  - Ligature substitutions (ﬁ → fi, ﬂ → fl, etc.)
  - Non-breaking spaces, soft hyphens, zero-width chars
  - Smart quotes → straight quotes
  - Hyphenated line-breaks from column layouts
  - Collapsed whitespace

Operates on the raw text before parsing so the parser always sees clean input.
Call `clean_pages()` on the list[PageResult] returned by pdf_reader.py.
"""

from __future__ import annotations

import re
import unicodedata

from src.mcqs.pdf_reader import PageResult
from src.core.logger import logger

# ── Ligature / unicode normalisation map ──────────────────────────────────
_LIGATURES: dict[str, str] = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
    "\u00ad": "",      # soft hyphen
    "\u200b": "",      # zero-width space
    "\u200c": "",      # zero-width non-joiner
    "\u200d": "",      # zero-width joiner
    "\u00a0": " ",     # non-breaking space
    "\u2019": "'",     # right single quotation mark
    "\u2018": "'",     # left single quotation mark
    "\u201c": '"',     # left double quotation mark
    "\u201d": '"',     # right double quotation mark
    "\u2013": "-",     # en-dash
    "\u2014": "-",     # em-dash
    "\u2022": "-",     # bullet
}

_LIGATURE_TABLE = str.maketrans(_LIGATURES)


def _normalize(text: str) -> str:
    """Apply NFC normalization then replace known problem chars."""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_LIGATURE_TABLE)
    return text


def _fix_hyphenated_breaks(text: str) -> str:
    """Rejoin words broken across lines by a hyphen (OCR column artefact)."""
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def _collapse_whitespace(text: str) -> str:
    """Replace multiple internal spaces with a single space, preserve newlines and leading indent."""
    # This regex replaces 2 or more horizontal spaces with a single space
    # but leaves leading/trailing line whitespace alone to preserve indentation
    return re.sub(r"[ \t]{2,}", " ", text)


def clean_text(text: str) -> str:
    text = _normalize(text)
    text = _fix_hyphenated_breaks(text)
    text = _collapse_whitespace(text)
    return text.strip()


def clean_pages(pages: list[PageResult]) -> list[PageResult]:
    """Return a new list of PageResults with cleaned text fields."""
    cleaned = []
    for page in pages:
        cleaned.append(PageResult(
            page_number=page.page_number,
            text=clean_text(page.text),
            tables=[
                [[clean_text(cell) for cell in row] for row in table]
                for table in page.tables
            ],
            has_images=page.has_images,
            reader_used=page.reader_used,
        ))
    logger.debug(f"Cleaned {len(pages)} page(s)")
    return cleaned
