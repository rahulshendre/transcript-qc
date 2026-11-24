"""The summary table added at the end of the QC document.

Four rows by three columns, in the layout of the reviewer's own documents:

    Movie Name: ...      Written By: ...      Episode: ...
    Major Mistakes: 09   Language Mistakes: 12   Punctuation Mistakes: 66
    Cc mistakes: 02      Repeated Mistakes: 04    Minor Mistakes: 04
    Total Mistakes: 97
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from transcript_qc.writer import W_NS, _w

_NAME = re.compile(
    r"^(?:LE\d+\s+)?(?P<code>[A-Za-z]+)[\s_-]+(?:EP[\s_-]*)?(?P<episode>\d+)", re.IGNORECASE
)
_LABEL_COLOUR = "0F4761"


@dataclass(frozen=True, slots=True)
class Details:
    movie: str
    writer: str
    episode: str


def details_from_name(
    file_name: str,
    movies: dict[str, str],
    movie: str | None = None,
    writer: str | None = None,
    episode: str | None = None,
) -> Details:
    """Movie, writer and episode from A's file name, unless given explicitly.

    "LE1 BEK_50_Feltiv.sushila.docx" gives code BEK (looked up in the rules' movie
    names), episode 50 and writer Sushila (the word after the last dot).
    """
    stem = file_name.rsplit(".", 1)[0] if file_name.lower().endswith(".docx") else file_name
    found = _NAME.match(stem)
    code = found["code"] if found else ""
    parsed_writer = stem.rsplit(".", 1)[1].strip().title() if "." in stem else ""
    return Details(
        movie=movie or movies.get(code.upper(), code),
        writer=writer or parsed_writer,
        episode=episode or (found["episode"] if found else ""),
    )


def _cell(width: int, label: str, value: str) -> etree._Element:
    cell = etree.Element(_w("tc"))
    props = etree.SubElement(cell, _w("tcPr"))
    etree.SubElement(props, _w("tcW")).attrib.update({_w("w"): str(width), _w("type"): "dxa"})
    borders = etree.SubElement(props, _w("tcBorders"))
    for side in ("top", "left", "bottom", "right"):
        etree.SubElement(borders, _w(side)).attrib.update(
            {_w("val"): "single", _w("sz"): "4", _w("space"): "0", _w("color"): "000000"}
        )
    paragraph = etree.SubElement(cell, _w("p"))
    for text, colour in ((label, _LABEL_COLOUR), (f" {value}" if value else "", None)):
        if not text:
            continue
        run = etree.SubElement(paragraph, _w("r"))
        rpr = etree.SubElement(run, _w("rPr"))
        etree.SubElement(rpr, _w("rFonts")).attrib.update(
            {_w("ascii"): "Helvetica", _w("hAnsi"): "Helvetica", _w("cs"): "Helvetica"}
        )
        etree.SubElement(rpr, _w("b"))
        if colour:
            etree.SubElement(rpr, _w("color")).set(_w("val"), colour)
        etree.SubElement(rpr, _w("sz")).set(_w("val"), "28")
        node = etree.SubElement(run, _w("t"))
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = text
    return cell


def summary_rows(details: Details, counts: dict[str, int]) -> list[list[tuple[str, str]]]:
    """(label, value) for each cell. Counts are padded to two digits."""
    n = {name: f"{value:02d}" for name, value in counts.items()}
    total = f"{sum(counts.values()):02d}"
    return [
        [("Movie Name:", details.movie), ("Written By:", details.writer),
         ("Episode:", details.episode)],
        [("Major Mistakes:", n["Major"]), ("Language Mistakes:", n["Language"]),
         ("Punctuation Mistakes:", n["Punctuation"])],
        [("Cc mistakes:", n["CC"]), ("Repeated Mistakes:", n["Repeated"]),
         ("Minor Mistakes:", n["Minor"])],
        [("Total Mistakes:", total), ("", ""), ("", "")],
    ]


def summary_elements(details: Details, counts: dict[str, int]) -> list[etree._Element]:
    """The table, then the empty paragraph Word needs after a table at the end of a page."""
    widths = (3332, 2800, 3095)
    table = etree.Element(_w("tbl"))
    props = etree.SubElement(table, _w("tblPr"))
    etree.SubElement(props, _w("tblW")).attrib.update({_w("w"): "0", _w("type"): "auto"})
    grid = etree.SubElement(table, _w("tblGrid"))
    for width in widths:
        etree.SubElement(grid, _w("gridCol")).set(_w("w"), str(width))
    for row in summary_rows(details, counts):
        tr = etree.SubElement(table, _w("tr"))
        trpr = etree.SubElement(tr, _w("trPr"))
        etree.SubElement(trpr, _w("trHeight")).set(_w("val"), "547")
        for width, (label, value) in zip(widths, row, strict=True):
            tr.append(_cell(width, label, value))
    return [table, etree.Element(_w("p"))]


__all__ = ["Details", "details_from_name", "summary_elements", "summary_rows", "W_NS"]
