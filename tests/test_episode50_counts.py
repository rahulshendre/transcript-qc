"""Counting on the real Episode 50. Skipped when the files are not present."""

import csv
import re
import unicodedata
from pathlib import Path

import pytest
from docx import Document

from transcript_qc.accuracy import EPISODE_50, gaps, total_within
from transcript_qc.classify import RULE_IDS
from transcript_qc.cli import main
from transcript_qc.compare import compare_files
from transcript_qc.count import analyse
from transcript_qc.rules import CATEGORIES, load_rules

DATA = Path(__file__).resolve().parent.parent / "data" / "ep50"
A = DATA / "LE1 BEK_50_Feltiv.sushila.docx"
B = DATA / "LE2 BHARAT EK KHOJ_EP_50_Chandrakala.docx"

pytestmark = pytest.mark.skipif(not (A.is_file() and B.is_file()), reason="Episode 50 not found")


@pytest.fixture(scope="module")
def comparison():
    return compare_files(A, B)


@pytest.fixture(scope="module")
def strict(comparison):
    return analyse(comparison, load_rules("strict"))


@pytest.fixture(scope="module")
def tuned(comparison):
    return analyse(comparison, load_rules("default"))


# Golden numbers: if a rule or a threshold changes on purpose, update these and the
# accuracy note together. If they move by accident, this is where it shows.
STRICT_COUNTS = {
    "Major": 65, "Language": 19, "Punctuation": 19, "CC": 44, "Repeated": 46, "Minor": 5,
}
TUNED_COUNTS = {
    "Major": 52, "Language": 29, "Punctuation": 66, "CC": 10, "Repeated": 6, "Minor": 11,
}


def test_strict_counts_are_stable(strict):
    assert strict.counts == STRICT_COUNTS
    assert strict.total == 198


def test_tuned_counts_are_stable(tuned):
    assert tuned.counts == TUNED_COUNTS
    assert tuned.total == 174


def test_the_tuned_rules_are_closer_to_the_reviewer_than_the_literal_ones(strict, tuned):
    def error(analysis):
        return abs(analysis.total - 97)

    assert error(tuned) < error(strict)


def test_the_tuned_rules_match_the_reviewers_punctuation_and_repeated_counts(tuned):
    by_name = {g.category: g for g in gaps(tuned.counts, EPISODE_50)}
    assert by_name["Punctuation"].within and by_name["Punctuation"].delta == 0
    assert by_name["Repeated"].within


def test_every_difference_is_accounted_for_exactly_once(comparison, tuned):
    assert len(tuned.counted) + len(tuned.repeats) + len(tuned.ignored) == len(tuned.mistakes)
    assert tuned.total == len(tuned.counted)


def test_every_counted_mistake_has_a_known_rule_and_a_reason(tuned):
    for m in tuned.counted:
        assert m.rule_id in RULE_IDS | {"REPEATED_PAIR"}
        assert m.note and m.a_text + m.b_text
        assert m.category in CATEGORIES


def test_nothing_that_is_only_spacing_is_counted(tuned):
    for m in tuned.mistakes:
        assert m.a_text.split() != m.b_text.split()


def test_every_repeated_mistake_stands_for_the_copies_that_point_at_it(tuned):
    by_index = {m.index: m for m in tuned.mistakes}
    for copy in tuned.repeats:
        first = by_index[copy.repeat_of]
        assert first.category == "Repeated" and first.status == "counted"
        assert first.hunk.key == copy.hunk.key
    for m in tuned.counted:
        if m.category == "Repeated":
            copies = [c for c in tuned.repeats if c.repeat_of == m.index]
            assert m.occurrences == len(copies) + 1


def test_the_known_repeated_pairs_from_the_brief_are_found(strict, tuned):
    for analysis in (strict, tuned):
        pairs = {(m.a_text, m.b_text) for m in analysis.counted if m.category == "Repeated"}
        assert ("ना", "न") in pairs and ("वह", "वो") in pairs


def test_the_briefs_own_examples_are_classified_as_the_brief_says(strict):
    def category(a_text, b_text):
        # what it is on its own: a repeated pair would otherwise show as Repeated
        def clean(text):
            return " ".join(unicodedata.normalize("NFC", text).split())

        def same(m):
            return (clean(m.a_text), clean(m.b_text)) == (clean(a_text), clean(b_text))

        return next(m.base_category for m in strict.mistakes if same(m))

    assert category("कहां", "कहाँ") == "Language"
    assert category("सच मुझमें", "सचमुच में") == "Major"
    assert category("[हवा चलने की आवाज़]", "[नाटकीय संगीत]") == "CC"
    assert category("राम राज", "रामराज") == "Minor"


def test_the_acceptance_bounds_are_reported_honestly(tuned):
    """Records where the tuned rules stand against the brief's bounds, so a change is visible."""
    within = {g.category for g in gaps(tuned.counts, EPISODE_50) if g.within}
    assert within == {"Punctuation", "Repeated"}
    assert not total_within(tuned.total, 97)


def test_the_command_line_writes_a_traceable_set_of_files(tmp_path, capsys):
    out = tmp_path / "ep50_QC.docx"
    code = main(["--a", str(A), "--b", str(B), "--out", str(out), "--reference", "ep50"])
    printed = capsys.readouterr().out
    assert code == 0
    with open(tmp_path / "mistakes.csv", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))[1:]
    assert len(rows) == TUNED_COUNTS_TOTAL
    by_category = {c: sum(1 for r in rows if r[3] == c) for c in CATEGORIES}
    assert by_category == TUNED_COUNTS
    assert all(r[4] for r in rows)
    table = Document(str(out)).tables[0]
    assert table.rows[0].cells[0].text == "Movie Name: Bharat Ek Khoj"
    assert table.rows[1].cells[2].text == "Punctuation Mistakes: 66"
    assert table.rows[3].cells[0].text == f"Total Mistakes: {TUNED_COUNTS_TOTAL}"
    assert re.search(r"Total\s+174\s+97", printed)


TUNED_COUNTS_TOTAL = sum(TUNED_COUNTS.values())
