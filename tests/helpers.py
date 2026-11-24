"""Build small .docx files for tests and read their revisions back."""

from __future__ import annotations

import zipfile
from pathlib import Path

from docx import Document
from lxml import etree

from transcript_qc.compare import Comparison, compare_files, compare_paragraphs
from transcript_qc.count import Analysis, analyse
from transcript_qc.rules import Rules, load_rules
from transcript_qc.writer import DOCUMENT_XML, W_NS, WriteStats, write_qc

# a paragraph is plain text, or a list of (text, {"bold": True, "italic": True, "font": "..."})
Para = str | list[tuple[str, dict]]


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def build(path: Path, paragraphs: list[Para]) -> Path:
    doc = Document()
    for item in paragraphs:
        paragraph = doc.add_paragraph()
        for text, props in [(item, {})] if isinstance(item, str) else item:
            run = paragraph.add_run(text)
            run.bold = props.get("bold")
            run.italic = props.get("italic")
            if "font" in props:
                run.font.name = props["font"]
    doc.save(path)
    return path


def make_qc(
    tmp_path: Path, a: list[Para], b: list[Para], **options
) -> tuple[Path, Comparison, WriteStats]:
    """Write A and B, compare them, write the QC file. Returns (qc path, comparison, stats)."""
    a_path = build(tmp_path / "a.docx", a)
    b_path = build(tmp_path / "b.docx", b)
    comparison = compare_files(a_path, b_path)
    out = tmp_path / "qc.docx"
    stats = write_qc(a_path, comparison, out, **options)
    return out, comparison, stats


def document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as package:
        return etree.fromstring(package.read(DOCUMENT_XML))


def revisions(path: Path) -> list[etree._Element]:
    """Every w:ins and w:del element, in document order."""
    root = document_root(path)
    return [e for e in root.iter() if e.tag in (w("ins"), w("del"))]


def revision_text(element: etree._Element) -> str:
    return "".join(t.text or "" for t in element.iter(w("t"), w("delText")))


def analysis(a: list[str], b: list[str], rules: Rules | str | None = "strict") -> Analysis:
    """Compare two lists of lines and count the mistakes. Strict rules unless told otherwise."""
    if rules is None or isinstance(rules, str):
        rules = load_rules(rules)
    return analyse(compare_paragraphs(a, b), rules)


def only(result: Analysis):
    """The single counted mistake of an analysis."""
    (mistake,) = result.counted
    return mistake
