"""Lay the two transcripts out side by side for review.

A and B break their lines in different places, so rows are not line numbers. A row is a
group of A lines and B lines that share words (or are part of the same difference), so a
line that A splits in two and B keeps whole sits in one row. B lines with no counterpart in
A (a new line) get a row of their own. Each line is cut into segments; a segment that
belongs to a difference carries that difference's index, so the screen can colour it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from transcript_qc.compare import Comparison
from transcript_qc.tokenize import Token


@dataclass(slots=True)
class Segment:
    text: str
    diff: int = -1   # index of the difference this text belongs to, -1 for matching text


@dataclass(slots=True)
class Line:
    para: int        # 1-based paragraph number in its file
    segments: list[Segment]


@dataclass(slots=True)
class Row:
    index: int
    a: list[Line] = field(default_factory=list)
    b: list[Line] = field(default_factory=list)


class _Groups:
    """Union-find over paragraphs, so linked A and B lines end up in one row."""

    def __init__(self) -> None:
        self.parent: dict[tuple[str, int], tuple[str, int]] = {}

    def find(self, node):
        self.parent.setdefault(node, node)
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def link(self, x, y) -> None:
        self.parent[self.find(x)] = self.find(y)


def _walk(comparison: Comparison):
    """Yield (a_token | None, b_token | None, diff index | -1) in file order."""
    a, b = comparison.a_tokens, comparison.b_tokens
    ia = ib = 0
    for index, diff in enumerate(comparison.diffs):
        while ia < diff.a_span[0] and ib < diff.b_span[0]:
            yield a[ia], b[ib], -1
            ia += 1
            ib += 1
        for token in a[diff.a_span[0] : diff.a_span[1]]:
            yield token, None, index
        for token in b[diff.b_span[0] : diff.b_span[1]]:
            yield None, token, index
        ia, ib = diff.a_span[1], diff.b_span[1]
    while ia < len(a) and ib < len(b):
        yield a[ia], b[ib], -1
        ia += 1
        ib += 1


def _segments(text: str, spans: list[tuple[int, int, int]]) -> list[Segment]:
    """Cut a paragraph into plain and highlighted segments. spans are (start, end, diff)."""
    out: list[Segment] = []
    cursor = 0
    for start, end, diff in sorted(spans):
        if start > cursor:
            out.append(Segment(text[cursor:start]))
        if out and out[-1].diff == diff and start <= cursor:
            out[-1].text += text[start:end]
        else:
            out.append(Segment(text[start:end], diff))
        cursor = max(cursor, end)
    if cursor < len(text):
        out.append(Segment(text[cursor:]))
    return out


def _spans(tokens: list[Token], marks: dict[int, int]) -> dict[int, list[tuple[int, int, int]]]:
    """Highlighted character spans per paragraph. A gap between two marked tokens of one
    difference is part of the highlight, so a changed phrase reads as one block."""
    per_para: dict[int, list[tuple[int, int, int]]] = {}
    last: dict[int, tuple[int, int, int]] = {}
    for position, diff in sorted(marks.items()):
        token = tokens[position]
        previous = last.get(token.para)
        adjacent = position >= 1 and marks.get(position - 1) == diff
        if previous and previous[2] == diff and adjacent:
            merged = (previous[0], token.end, diff)
            per_para[token.para][-1] = merged
            last[token.para] = merged
            continue
        span = (token.start, token.end, diff)
        per_para.setdefault(token.para, []).append(span)
        last[token.para] = span
    return per_para


def build_rows(comparison: Comparison) -> tuple[list[Row], dict[int, int]]:
    """Rows for the side-by-side view, and which row each difference sits in."""
    a_marks: dict[int, int] = {}
    b_marks: dict[int, int] = {}
    a_index = {id(t): i for i, t in enumerate(comparison.a_tokens)}
    b_index = {id(t): i for i, t in enumerate(comparison.b_tokens)}
    groups = _Groups()
    order: dict[tuple[str, int], int] = {}
    for step, (a_tok, b_tok, diff) in enumerate(_walk(comparison)):
        if a_tok is not None:
            node = ("A", a_tok.para)
            groups.find(node)
            order.setdefault(node, step)
            if diff >= 0:
                a_marks[a_index[id(a_tok)]] = diff
        if b_tok is not None:
            node = ("B", b_tok.para)
            groups.find(node)
            order.setdefault(node, step)
            if diff >= 0:
                b_marks[b_index[id(b_tok)]] = diff
        if a_tok is not None and b_tok is not None:
            groups.link(("A", a_tok.para), ("B", b_tok.para))
    # tokens in one difference sit together even when a line break falls inside it
    for diff in comparison.diffs:
        nodes = [("A", t.para) for t in diff.a] + [("B", t.para) for t in diff.b]
        for other in nodes[1:]:
            groups.link(nodes[0], other)
    members: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for node in order:
        members.setdefault(groups.find(node), []).append(node)
    def position(nodes):
        """Where a row goes: by its A lines when it has any, else by its B lines."""
        a_steps = [order[n] for n in nodes if n[0] == "A"]
        return min(a_steps) if a_steps else min(order[n] for n in nodes)

    ordered = sorted(members.values(), key=position)
    a_spans = _spans(comparison.a_tokens, a_marks)
    b_spans = _spans(comparison.b_tokens, b_marks)
    rows: list[Row] = []
    row_of_diff: dict[int, int] = {}
    for index, nodes in enumerate(ordered):
        row = Row(index)
        for side, para in sorted(nodes, key=lambda n: (n[0], n[1])):
            if side == "A":
                text = comparison.a_paragraphs[para]
                row.a.append(Line(para + 1, _segments(text, a_spans.get(para, []))))
            else:
                text = comparison.b_paragraphs[para]
                row.b.append(Line(para + 1, _segments(text, b_spans.get(para, []))))
        rows.append(row)
        for line in row.a + row.b:
            for segment in line.segments:
                if segment.diff >= 0:
                    row_of_diff.setdefault(segment.diff, index)
    for diff_index, diff in enumerate(comparison.diffs):
        if diff_index not in row_of_diff:        # an insert or delete with no text on either side
            anchor = ("A", diff.a_line - 1)
            if anchor in order:
                row_of_diff[diff_index] = next(
                    i for i, nodes in enumerate(ordered) if anchor in nodes
                )
    return rows, row_of_diff
