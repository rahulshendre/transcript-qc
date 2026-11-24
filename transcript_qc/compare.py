"""Load two transcript files and compare them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from transcript_qc.align import Diff, align
from transcript_qc.reader import read_paragraphs
from transcript_qc.tokenize import Token, tokenize


@dataclass(frozen=True, slots=True)
class Comparison:
    a_paragraphs: list[str]
    b_paragraphs: list[str]
    a_tokens: list[Token]
    b_tokens: list[Token]
    diffs: list[Diff]


def compare_paragraphs(a_paragraphs: list[str], b_paragraphs: list[str]) -> Comparison:
    """Tokenise and align two transcripts given as lists of paragraphs."""
    a_tokens, b_tokens = tokenize(a_paragraphs), tokenize(b_paragraphs)
    return Comparison(a_paragraphs, b_paragraphs, a_tokens, b_tokens, align(a_tokens, b_tokens))


def compare_files(a_path: str | Path, b_path: str | Path) -> Comparison:
    """Read A and B, tokenise both and align them."""
    return compare_paragraphs(read_paragraphs(a_path), read_paragraphs(b_path))
