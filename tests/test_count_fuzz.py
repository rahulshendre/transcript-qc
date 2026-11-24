"""Random transcript pairs: the counts must always add up and trace back to rows."""

import csv
import random

import pytest
import test_fuzz as gen
from helpers import make_qc

from transcript_qc.classify import RULE_IDS
from transcript_qc.compare import compare_paragraphs
from transcript_qc.count import analyse
from transcript_qc.report import write_csv
from transcript_qc.revisions import comparable, revision_texts
from transcript_qc.rules import CATEGORIES, load_rules
from transcript_qc.summary import Details, summary_elements
from transcript_qc.writer import write_qc


def make_pair(seed):
    rng = random.Random(seed)
    base = [gen.random_token(rng) for _ in range(rng.randint(3, 50))]
    a = gen.layout(base, rng, double_spaces=False)
    b = gen.layout(gen.edit(base, rng), rng, double_spaces=True)
    return a, b


@pytest.mark.parametrize("profile", ["strict", "default"])
@pytest.mark.parametrize("seed", range(100))
def test_counts_add_up_and_every_difference_is_accounted_for(profile, seed):
    a, b = make_pair(seed)
    comparison = compare_paragraphs(a, b)
    result = analyse(comparison, load_rules(profile))
    assert tuple(result.counts) == CATEGORIES
    assert result.total == sum(result.counts.values()) == len(result.counted)
    assert len(result.counted) + len(result.repeats) + len(result.ignored) == len(result.mistakes)
    for m in result.mistakes:
        assert m.rule_id in RULE_IDS | {"REPEATED_PAIR", "NO_RULE"}
        assert m.note
        assert m.a_text.split() != m.b_text.split()          # never a spacing-only difference
        assert m.line_no >= 1
    for copy in result.repeats:
        first = result.mistakes[copy.repeat_of]
        assert first.category == "Repeated" and first.hunk.key == copy.hunk.key
    # strict rules: a Repeated mistake really does stand for 2 or more copies
    if profile == "strict":
        for m in result.counted:
            assert (m.category == "Repeated") == (m.occurrences >= 2)


@pytest.mark.parametrize("seed", range(40))
def test_the_csv_always_has_one_row_per_counted_mistake(tmp_path, seed):
    a, b = make_pair(seed)
    result = analyse(compare_paragraphs(a, b), load_rules("default"))
    path = tmp_path / "m.csv"
    assert write_csv(result, path) == result.total
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))[1:]
    assert len(rows) == result.total
    for category in CATEGORIES:
        assert sum(1 for r in rows if r[3] == category) == result.counts[category]


@pytest.mark.parametrize("seed", range(40))
def test_the_qc_document_with_its_summary_table_always_round_trips(tmp_path, seed):
    a, b = make_pair(seed)
    out, comparison, _ = make_qc(tmp_path, a, b)
    result = analyse(comparison, load_rules("default"))
    final = tmp_path / "final.docx"
    write_qc(
        tmp_path / "a.docx", comparison, final,
        append=summary_elements(Details("M", "W", "1"), result.counts),
    )
    rejected, accepted = revision_texts(final)
    assert rejected[: len(comparison.a_paragraphs)] == comparison.a_paragraphs
    assert comparable(accepted) == comparable(comparison.b_paragraphs)
