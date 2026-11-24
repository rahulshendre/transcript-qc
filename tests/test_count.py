import dataclasses

from helpers import analysis

from transcript_qc.rules import CATEGORIES, load_rules, repeat_threshold

STRICT = load_rules("strict")


def repeated_lines(word_a="वह", word_b="बह", times=3):
    a = [f"{word_a} आया {i}" for i in range(times)]
    b = [f"{word_b} आया {i}" for i in range(times)]
    return a, b


# rule 3: repeated patterns count once ----------------------------------------

def test_a_repeated_pair_is_one_repeated_mistake_and_nothing_else():
    a, b = repeated_lines(times=4)
    result = analysis(a, b, "strict")
    assert result.counts["Repeated"] == 1
    assert sum(v for k, v in result.counts.items() if k != "Repeated") == 0
    assert result.total == 1


def test_the_other_occurrences_are_kept_but_add_nothing():
    a, b = repeated_lines(times=4)
    result = analysis(a, b, "strict")
    assert len(result.mistakes) == 4
    assert len(result.counted) == 1
    assert len(result.repeats) == 3
    first = result.counted[0]
    assert all(m.repeat_of == first.index and m.status == "repeat" for m in result.repeats)
    assert first.occurrences == 4
    assert len(first.lines) == 4


def test_the_repeated_mistake_says_what_it_would_be_on_its_own_and_where_it_appears():
    a, b = repeated_lines(times=3)
    first = analysis(a, b, "strict").counted[0]
    assert "seen 3 times" in first.note
    assert first.base_category in first.note
    assert first.rule_id == "REPEATED_PAIR"


def test_a_pair_below_the_threshold_is_counted_each_time():
    a, b = repeated_lines(times=2)
    rules = dataclasses.replace(STRICT, repeated_min=3)
    result = analysis(a, b, rules)
    assert result.counts["Repeated"] == 0
    assert len(result.counted) == 2


def test_the_threshold_is_inclusive():
    a, b = repeated_lines(times=3)
    assert analysis(a, b, dataclasses.replace(STRICT, repeated_min=3)).counts["Repeated"] == 1
    assert analysis(a, b, dataclasses.replace(STRICT, repeated_min=4)).counts["Repeated"] == 0


def test_the_same_words_in_a_different_direction_are_a_different_pair():
    a = ["वह आया", "बह गया"]
    b = ["बह आया", "वह गया"]
    assert analysis(a, b, "strict").counts["Repeated"] == 0


def test_only_the_chosen_categories_can_become_repeated():
    a = ["खूब, बहुत", "खूब, बहुत", "खूब, बहुत"]
    b = ["खूब! बहुत", "खूब! बहुत", "खूब! बहुत"]
    assert analysis(a, b, "strict").counts["Repeated"] == 1
    words_only = dataclasses.replace(STRICT, repeated_categories=frozenset({"Major", "Language"}))
    result = analysis(a, b, words_only)
    assert result.counts["Repeated"] == 0
    assert result.counts["Punctuation"] == 3


# rule 5 ----------------------------------------------------------------------

def test_the_total_is_the_sum_of_the_six_counts_and_all_six_are_present():
    a = ["जल भी कहां था", "बहुत खूब", "आओ [हवा]", "उसके मामा के पोते", "ठीक है", "राम राज आया"]
    b = ["जल भी कहाँ था", "बहुत खूब।", "आओ [संगीत]", "उसके मामा", "ठीक है", "रामराज आया"]
    result = analysis(a, b, "strict")
    assert tuple(result.counts) == CATEGORIES
    assert result.total == sum(result.counts.values()) == 5
    assert all(result.counts[c] == 1 for c in ("Major", "Language", "Punctuation", "CC", "Minor"))
    assert result.counts["Repeated"] == 0


def test_counts_plus_repeats_plus_ignored_cover_every_difference():
    a, b = repeated_lines(times=5)
    result = analysis(a + ["बहुत खूब"], b + ["बहुत खूब।"], "strict")
    assert len(result.counted) + len(result.repeats) + len(result.ignored) == len(result.mistakes)


def test_counting_is_deterministic():
    a, b = repeated_lines(times=4)
    first = analysis(a, b, "strict")
    second = analysis(a, b, "strict")
    assert first.counts == second.counts
    assert [(m.category, m.rule_id, m.line_no) for m in first.mistakes] == [
        (m.category, m.rule_id, m.line_no) for m in second.mistakes
    ]


# rule 2: formatting is never a mistake ---------------------------------------

def test_double_spaces_and_line_breaks_count_for_nothing():
    a = ["सबसे अहम पहलू था-औरतों का योगदान।"]
    b = ["सबसे  अहम  पहलू  था-", "", "औरतों  का  योगदान।"]
    assert analysis(a, b, "strict").total == 0


# the judgement switches ------------------------------------------------------

def test_changes_next_to_each_other_with_nothing_matching_between_are_one_hunk():
    # rule 1: a run of consecutive changed words is one mistake, even across a line break
    a = ["उसके मामा के पोते", "राम राज आया"]
    b = ["उसके मामा", "रामराज आया"]
    result = analysis(a, b, "strict")
    assert len(result.mistakes) == 1


def test_song_markers_can_be_left_uncounted():
    a, b = ["सृष्टि से पहले"], ["♪ सृष्टि से पहले ♪"]
    # two identical insertions would collapse into one Repeated mistake, so switch that off
    counted = analysis(a, b, dataclasses.replace(STRICT, repeated_min=99))
    assert counted.counts["CC"] == 2
    muted = analysis(a, b, dataclasses.replace(STRICT, ignore_music_markers=True))
    assert muted.counts["CC"] == 0
    assert len(muted.ignored) == 2
    assert "song markers are formatting" in muted.ignored[0].ignored_because


def test_a_sound_tag_only_one_side_has_can_be_left_uncounted_but_a_changed_tag_still_counts():
    rules = dataclasses.replace(STRICT, count_tags="changed_only")
    only_in_b = analysis(["आओ"], ["आओ [हँसते हुए]"], rules)
    assert (only_in_b.counts["CC"], len(only_in_b.ignored)) == (0, 1)
    only_in_a = analysis(["आओ [हँसते हुए]"], ["आओ"], rules)
    assert (only_in_a.counts["CC"], len(only_in_a.ignored)) == (0, 1)
    changed = analysis(["आओ [हवा चलने की आवाज़]"], ["आओ [नाटकीय संगीत]"], rules)
    assert (changed.counts["CC"], len(changed.ignored)) == (1, 0)


def test_a_mark_dropped_where_b_breaks_the_line_is_a_line_break_not_a_mistake():
    rules = dataclasses.replace(STRICT, ignore_line_break_marks=True)
    broken = analysis(["खूब, बहुत अच्छा"], ["खूब", "", "बहुत अच्छा"], rules)
    assert (broken.counts["Punctuation"], len(broken.ignored)) == (0, 1)
    assert "line" in broken.ignored[0].ignored_because
    midline = analysis(["खूब, बहुत अच्छा"], ["खूब बहुत अच्छा"], rules)
    assert midline.counts["Punctuation"] == 1  # B keeps the line, so the missing mark is real


def test_only_a_mark_b_lacks_is_a_line_break_candidate():
    rules = dataclasses.replace(STRICT, ignore_line_break_marks=True)
    changed = analysis(["खूब, बहुत"], ["खूब!", "", "बहुत"], rules)
    assert changed.counts["Punctuation"] == 1   # a different mark is still a different mark


def test_a_long_cut_is_not_a_word_mistake_but_a_short_one_is():
    rules = dataclasses.replace(STRICT, ignore_long_cuts_words=4)
    cut = analysis(["वंदे मातरम वंदे मातरम सब आए"], ["सब आए"], rules)
    assert (cut.counts["Major"], len(cut.ignored)) == (0, 1)
    short = analysis(["वंदे मातरम सब आए"], ["सब आए"], rules)
    assert short.counts["Major"] == 1
    assert "cut" in cut.ignored[0].ignored_because


def test_an_ignored_difference_is_not_part_of_a_repeated_pair():
    rules = dataclasses.replace(STRICT, ignore_music_markers=True)
    a = ["एक", "दो", "तीन"]
    b = ["♪ एक", "♪ दो", "♪ तीन"]
    result = analysis(a, b, rules)
    assert result.counts["Repeated"] == 0
    assert len(result.ignored) == 3


def test_the_strict_profile_has_no_judgement_switches_on():
    assert not STRICT.ignore_music_markers
    assert not STRICT.ignore_line_break_marks
    assert STRICT.ignore_long_cuts_words == 0
    assert STRICT.count_tags == "all"
    assert STRICT.repeated_min == 2


def test_the_default_profile_is_the_tuned_one():
    tuned = load_rules("default")
    assert tuned.ignore_music_markers and tuned.ignore_line_break_marks
    assert tuned.count_tags == "changed_only"
    assert tuned.repeated_min == 5
    assert repeat_threshold(tuned, "Language") == 5
    assert repeat_threshold(tuned, "Punctuation") == 10


def test_a_pair_needs_a_different_number_of_repeats_in_each_category():
    rules = dataclasses.replace(
        STRICT, repeated_min=3, repeated_min_by_category={"Punctuation": 6}
    )
    words = analysis(*repeated_lines(times=3), rules)
    assert words.counts["Repeated"] == 1                       # a word pair: 3 is enough
    marks = analysis(["खूब, बहुत"] * 5, ["खूब! बहुत"] * 5, rules)
    assert marks.counts["Repeated"] == 0 and marks.counts["Punctuation"] == 5   # needs 6
    more = analysis(["खूब, बहुत"] * 6, ["खूब! बहुत"] * 6, rules)
    assert more.counts["Repeated"] == 1 and more.counts["Punctuation"] == 0
