"""Read a transcript .docx into its paragraphs.

Both inputs hold one subtitle line per paragraph, with blank paragraphs between
lines. The blanks are kept so a paragraph's position in the list is its position
in the file: that index is how every difference maps back to a line of file A.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document


def read_paragraphs(path: str | Path) -> list[str]:
    """Text of every paragraph in the file, blank ones included, in order."""
    return [paragraph.text for paragraph in Document(str(path)).paragraphs]
