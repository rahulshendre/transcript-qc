"""Classify every hunk and apply the counting rules.

Counting rules, in order:
 1. One hunk, one mistake (the aligner already merges a run of changed words).
 2. Spacing between words and line breaks are never mistakes (the tokenizer drops them).
 3. A pair (A text -> B text) seen more than once is one Repeated mistake; its other
    occurrences stay in the document but add nothing to any count.
 4. One category per mistake, the first rule that matches; a hunk mixing a word change
    with punctuation, ♪ or a sound tag is split in two (see hunks.py).
 5. The total is the sum of the six counts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from transcript_qc.classify import classify
from transcript_qc.compare import Comparison
from transcript_qc.hunks import Hunk, split_all
from transcript_qc.rules import CATEGORIES, Rules, repeat_threshold


@dataclass(slots=True)
class Mistake:
    index: int
    line_no: int          # 1-based paragraph in file A
    b_line: int           # 1-based paragraph in file B
    a_text: str
    b_text: str
    category: str         # what it counts as (Repeated for a repeated pair)
    base_category: str    # what it would count as on its own
    rule_id: str
    note: str
    confidence: float
    status: str = "counted"        # counted, repeat (a later copy of a repeated pair) or ignored
    ignored_because: str = ""      # for an ignored difference: why it adds nothing
    repeat_of: int | None = None   # index of the mistake that stands for this repeat
    occurrences: int = 1           # for a Repeated mistake: how many times the pair appears
    lines: list[int] = field(default_factory=list)  # for a Repeated mistake: every A line
    hunk: Hunk | None = None


@dataclass(slots=True)
class Analysis:
    mistakes: list[Mistake]
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def counted(self) -> list[Mistake]:
        return [m for m in self.mistakes if m.status == "counted"]

    @property
    def ignored(self) -> list[Mistake]:
        """Differences the engine saw but did not count, with the reason on each."""
        return [m for m in self.mistakes if m.status == "ignored"]

    @property
    def repeats(self) -> list[Mistake]:
        """Later copies of a repeated pair: shown and tracked, but they add nothing."""
        return [m for m in self.mistakes if m.status == "repeat"]


def _repeat_note(first: Mistake, n: int, lines: list[int]) -> str:
    shown = ", ".join(str(x) for x in lines[:8]) + (" ..." if len(lines) > 8 else "")
    return f"seen {n} times (lines {shown}); on its own it would be {first.base_category}"


def _line_break_mark(hunk: Hunk, comparison: Comparison) -> bool:
    """True for a mark A has and B lacks at the place where B breaks the line."""
    if hunk.b or not hunk.a:
        return False
    start = hunk.b_span[0]
    tokens = comparison.b_tokens
    if start <= 0 or start >= len(tokens):
        return False
    return tokens[start - 1].para != tokens[start].para


def _ignore_reason(mistake: Mistake, comparison: Comparison, rules: Rules) -> str:
    """Why a difference adds nothing under the rules' switches, or an empty string."""
    hunk = mistake.hunk
    if rules.ignore_music_markers and mistake.rule_id == "CC_MUSIC":
        return "song markers are formatting, not counted"
    limit = rules.ignore_long_cuts_words
    if limit and mistake.rule_id == "MAJOR_ADDED" and len(hunk.tokens) >= limit:
        return f"{len(hunk.tokens)} words only one side has: a cut, not a word mistake"
    if rules.count_tags == "changed_only" and mistake.rule_id == "CC_TAG":
        if not (hunk.a and hunk.b):
            return "sound tag on one side only: a choice of what to annotate, not counted"
    if (
        rules.ignore_line_break_marks
        and mistake.rule_id == "PUNCT_ONLY"
        and _line_break_mark(hunk, comparison)
    ):
        return "mark dropped because B breaks the line here: a line break, not a mistake"
    return ""


def analyse(comparison: Comparison, rules: Rules) -> Analysis:
    """Classify every hunk of the comparison and count the mistakes."""
    mistakes: list[Mistake] = []
    for index, hunk in enumerate(split_all(comparison.diffs)):
        verdict = classify(hunk, rules)
        mistakes.append(
            Mistake(
                index, hunk.a_line, hunk.b_line, hunk.a_text, hunk.b_text,
                verdict.category, verdict.category, verdict.rule_id, verdict.note,
                verdict.confidence, hunk=hunk,
            )
        )
    groups: dict[tuple[str, str], list[Mistake]] = defaultdict(list)
    for mistake in mistakes:
        reason = _ignore_reason(mistake, comparison, rules)
        if reason:
            mistake.status, mistake.ignored_because = "ignored", reason
            continue
        groups[mistake.hunk.key].append(mistake)
    for members in groups.values():
        if any(m.base_category not in rules.repeated_categories for m in members):
            continue
        if len(members) < repeat_threshold(rules, members[0].base_category):
            continue
        first = members[0]
        lines = [m.line_no for m in members]
        first.category, first.rule_id = "Repeated", "REPEATED_PAIR"
        first.occurrences, first.lines = len(members), lines
        first.note = _repeat_note(first, len(members), lines)
        for other in members[1:]:
            other.status, other.repeat_of = "repeat", first.index
    tally = Counter(m.category for m in mistakes if m.status == "counted")
    return Analysis(mistakes, {name: tally.get(name, 0) for name in CATEGORIES})
