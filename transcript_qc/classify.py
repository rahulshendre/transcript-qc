"""Decide which category a hunk belongs to.

Every rule has an id. Rules are tried in the order given in rules.yaml and the
first one that matches decides the category. The id and a plain-words reason are
kept with the mistake, so every count can be traced back to the rule behind it.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from transcript_qc.hunks import Hunk
from transcript_qc.rules import Rules
from transcript_qc.tokenize import MUSIC, PUNCT, TAG, WORD

_ZERO_WIDTH = {"‌", "‍"}


@dataclass(frozen=True, slots=True)
class Verdict:
    category: str
    rule_id: str
    note: str
    confidence: float  # 1.0 = a rule that cannot be argued with; lower = near a threshold


def compact(text: str) -> str:
    """Text with all spacing removed: the form used to compare words."""
    return "".join(text.split())


_VOWEL_LENGTH = str.maketrans({"ई": "इ", "ऊ": "उ", "ॠ": "ऋ"})


def skeleton(text: str, ignore_marks: frozenset[str], fold_vowel_length: bool = True) -> str:
    """The letters of a word without its matras, nukta, anusvara and chandrabindu.

    Long and short independent vowels (उ and ऊ) are treated as the same letter, since the
    difference between them is a matter of vowel length, not a different word.
    """
    letters = "".join(
        c for c in text
        if unicodedata.category(c) not in ignore_marks and c not in _ZERO_WIDTH
    )
    return letters.translate(_VOWEL_LENGTH) if fold_vowel_length else letters


def distance(a: str, b: str) -> float:
    """Normalised edit distance between two words: 0 identical, 1 nothing in common."""
    if not a and not b:
        return 0.0
    return Levenshtein.normalized_distance(a, b)


def pair_words(a: list[str], b: list[str]) -> list[tuple[str | None, str | None]]:
    """Line up the words of A and B: matched pairs, and None where a word has no partner.

    Chooses the pairing with the least total distance; a word with no partner costs 1,
    the same as the worst possible pair.
    """
    n, m = len(a), len(b)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = float(i)
    for j in range(1, m + 1):
        cost[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(
                cost[i - 1][j - 1] + distance(a[i - 1], b[j - 1]),
                cost[i - 1][j] + 1.0,
                cost[i][j - 1] + 1.0,
            )
    pairs: list[tuple[str | None, str | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + distance(a[i - 1], b[j - 1]):
            pairs.append((a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + 1.0:
            pairs.append((a[i - 1], None))
            i -= 1
        else:
            pairs.append((None, b[j - 1]))
            j -= 1
    pairs.reverse()
    return pairs


class _Ctx:
    """What the rules look at for one hunk."""

    def __init__(self, hunk: Hunk, rules: Rules) -> None:
        self.hunk, self.rules = hunk, rules
        self.a_norm = " ".join(t.norm for t in hunk.a)
        self.b_norm = " ".join(t.norm for t in hunk.b)
        self.a = compact(self.a_norm)
        self.b = compact(self.b_norm)
        self.a_text, self.b_text = hunk.a_text, hunk.b_text
        a_words = [t.norm for t in hunk.a if t.kind == WORD]
        b_words = [t.norm for t in hunk.b if t.kind == WORD]
        self.pairs = pair_words(a_words, b_words) if a_words and b_words else []
        self.has_gap = any(x is None or y is None for x, y in self.pairs)
        # the largest distance among words judged on distance alone: a pair that is a known
        # variant or the same letters is not a distance case, so it should not set the note
        self.worst = max(
            (distance(x, y) for x, y in self.pairs
             if x and y and self.pair_kind(x, y) in ("similar", "different")),
            default=0.0,
        )

    def pair_kind(self, x: str, y: str) -> str:
        """How two paired words relate: variant, marks (same letters), similar, or different."""
        if (x, y) in self.rules.variants:
            return "variant"
        if x and y and (skeleton(x, self.rules.ignore_marks, self.rules.fold_vowel_length)
                        == skeleton(y, self.rules.ignore_marks, self.rules.fold_vowel_length)):
            return "marks"
        if distance(x, y) <= self.rules.language_max_distance:
            return "similar"
        return "different"

    def kinds_of_pairs(self) -> set[str]:
        return {self.pair_kind(x, y) for x, y in self.pairs if x is not None and y is not None}

    def kinds(self, wanted: str) -> bool:
        return any(t.kind == wanted for t in self.hunk.tokens)

    def shown(self) -> str:
        return f"{self.a_text or '-'} vs {self.b_text or '-'}"


def _which_side(ctx: _Ctx, what: str) -> str:
    """Plain words for what is different: missing in A, extra in A, or changed."""
    if ctx.hunk.a and not ctx.hunk.b:
        return f"{what} in A is not in the reference: {ctx.a_text}"
    if ctx.hunk.b and not ctx.hunk.a:
        return f"{what} missing in A: {ctx.b_text}"
    return f"{what} differs: {ctx.shown()}"


def _cc_tag(ctx: _Ctx) -> Verdict | None:
    if ctx.kinds(TAG):
        return Verdict("CC", "CC_TAG", _which_side(ctx, "sound tag"), 1.0)
    return None


def _cc_music(ctx: _Ctx) -> Verdict | None:
    if ctx.kinds(MUSIC):
        return Verdict("CC", "CC_MUSIC", _which_side(ctx, "song marker"), 1.0)
    return None


def _punct_only(ctx: _Ctx) -> Verdict | None:
    tokens = ctx.hunk.tokens
    if tokens and all(t.kind == PUNCT for t in tokens):
        return Verdict("Punctuation", "PUNCT_ONLY", _which_side(ctx, "punctuation"), 1.0)
    return None


def _minor_space(ctx: _Ctx) -> Verdict | None:
    if ctx.a and ctx.a == ctx.b:
        note = f"a space splits or joins a word: {ctx.shown()}"
        return Verdict("Minor", "MINOR_SPACE", note, 1.0)
    return None


def _word_hunk(ctx: _Ctx) -> bool:
    """True for a hunk of words with a partner for every word, so word-by-word rules apply."""
    return bool(ctx.pairs) and not ctx.has_gap


def _lang_variant(ctx: _Ctx) -> Verdict | None:
    if _word_hunk(ctx) and ctx.kinds_of_pairs() == {"variant"}:
        return Verdict("Language", "LANG_VARIANT", f"known spelling variant: {ctx.shown()}", 0.95)
    return None


def _lang_marks(ctx: _Ctx) -> Verdict | None:
    if _word_hunk(ctx) and ctx.kinds_of_pairs() <= {"variant", "marks"}:
        note = f"same letters, different matras: {ctx.shown()}"
        return Verdict("Language", "LANG_MARKS", note, 0.9)
    return None


def _major_added(ctx: _Ctx) -> Verdict | None:
    if ctx.hunk.a and not ctx.hunk.b:
        return Verdict("Major", "MAJOR_ADDED", f"extra word in A: {ctx.a_text}", 0.85)
    if ctx.hunk.b and not ctx.hunk.a:
        return Verdict("Major", "MAJOR_ADDED", f"word missing in A: {ctx.b_text}", 0.85)
    if ctx.has_gap:
        return Verdict("Major", "MAJOR_ADDED", f"a word added or removed: {ctx.shown()}", 0.8)
    return None


def _confidence(d: float, limit: float) -> float:
    """Sure far from the threshold, unsure right next to it."""
    return round(0.5 + min(abs(d - limit), 0.25) * 2, 2)


def _lang_similar(ctx: _Ctx) -> Verdict | None:
    if _word_hunk(ctx) and "different" not in ctx.kinds_of_pairs():
        note = f"spelled close to the reference (distance {ctx.worst:.2f}): {ctx.shown()}"
        sure = _confidence(ctx.worst, ctx.rules.language_max_distance)
        return Verdict("Language", "LANG_SIMILAR", note, sure)
    return None


def _major_different(ctx: _Ctx) -> Verdict | None:
    note = f"different word (distance {ctx.worst:.2f}): {ctx.shown()}"
    sure = _confidence(ctx.worst, ctx.rules.language_max_distance)
    return Verdict("Major", "MAJOR_DIFFERENT", note, sure)


_RULES: dict[str, Callable[[_Ctx], Verdict | None]] = {
    "CC_TAG": _cc_tag,
    "CC_MUSIC": _cc_music,
    "PUNCT_ONLY": _punct_only,
    "MINOR_SPACE": _minor_space,
    "LANG_VARIANT": _lang_variant,
    "LANG_MARKS": _lang_marks,
    "MAJOR_ADDED": _major_added,
    "LANG_SIMILAR": _lang_similar,
    "MAJOR_DIFFERENT": _major_different,
}
RULE_IDS = frozenset(_RULES)


def classify(hunk: Hunk, rules: Rules) -> Verdict:
    """The category of a hunk, from the first rule in the rules' order that matches."""
    ctx = _Ctx(hunk, rules)
    for rule_id in rules.order:
        verdict = _RULES[rule_id](ctx)
        if verdict is not None:
            return verdict
    return Verdict("Major", "NO_RULE", f"no rule matched: {ctx.shown()}", 0.5)
