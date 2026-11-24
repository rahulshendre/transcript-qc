"""Read a transcript .docx into its paragraphs.

Both inputs hold one subtitle line per paragraph, with blank paragraphs between
lines. The blanks are kept so a paragraph's position in the list is its position
in the file: that index is how every difference maps back to a line of file A.

Only body paragraphs are read. A file the tool would read wrongly is refused
(not a .docx, or tracked changes still in it), and one it would read only in part
(tables, text boxes) is reported, so no text goes missing without a word.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document

_TRACKED = ".//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo"


class InputError(ValueError):
    """A transcript file cannot be used. The message says what to do about it."""


def _open(path: str | Path):
    try:
        return Document(str(path))
    except Exception as error:  # not a zip, or a zip that is not a Word document
        name = Path(path).name
        raise InputError(f"{name} is not a Word .docx file, or it is damaged.") from error


def read_paragraphs(path: str | Path) -> list[str]:
    """Text of every paragraph in the file, blank ones included, in order."""
    document = _open(path)
    if document.element.body.xpath(_TRACKED):
        raise InputError(
            f"{Path(path).name} has tracked changes. "
            "Accept or reject them in Word, then run the tool again."
        )
    return [paragraph.text for paragraph in document.paragraphs]


def docx_warnings(path: str | Path) -> list[str]:
    """Text in the file that the tool does not compare."""
    body = _open(path).element.body
    name = Path(path).name
    found = []
    for xpath, noun in ((".//w:tbl", "table"), (".//w:txbxContent", "text box")):
        count = len(body.xpath(xpath))
        if count:
            plural = "s" if count > 1 else ""
            found.append(f"{name} has {count} {noun}{plural}. Text inside {noun}s is not compared.")
    return found
