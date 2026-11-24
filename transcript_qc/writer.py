"""Write the QC document: a copy of file A where every difference is a tracked change.

The output is built from A's own package. Only word/document.xml is rewritten,
and only the paragraphs that contain a difference, so the embedded fonts, styles
and every unchanged paragraph stay exactly as they were.

Each difference becomes Word revisions:

    delete   -> <w:del> holding the removed runs (text in <w:delText>)
    insert   -> <w:ins> holding a new run
    replace  -> a <w:del> followed by a <w:ins>

Rejecting every revision gives A's text back. Accepting every revision gives B's
text (spacing aside: how many spaces sit between words is formatting, not a
mistake, so spacing is never tracked).
"""

from __future__ import annotations

import copy
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree

from transcript_qc.align import Diff
from transcript_qc.compare import Comparison
from transcript_qc.tokenize import PUNCT, Token

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
DOCUMENT_XML = "word/document.xml"
DEFAULT_AUTHOR = "QC-Bot"

_ATTACHES_LEFT = frozenset({"Po", "Pe", "Pf", "Pd", "Pc"})  # , । ? ! ) ” - stay on the word before
_ATTACHES_RIGHT = frozenset({"Ps", "Pi"})                    # ( [ “ stay on the word after


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


@dataclass(frozen=True, slots=True)
class WriteStats:
    insertions: int
    deletions: int
    changed_paragraphs: int


@dataclass(frozen=True, slots=True)
class _Event:
    pos: int      # character position in the paragraph where it happens
    seq: int      # file order of the difference, to break ties at the same position
    kind: str     # "del" or "ins"
    end: int = 0  # for a deletion: where the removed text stops
    text: str = ""  # for an insertion: the text to add


def _collapse(text: str) -> str:
    """Spacing between words is formatting: runs of whitespace become one space."""
    return " ".join(text.split())


def _b_text(tokens: tuple[Token, ...], b_paragraphs: list[str]) -> str:
    """B's text for a run of tokens, in B's own spelling and punctuation spacing."""
    pieces: list[str] = []
    i = 0
    while i < len(tokens):
        j = i
        while j + 1 < len(tokens) and tokens[j + 1].para == tokens[i].para:
            j += 1
        pieces.append(_collapse(b_paragraphs[tokens[i].para][tokens[i].start : tokens[j].end]))
        i = j + 1
    return " ".join(pieces)


def _groups(tokens: tuple[Token, ...]) -> list[tuple[int, int, int]]:
    """(paragraph, start, end) for each paragraph a run of A's tokens touches."""
    spans: list[tuple[int, int, int]] = []
    for token in tokens:
        if spans and spans[-1][0] == token.para:
            spans[-1] = (token.para, spans[-1][1], token.end)
        else:
            spans.append((token.para, token.start, token.end))
    return spans


def _insert_point(
    group: list[Diff], a_tokens: list[Token], b_tokens: list[Token]
) -> tuple[int, int]:
    """(paragraph, position) where text that exists only in B goes into A.

    group holds the inserts that sit at one spot in A, in B's order. Between two
    words of one line they go right after the earlier word. When the spot is a
    line break in A, it follows B: text on the same B line as the word before it
    goes to the end of that A line; text on the same B line as the word after it
    goes to the start of the next A line.
    """
    k = group[0].a_span[0]
    prev = a_tokens[k - 1] if k > 0 else None
    nxt = a_tokens[k] if k < len(a_tokens) else None
    if prev is not None and nxt is not None and prev.para == nxt.para:
        return prev.para, prev.end
    if prev is None and nxt is None:
        raise ValueError("cannot place an insertion in an empty file")
    if prev is None:
        return nxt.para, nxt.start
    if nxt is None:
        return prev.para, prev.end
    b_start, b_end = group[0].b_span[0], group[-1].b_span[1]
    first, last = group[0].b[0], group[-1].b[-1]
    before = b_tokens[b_start - 1] if b_start > 0 else None
    after = b_tokens[b_end] if b_end < len(b_tokens) else None
    follows_prev = before is not None and before.para == first.para
    precedes_next = after is not None and after.para == last.para
    if precedes_next and not follows_prev:
        return nxt.para, nxt.start
    return prev.para, prev.end


def _needs_space(left: str, right: str) -> bool:
    """True when text ending in `left` and text starting with `right` must be spaced apart.

    Closing punctuation (, । ? !) attaches to the word before it, and an opening
    bracket or quote attaches to the word after it. Words, ♪ and [tags] get a space.
    """
    if left.isspace() or right.isspace():
        return False
    if unicodedata.category(right) in _ATTACHES_LEFT:
        return False
    return unicodedata.category(left) not in _ATTACHES_RIGHT


def _pad(text: str, left: str, right: str) -> str:
    """text with the spaces it needs next to the characters that surround it."""
    if left and _needs_space(left, text[0]):
        text = " " + text
    if right and _needs_space(text[-1], right):
        text += " "
    return text


def _group_texts(group: list[Diff], b_paragraphs: list[str], paragraph: str, pos: int) -> list[str]:
    """The text to insert for each diff of a group, with the spaces the words need.

    The first and last texts are spaced against A's neighbouring characters. Inside
    the group the spacing follows B's own spacing.
    """
    texts = [_b_text(d.b, b_paragraphs) for d in group]
    for i in range(1, len(group)):
        before, after = group[i - 1].b[-1], group[i].b[0]
        if before.para != after.para or after.start > before.end:
            texts[i] = " " + texts[i]
    left = paragraph[pos - 1] if pos > 0 else ""
    right = paragraph[pos] if pos < len(paragraph) else ""
    if group[0].b[0].kind == PUNCT:
        left = ""  # a punctuation mark attaches to what is before it
    texts[0] = _pad(texts[0], left, "") if left else texts[0]
    texts[-1] = _pad(texts[-1], "", right) if right else texts[-1]
    return texts


def _plan(comparison: Comparison) -> dict[int, list[_Event]]:
    """The edits for each paragraph of A, from the differences."""
    events: dict[int, list[_Event]] = {}
    seq = 0
    diffs = comparison.diffs

    def add(para: int, event: _Event) -> None:
        events.setdefault(para, []).append(event)

    i = 0
    while i < len(diffs):
        diff = diffs[i]
        if diff.a:
            groups = _groups(diff.a)
            for para, start, end in groups:
                add(para, _Event(start, seq, "del", end=end))
                seq += 1
            if diff.b:
                para, start, end = groups[-1]
                paragraph = comparison.a_paragraphs[para]
                text = _pad(
                    _b_text(diff.b, comparison.b_paragraphs),
                    paragraph[start - 1] if start > 0 else "",
                    paragraph[end] if end < len(paragraph) else "",
                )
                add(para, _Event(end, seq, "ins", text=text))
                seq += 1
            i += 1
            continue
        j = i + 1  # inserts at the same spot in A belong together
        while j < len(diffs) and not diffs[j].a and diffs[j].a_span[0] == diff.a_span[0]:
            j += 1
        group = diffs[i:j]
        para, pos = _insert_point(group, comparison.a_tokens, comparison.b_tokens)
        texts = _group_texts(group, comparison.b_paragraphs, comparison.a_paragraphs[para], pos)
        for text in texts:
            add(para, _Event(pos, seq, "ins", text=text))
            seq += 1
        i = j
    for items in events.values():
        items.sort(key=lambda e: (e.pos, e.seq))
    return events


class _Ids:
    def __init__(self, author: str, date: str) -> None:
        self.author, self.date, self._next = author, date, 1

    def mark(self, tag: str) -> etree._Element:
        element = etree.Element(_w(tag))
        element.set(_w("id"), str(self._next))
        element.set(_w("author"), self.author)
        element.set(_w("date"), self.date)
        self._next += 1
        return element


def _run(rpr: etree._Element | None, text: str, deleted: bool) -> etree._Element:
    run = etree.Element(_w("r"))
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    node = etree.SubElement(run, _w("delText" if deleted else "t"))
    node.set(f"{{{XML_NS}}}space", "preserve")
    node.text = text
    return run


class _Paragraph:
    """A paragraph's runs, so a character range can be cut out of them."""

    def __init__(self, element: etree._Element) -> None:
        self.element = element
        self.runs = element.findall(_w("r"))
        self.texts = ["".join(t.text or "" for t in r.findall(_w("t"))) for r in self.runs]
        self.rprs = [r.find(_w("rPr")) for r in self.runs]
        self.text = "".join(self.texts)
        unsupported = {
            etree.QName(c).localname for c in element if etree.QName(c).localname not in _KNOWN
        }
        if unsupported:
            raise ValueError(f"paragraph holds content the writer cannot rewrite: {unsupported}")

    def pieces(self, start: int, end: int) -> list[tuple[etree._Element | None, str]]:
        """(run properties, text) for each run overlapping start..end."""
        found, offset = [], 0
        for rpr, text in zip(self.rprs, self.texts, strict=True):
            lo, hi = max(start, offset), min(end, offset + len(text))
            if lo < hi:
                found.append((rpr, text[lo - offset : hi - offset]))
            offset += len(text)
        return found

    def style_at(self, pos: int) -> etree._Element | None:
        """Run properties for text added at pos: those of the character before it."""
        probe = pos - 1 if pos > 0 else 0
        offset = 0
        for rpr, text in zip(self.rprs, self.texts, strict=True):
            if offset <= probe < offset + len(text):
                return rpr
            offset += len(text)
        if self.rprs:
            return self.rprs[-1]
        mark = self.element.find(f"{_w('pPr')}/{_w('rPr')}")
        return mark


_KNOWN = {"pPr", "r", "proofErr"}


def _rewrite(para: _Paragraph, events: list[_Event], ids: _Ids) -> tuple[int, int]:
    """Replace the paragraph's runs with kept text plus tracked changes. Returns (ins, del)."""
    new: list[etree._Element] = []
    cursor = ins_count = del_count = 0

    def keep(end: int) -> None:
        for rpr, text in para.pieces(cursor, end):
            new.append(_run(rpr, text, deleted=False))

    for event in events:
        if event.kind == "del":
            keep(event.pos)
            mark = ids.mark("del")
            for rpr, text in para.pieces(event.pos, event.end):
                mark.append(_run(rpr, text, deleted=True))
            new.append(mark)
            cursor = event.end
            del_count += 1
        else:
            keep(event.pos)
            mark = ids.mark("ins")
            mark.append(_run(para.style_at(event.pos), event.text, deleted=False))
            new.append(mark)
            cursor = max(cursor, event.pos)
            ins_count += 1
    keep(len(para.text))
    for child in list(para.element):
        if child.tag != _w("pPr"):
            para.element.remove(child)
    para.element.extend(new)
    return ins_count, del_count


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_qc(
    a_path: str | Path,
    comparison: Comparison,
    out_path: str | Path,
    author: str = DEFAULT_AUTHOR,
    date: str | None = None,
    append: list[etree._Element] | None = None,
) -> WriteStats:
    """Write A with every difference as a tracked change to out_path.

    append: extra body elements (the summary table) added after A's last paragraph.
    """
    events = _plan(comparison)
    ids = _Ids(author, date or _now())
    with zipfile.ZipFile(a_path) as source:
        root = etree.fromstring(source.read(DOCUMENT_XML))
        body = root.find(_w("body"))
        paragraphs = body.findall(_w("p"))
        insertions = deletions = 0
        for index, items in sorted(events.items()):
            para = _Paragraph(paragraphs[index])
            if para.text != comparison.a_paragraphs[index]:
                raise ValueError(f"paragraph {index + 1} differs between the file and the diff")
            added, removed = _rewrite(para, items, ids)
            insertions += added
            deletions += removed
        if append:
            section = body.find(_w("sectPr"))
            for element in append:
                if section is not None:
                    section.addprevious(element)
                else:
                    body.append(element)
        document = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(out_path, "w") as target:
            for info in source.infolist():
                data = document if info.filename == DOCUMENT_XML else source.read(info.filename)
                entry = zipfile.ZipInfo(info.filename, info.date_time)
                entry.compress_type = info.compress_type
                entry.external_attr = info.external_attr
                target.writestr(entry, data)
    return WriteStats(insertions, deletions, len(events))
