"""Compare counts with a reviewer's reference table and check the acceptance bounds."""

from __future__ import annotations

import math
from dataclasses import dataclass

from transcript_qc.rules import CATEGORIES

# Bharat Ek Khoj, Episode 50: the table the QC team produced by hand.
EPISODE_50 = {
    "Major": 9, "Language": 12, "Punctuation": 66, "CC": 2, "Repeated": 4, "Minor": 4,
}


@dataclass(frozen=True, slots=True)
class Gap:
    category: str
    engine: int
    reference: int

    @property
    def delta(self) -> int:
        return self.engine - self.reference

    @property
    def tolerance(self) -> float:
        """Each category may be off by 20 percent or 3, whichever is larger."""
        return max(0.2 * self.reference, 3)

    @property
    def within(self) -> bool:
        return abs(self.delta) <= self.tolerance


def parse_reference(text: str) -> dict[str, int]:
    """'ep50', or six numbers in the order Major, Language, Punctuation, CC, Repeated, Minor."""
    if text.lower() in ("ep50", "episode50"):
        return dict(EPISODE_50)
    values = [int(x) for x in text.replace(" ", "").split(",")]
    if len(values) != len(CATEGORIES):
        raise ValueError(f"expected {len(CATEGORIES)} numbers, got {len(values)}")
    return dict(zip(CATEGORIES, values, strict=True))


def gaps(counts: dict[str, int], reference: dict[str, int]) -> list[Gap]:
    return [Gap(name, counts.get(name, 0), reference[name]) for name in CATEGORIES]


def total_tolerance(reference_total: int) -> int:
    """The total may be off by 10 percent, rounded up (97 allows 87 to 107, as the brief says)."""
    return math.ceil(0.1 * reference_total)


def total_within(engine_total: int, reference_total: int) -> bool:
    return abs(engine_total - reference_total) <= total_tolerance(reference_total)


def format_table(counts: dict[str, int], reference: dict[str, int]) -> str:
    rows = gaps(counts, reference)
    engine_total, ref_total = sum(counts.values()), sum(reference.values())
    lines = [f"{'category':<12} {'engine':>7} {'reference':>10} {'difference':>11}  within bound"]
    for g in rows:
        lines.append(
            f"{g.category:<12} {g.engine:>7} {g.reference:>10} {g.delta:>+11}  "
            f"{'yes' if g.within else 'no'} (+/-{g.tolerance:g})"
        )
    verdict = "yes" if total_within(engine_total, ref_total) else "no"
    lines.append(
        f"{'Total':<12} {engine_total:>7} {ref_total:>10} {engine_total - ref_total:>+11}  "
        f"{verdict} (+/-{total_tolerance(ref_total)})"
    )
    return "\n".join(lines)
