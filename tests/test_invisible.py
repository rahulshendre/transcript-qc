"""Characters nobody can see must never show up as a mistake."""

import pytest

from transcript_qc.compare import compare_paragraphs


# invisible characters are never a mistake
@pytest.mark.parametrize("char", ["​", "⁠", "﻿", "­", "‎", "‏"])
@pytest.mark.parametrize("where", ["inside", "between", "end", "start"])
def test_invisible_characters_alone_are_not_a_difference(char, where):
    base = "नमस्ते दुनिया कैसे हो"
    changed = {
        "inside": base.replace("दुनिया", "दुनि" + char + "या"),
        "between": base.replace("दुनिया कैसे", "दुनिया " + char + " कैसे"),
        "end": base + char,
        "start": char + base,
    }[where]
    assert compare_paragraphs([base], [changed]).diffs == []
    assert compare_paragraphs([changed], [base]).diffs == []


@pytest.mark.parametrize("joiner", ["‌", "‍"])
def test_joiners_at_the_edge_of_a_word_are_not_a_difference(joiner):
    base = "नमस्ते दुनिया कैसे हो"
    assert compare_paragraphs([base], [base + joiner]).diffs == []
    assert compare_paragraphs([base], [base.replace("दुनिया", joiner + "दुनिया" + joiner)]).diffs == []


def test_a_joiner_inside_a_word_still_shows_because_it_changes_the_shape():
    result = compare_paragraphs(["क्षत्रिय"], ["क्‍षत्रिय"])
    assert len(result.diffs) == 1


def test_a_zero_width_space_between_words_with_no_real_space_is_a_missing_space():
    result = compare_paragraphs(["दुनिया कैसे"], ["दुनिया​कैसे"])
    assert len(result.diffs) == 1
