"""Line up two token streams and list where they differ.

The whole file is aligned as one stream, not line by line, because the two
transcripts break lines in different places: one line in A can be two in B.

Alignment runs in two passes. Aligning every token at once lets a comma in one
line pair up with a comma two lines away, which turns a simple spelling change
(कहां to कहाँ) into a delete plus an insert. So the first pass aligns only the
content tokens (words and [sound tags]). The second pass compares the small
gaps of punctuation and ♪ markers between matched content tokens. Changed
content and changed punctuation therefore always come out as separate
differences, even when they touch.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from transcript_qc.tokenize import TAG, WORD, Token

_CONTENT = (WORD, TAG)


@dataclass(frozen=True, slots=True)
class Diff:
    """One run of changed tokens: replace, delete (only in A) or insert (only in B).

    a_span and b_span are token index ranges (start, end) into each file's token
    list. An empty range marks where an insert or delete sits.
    """

    tag: str
    a: tuple[Token, ...]
    b: tuple[Token, ...]
    a_span: tuple[int, int]
    b_span: tuple[int, int]
    a_line: int  # 1-based paragraph of file A (for an insert: the line it goes into)
    b_line: int  # 1-based paragraph of file B

    @property
    def a_text(self) -> str:
        return " ".join(t.text for t in self.a)

    @property
    def b_text(self) -> str:
        return " ".join(t.text for t in self.b)


def _line_at(tokens: list[Token], start: int, end: int) -> int:
    """1-based paragraph for a token range; an empty range borrows its left neighbour."""
    if not tokens:
        return 1
    if end > start:
        return tokens[start].para + 1
    return tokens[max(min(start, len(tokens)) - 1, 0)].para + 1


class _Side:
    """One file's tokens split into content tokens and the gaps between them."""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.content = [i for i, t in enumerate(tokens) if t.kind in _CONTENT]
        # cpos[m] is where content token m sits; the last entry marks the end of the file.
        self.cpos = [*self.content, len(tokens)]
        self.norms = [tokens[i].norm for i in self.content]
        self.used: set[int] = set()

    def gap(self, m: int) -> tuple[int, int]:
        """Token range of the gap before content token m (m == len(content): the tail)."""
        start = self.cpos[m - 1] + 1 if m > 0 else 0
        return start, self.cpos[m]

    def take_gap(self, m: int) -> tuple[int, int]:
        """The gap's range the first time it is asked for, an empty range after that."""
        start, end = self.gap(m)
        if m in self.used:
            return end, end
        self.used.add(m)
        return start, end

    def run(self, m1: int, m2: int) -> tuple[int, int]:
        """Token range covering content tokens m1..m2-1 and the punctuation between them."""
        if m2 > m1:
            self.used.update(range(m1 + 1, m2))
            return self.cpos[m1], self.cpos[m2 - 1] + 1
        return self.cpos[m1], self.cpos[m1]


def _make(a: _Side, b: _Side, tag: str, a_span: tuple[int, int], b_span: tuple[int, int]) -> Diff:
    return Diff(
        tag,
        tuple(a.tokens[a_span[0] : a_span[1]]),
        tuple(b.tokens[b_span[0] : b_span[1]]),
        a_span,
        b_span,
        _line_at(a.tokens, *a_span),
        _line_at(b.tokens, *b_span),
    )


def _gap_diffs(
    a: _Side, b: _Side, a_span: tuple[int, int], b_span: tuple[int, int]
) -> list[Diff]:
    """Differences between two gaps of punctuation and ♪ markers."""
    a_gap, b_gap = a.tokens[a_span[0] : a_span[1]], b.tokens[b_span[0] : b_span[1]]
    if [t.norm for t in a_gap] == [t.norm for t in b_gap]:
        return []
    matcher = SequenceMatcher(
        None, [t.norm for t in a_gap], [t.norm for t in b_gap], autojunk=False
    )
    found = []
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag != "equal":
            found.append(
                _make(
                    a, b, tag,
                    (a_span[0] + a1, a_span[0] + a2),
                    (b_span[0] + b1, b_span[0] + b2),
                )
            )
    return found


def align(a_tokens: list[Token], b_tokens: list[Token]) -> list[Diff]:
    """Every difference between the two streams, in file order."""
    a, b = _Side(a_tokens), _Side(b_tokens)
    matcher = SequenceMatcher(None, a.norms, b.norms, autojunk=False)
    diffs: list[Diff] = []
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        diffs += _gap_diffs(a, b, a.take_gap(a1), b.take_gap(b1))
        if tag == "equal":
            for step in range(1, a2 - a1):
                diffs += _gap_diffs(a, b, a.take_gap(a1 + step), b.take_gap(b1 + step))
        else:
            diffs.append(_make(a, b, tag, a.run(a1, a2), b.run(b1, b2)))
    diffs += _gap_diffs(a, b, a.take_gap(len(a.content)), b.take_gap(len(b.content)))
    return diffs
