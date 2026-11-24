"""Turn differences into the units that get counted.

A difference that mixes a word change with a punctuation, ♪ or sound-tag change is
split in two, so each can be counted on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from transcript_qc.align import Diff
from transcript_qc.tokenize import WORD, Token


@dataclass(frozen=True, slots=True)
class Hunk:
    diff_index: int  # which difference it came from
    kind: str        # "word" (only words) or "other" (punctuation, ♪, [tags])
    a: tuple[Token, ...]
    b: tuple[Token, ...]
    a_line: int
    b_line: int
    b_span: tuple[int, int]  # where it sits in file B's tokens (empty range for a deletion)

    @property
    def tokens(self) -> tuple[Token, ...]:
        return self.a + self.b

    @property
    def a_text(self) -> str:
        return " ".join(" ".join(t.text.split()) for t in self.a)

    @property
    def b_text(self) -> str:
        return " ".join(" ".join(t.text.split()) for t in self.b)

    @property
    def key(self) -> tuple[str, str]:
        """(A text, B text) in matching form: the pair a repeat is recognised by."""
        return " ".join(t.norm for t in self.a), " ".join(t.norm for t in self.b)


def split_diff(diff: Diff, index: int) -> list[Hunk]:
    """One hunk, or two when words are mixed with punctuation, ♪ or a sound tag."""
    words_a = tuple(t for t in diff.a if t.kind == WORD)
    words_b = tuple(t for t in diff.b if t.kind == WORD)
    other_a = tuple(t for t in diff.a if t.kind != WORD)
    other_b = tuple(t for t in diff.b if t.kind != WORD)
    has_words = bool(words_a or words_b)
    has_other = bool(other_a or other_b)
    if has_words and has_other and [t.norm for t in other_a] == [t.norm for t in other_b]:
        # the punctuation inside a changed run is the same on both sides: only the words changed
        return [Hunk(index, "word", words_a, words_b, diff.a_line, diff.b_line, diff.b_span)]
    if has_words and has_other:
        return [
            Hunk(index, "word", words_a, words_b, diff.a_line, diff.b_line, diff.b_span),
            Hunk(index, "other", other_a, other_b, diff.a_line, diff.b_line, diff.b_span),
        ]
    kind = "word" if has_words else "other"
    return [Hunk(index, kind, diff.a, diff.b, diff.a_line, diff.b_line, diff.b_span)]


def split_all(diffs: list[Diff]) -> list[Hunk]:
    return [hunk for i, diff in enumerate(diffs) for hunk in split_diff(diff, i)]
