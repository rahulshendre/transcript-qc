"""Put a known number of each mistake into a clean transcript and check the tool finds exactly those.

The expected counts come from what was put in (tests/synthetic.py), not from running the tool. This is
the check that does not depend on Episode 50: it shows the rules do what they say on text they were never
tuned on. It does not show that the rules match a reviewer's judgement; that needs a second real episode.
"""

import pytest
from helpers import make_qc
from synthetic import Plan, build

from transcript_qc.compare import compare_paragraphs
from transcript_qc.count import analyse
from transcript_qc.revisions import round_trip
from transcript_qc.rules import CATEGORIES, load_rules

PLANS = {
    "mixed": Plan(major_different=8, major_missing=6, language=8, punctuation=12, cc=5, minor=4,
                  repeat_pair=("न", "ना"), repeat_times=7),
    "only_major": Plan(major_different=8, major_missing=8),
    "only_language": Plan(language=16),
    "only_punctuation": Plan(punctuation=24),
    "only_cc": Plan(cc=5),
    "only_minor": Plan(minor=4),
    "a_repeated_pair": Plan(repeat_pair=("वो", "वह"), repeat_times=9),
    "too_few_to_repeat": Plan(repeat_pair=("न", "ना"), repeat_times=3),
    "long_file": Plan(major_different=8, major_missing=8, language=8, punctuation=30, cc=5, minor=4,
                      lines=400, repeat_pair=("न", "ना"), repeat_times=7),
    "nothing_wrong": Plan(),
}
SEEDS = range(15)


def counted(pair):
    return analyse(compare_paragraphs(pair.a, pair.b), load_rules("default")).counts


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("name", PLANS)
def test_the_tool_finds_exactly_the_mistakes_that_were_put_in(name, seed):
    pair = build(PLANS[name], seed)
    assert counted(pair) == PLANS[name].expected(), "\n".join(pair.log)


@pytest.mark.parametrize("category,field", [
    ("Major", "major_different"), ("Major", "major_missing"), ("Language", "language"),
    ("Punctuation", "punctuation"), ("CC", "cc"), ("Minor", "minor"),
])
@pytest.mark.parametrize("how_many", [1, 2, 3])
def test_each_category_is_found_whether_there_is_one_mistake_or_a_few(category, field, how_many):
    pair = build(Plan(**{field: how_many}), seed=3)
    expected = dict.fromkeys(CATEGORIES, 0) | {category: how_many}
    assert counted(pair) == expected, "\n".join(pair.log)


def test_formatting_noise_alone_counts_nothing():
    # song markers, double spaces, a non-breaking space and a zero-width space differ; none is a mistake
    pair = build(Plan(noise=True), seed=1)
    result = analyse(compare_paragraphs(pair.a, pair.b), load_rules("default"))
    assert sum(result.counts.values()) == 0
    assert len(result.counted) == 0


def test_two_changed_words_that_touch_across_a_line_break_are_one_run():
    # the brief's rule 1: a run of consecutive changed words is one mistake. The last word of one
    # line and the first word of the next are consecutive in the stream, so they merge.
    result = analyse(
        compare_paragraphs(["सुबह ही जंगल पलिता", "उंचे स्कूल फिर लोहा"],
                           ["सुबह ही जंगल पलीता", "ऊँचे स्कूल फिर लोहा"]),
        load_rules("default"),
    )
    assert result.counts["Language"] == 1


def test_the_qc_document_for_a_made_up_pair_round_trips(tmp_path):
    pair = build(PLANS["mixed"], seed=7)
    qc, comparison, _ = make_qc(tmp_path, pair.a, pair.b)
    rejected, accepted = round_trip(qc, comparison.a_paragraphs, comparison.b_paragraphs)
    assert rejected >= 0.999 and accepted >= 0.999
