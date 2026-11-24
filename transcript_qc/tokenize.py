"""Split transcript lines into tokens for matching.

A token is a word, one punctuation mark, a ♪ song marker, or a whole [sound tag].
Each token remembers where it came from (paragraph index and character span in
the original text) so a later step can write changes back into file A without
touching anything else. Matching uses a normalised copy (Unicode NFC); the
original text is never altered.

Python's regex `\\w` does not match Devanagari vowel signs, so words are found by
elimination instead: a word is a run of characters that are not whitespace,
punctuation, symbols or brackets. That keeps matras, nukta, anusvara and
chandrabindu inside the word they belong to.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

WORD = "word"
PUNCT = "punct"
MUSIC = "music"
TAG = "tag"

_MUSIC_MARKS = frozenset("♪♫")
_TAG = re.compile(r"\[[^\]]*\]")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Token:
    text: str   # exactly as written in the file
    norm: str   # NFC form, used for matching only
    kind: str   # word, punct, music or tag
    para: int   # 0-based paragraph index in its file
    start: int  # character span inside that paragraph's text
    end: int


def _is_separator(ch: str) -> bool:
    """True for characters that end a word: space, punctuation, symbols, brackets."""
    if ch.isspace() or ch in _MUSIC_MARKS or ch in "[]":
        return True
    return unicodedata.category(ch)[0] in "PS"


def _normalise(piece: str, kind: str) -> str:
    """The form used for matching. Spacing inside a [sound tag] is formatting, so it collapses."""
    norm = unicodedata.normalize("NFC", piece)
    if kind == TAG:
        norm = "[" + _SPACES.sub(" ", norm[1:-1]).strip() + "]"
    return norm


def tokenize_line(text: str, para: int) -> list[Token]:
    """Tokens of one paragraph. Whitespace between words is dropped, never a token."""
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "[" and (tag := _TAG.match(text, i)):
            j, kind = tag.end(), TAG
        elif ch in _MUSIC_MARKS:
            j, kind = i + 1, MUSIC
        elif _is_separator(ch):
            j, kind = i + 1, PUNCT
        else:
            j = i + 1
            while j < n and not _is_separator(text[j]):
                j += 1
            kind = WORD
        piece = text[i:j]
        tokens.append(Token(piece, _normalise(piece, kind), kind, para, i, j))
        i = j
    return tokens


def tokenize(paragraphs: list[str]) -> list[Token]:
    """Tokens of a whole file as one stream, so lines can be merged or split freely."""
    stream: list[Token] = []
    for index, text in enumerate(paragraphs):
        stream.extend(tokenize_line(text, index))
    return stream
