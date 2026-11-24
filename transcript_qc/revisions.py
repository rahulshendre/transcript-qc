"""Read a QC document back as Word would after Accept All or Reject All.

Used to check the writer: rejecting every revision must give file A's text, and
accepting every revision must give file B's text.
"""

from __future__ import annotations

import unicodedata
import zipfile
from difflib import SequenceMatcher
from pathlib import Path

from lxml import etree

from transcript_qc.writer import DOCUMENT_XML, W_NS


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def revision_texts(docx_path: str | Path) -> tuple[list[str], list[str]]:
    """(text after Reject All, text after Accept All) for every paragraph."""
    with zipfile.ZipFile(docx_path) as package:
        root = etree.fromstring(package.read(DOCUMENT_XML))
    rejected: list[str] = []
    accepted: list[str] = []
    for paragraph in root.find(_w("body")).findall(_w("p")):
        before, after = [], []
        for node in paragraph.iter(_w("t"), _w("delText")):
            text = node.text or ""
            if node.tag == _w("delText"):
                before.append(text)
            elif any(a.tag == _w("ins") for a in node.iterancestors()):
                after.append(text)
            else:
                before.append(text)
                after.append(text)
        rejected.append("".join(before))
        accepted.append("".join(after))
    return rejected, accepted


def comparable(paragraphs: list[str]) -> str:
    """Text with spacing removed and Unicode normalised: what must match across files."""
    return "".join("".join(unicodedata.normalize("NFC", p).split()) for p in paragraphs)


def match_ratio(left: list[str], right: list[str]) -> float:
    """Share of characters that match, spacing aside (1.0 means identical)."""
    a, b = comparable(left), comparable(right)
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=True).ratio()


def round_trip(
    docx_path: str | Path, a_paragraphs: list[str], b_paragraphs: list[str]
) -> tuple[float, float]:
    """(Reject All vs A, Accept All vs B) match ratios for a QC document."""
    rejected, accepted = revision_texts(docx_path)
    return match_ratio(rejected, a_paragraphs), match_ratio(accepted, b_paragraphs)
