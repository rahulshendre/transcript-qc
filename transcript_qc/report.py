"""Write the list of counted mistakes as a CSV file."""

from __future__ import annotations

import csv
from pathlib import Path

from transcript_qc.count import Analysis

COLUMNS = ("line_no", "a_text", "b_text", "category", "rule_id", "note")


def write_csv(analysis: Analysis, path: str | Path) -> int:
    """One row per counted mistake, so every number in the summary has rows behind it."""
    rows = analysis.counted
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:  # BOM: Excel reads Hindi
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for m in rows:
            writer.writerow([m.line_no, m.a_text, m.b_text, m.category, m.rule_id, m.note])
    return len(rows)
