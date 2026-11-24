import dataclasses
import re

import pytest
from helpers import analysis, only

from transcript_qc.classify import RULE_IDS, distance, skeleton
from transcript_qc.compare import compare_paragraphs
from transcript_qc.hunks import split_all
from transcript_qc.rules import CATEGORIES, load_rules

STRICT = load_rules("strict")


def classify_one(a: str, b: str, rules=STRICT):
    """Category and rule id of the only mistake between two single lines."""
    result = analysis([a], [b], rules)
    mistakes = result.mistakes
    assert len(mistakes) == 1, [(m.a_text, m.b_text, m.rule_id) for m in mistakes]
    return mistakes[0].category, mistakes[0].rule_id


# one test per category -------------------------------------------------------

def test_major_a_different_word():
    assert classify_one("उसने कहा", "उसने खाना") == ("Major", "MAJOR_DIFFERENT")


def test_major_a_word_missing_or_extra():
    assert classify_one("उसके मामा के पोते", "उसके मामा") == ("Major", "MAJOR_ADDED")
    assert classify_one("उसके मामा", "उसके मामा के पोते") == ("Major", "MAJOR_ADDED")


def test_language_a_matra_or_spelling_mistake():
    assert classify_one("जल भी कहां था", "जल भी कहाँ था") == ("Language", "LANG_MARKS")
    assert classify_one("पलिता लगाओ", "पलीता लगाओ") == ("Language", "LANG_MARKS")
    assert classify_one("कहिए जी", "कहिये जी") == ("Language", "LANG_SIMILAR")


def test_punctuation_missing_extra_or_wrong():
    assert classify_one("बहुत खूब", "बहुत खूब।") == ("Punctuation", "PUNCT_ONLY")
    assert classify_one("बहुत खूब।", "बहुत खूब") == ("Punctuation", "PUNCT_ONLY")
    assert classify_one("खूब, बहुत", "खूब! बहुत") == ("Punctuation", "PUNCT_ONLY")


def test_cc_sound_tags_and_song_markers():
    assert classify_one("आओ [हवा चलने की आवाज़]", "आओ [नाटकीय संगीत]") == ("CC", "CC_TAG")
    assert classify_one("आओ", "आओ [हँसते हुए]") == ("CC", "CC_TAG")
    assert classify_one("सृष्टि से पहले", "♪ सृष्टि से पहले") == ("CC", "CC_MUSIC")


def test_repeated_a_pair_seen_more_than_once():
    a = ["वह आया", "वह गया", "वह बैठा"]
    b = ["बह आया", "बह गया", "बह बैठा"]
    result = analysis(a, b, "strict")
    assert result.counts["Repeated"] == 1
    assert only(result).category == "Repeated"


def test_minor_a_space_that_splits_or_joins_a_word():
    assert classify_one("राम राज आया", "रामराज आया") == ("Minor", "MINOR_SPACE")
    assert classify_one("गांधीजी आए", "गांधी जी आए") == ("Minor", "MINOR_SPACE")


# the rules behind them -------------------------------------------------------

def test_every_rule_in_the_shipped_order_exists():
    for profile in ("default", "strict"):
        assert set(load_rules(profile).order) <= RULE_IDS


def test_a_known_variant_is_language_even_when_the_words_look_different():
    # वह and वो share only one letter, so on distance alone this would be Major
    assert distance("वह", "वो") > 0.4
    assert classify_one("वह आया", "वो आया") == ("Language", "LANG_VARIANT")


def test_a_variant_works_in_both_directions_and_is_configurable():
    assert classify_one("वो आया", "वह आया") == ("Language", "LANG_VARIANT")
    assert classify_one("पर आया", "पे आया")[0] == "Major"
    custom = dataclasses.replace(STRICT, variants=STRICT.variants | {("पर", "पे"), ("पे", "पर")})
    assert classify_one("पर आया", "पे आया", custom) == ("Language", "LANG_VARIANT")


def test_same_letters_without_matras_is_language_even_when_distance_is_high():
    assert distance("तु", "तू") > 0.4
    assert classify_one("तु आया", "तू आया") == ("Language", "LANG_MARKS")


def test_the_distance_threshold_decides_between_language_and_major():
    assert distance("अगर", "मगर") == pytest.approx(1 / 3)
    assert classify_one("अगर आया", "मगर आया")[0] == "Language"
    stricter = dataclasses.replace(STRICT, language_max_distance=0.2)
    assert classify_one("अगर आया", "मगर आया", stricter)[0] == "Major"


def test_a_distance_exactly_at_the_threshold_is_still_language():
    # two of five letters differ: distance exactly 0.4, and the rule says "at or below"
    assert distance("कखगघङ", "कखगचछ") == pytest.approx(0.4)
    assert classify_one("कखगघङ आया", "कखगचछ आया") == ("Language", "LANG_SIMILAR")
    just_over = dataclasses.replace(STRICT, language_max_distance=0.39)
    assert classify_one("कखगघङ आया", "कखगचछ आया", just_over)[0] == "Major"


def test_minor_is_decided_before_language():
    # identical once spaces go: distance 0, which would otherwise look like a spelling variant
    assert classify_one("कब का", "कबका") == ("Minor", "MINOR_SPACE")


def test_the_first_matching_rule_wins_so_the_order_matters():
    # कहां -> कहाँ matches both LANG_MARKS and MAJOR_DIFFERENT's catch-all; the order picks one
    assert classify_one("जल कहां", "जल कहाँ") == ("Language", "LANG_MARKS")
    similar_first = dataclasses.replace(STRICT, order=("LANG_SIMILAR", "LANG_MARKS"))
    assert classify_one("जल कहां", "जल कहाँ", similar_first) == ("Language", "LANG_SIMILAR")
    major_first = dataclasses.replace(STRICT, order=("MAJOR_DIFFERENT", "LANG_MARKS"))
    assert classify_one("जल कहां", "जल कहाँ", major_first)[0] == "Major"


def test_a_difference_no_rule_claims_is_still_counted():
    nothing = dataclasses.replace(STRICT, order=("PUNCT_ONLY",))
    category, rule_id = classify_one("उसने कहा", "उसने खाना", nothing)
    assert (category, rule_id) == ("Major", "NO_RULE")


def test_skeleton_ignores_matras_nukta_anusvara_and_chandrabindu():
    marks = STRICT.ignore_marks
    assert skeleton("कहां", marks) == skeleton("कहाँ", marks)
    assert skeleton("ज़रूर", marks) == skeleton("जरूर", marks)
    assert skeleton("गंभीर", marks) == skeleton("गभीर", marks)
    assert skeleton("कहा", marks) == skeleton("कही", marks) == "कह"
    assert skeleton("कहा", marks) != skeleton("खाना", marks)


def test_distance_runs_from_zero_to_one():
    assert distance("कहाँ", "कहाँ") == 0
    assert distance("कहाँ", "") == 1
    assert 0 < distance("कहां", "कहाँ") < 1


# word by word ----------------------------------------------------------------

def test_the_briefs_major_example_is_major_because_each_word_is_a_different_word():
    # सच मुझमें -> सचमुच में: little changes in the letters overall, but सच/सचमुच and
    # मुझमें/में are each far apart as words
    assert classify_one("वही सच मुझमें जानता", "वही सचमुच में जानता")[0] == "Major"


def test_a_hunk_is_language_only_when_every_word_in_it_is_a_spelling_variant():
    assert classify_one("बना ना आया", "बनो न आया")[0] == "Language"
    assert classify_one("बना सच आया", "बनो मुझमें आया")[0] == "Major"


def test_vowel_length_is_spelling_not_a_different_word():
    assert classify_one("उंचे आकाश", "ऊँचे आकाश") == ("Language", "LANG_MARKS")
    no_fold = dataclasses.replace(STRICT, fold_vowel_length=False)
    assert classify_one("उंचे आकाश", "ऊँचे आकाश", no_fold)[0] == "Major"


def test_a_word_with_no_partner_inside_a_replacement_makes_it_major():
    assert classify_one("कहां वह", "कहाँ बहुत वह") == ("Major", "MAJOR_ADDED")


def test_pairing_matches_each_word_with_its_closest_partner():
    from transcript_qc.classify import pair_words

    assert pair_words(["कहां", "था"], ["कहाँ", "था"]) == [("कहां", "कहाँ"), ("था", "था")]
    assert pair_words(["कहां", "था"], ["था"]) == [("कहां", None), ("था", "था")]
    assert pair_words(["था"], ["कहां", "था"]) == [(None, "कहां"), ("था", "था")]
    assert pair_words([], []) == []


# splitting mixed differences -------------------------------------------------

def test_a_word_change_mixed_with_punctuation_becomes_two_mistakes():
    result = analysis(["वाह करता , उंचे"], ["वा अकर्ता ! ऊँचे"], "strict")
    kinds = sorted((m.hunk.kind, m.category) for m in result.mistakes)
    assert kinds == [("other", "Punctuation"), ("word", "Language")]


def test_a_sound_tag_mixed_with_words_is_split_so_the_words_are_still_counted():
    result = analysis(["आओ [हवा की आवाज़] चलो"], ["आओ सब चलो"], "strict")
    assert sorted((m.hunk.kind, m.category) for m in result.mistakes) == [
        ("other", "CC"), ("word", "Major"),
    ]


def test_punctuation_that_is_the_same_on_both_sides_of_a_changed_run_is_not_a_mistake():
    # the commas inside the changed words match, so only the words differ
    result = analysis(["वाह , करता , उंचे"], ["वा , अकर्ता , ऊँचे"], "strict")
    assert [(m.hunk.kind, m.category) for m in result.mistakes] == [("word", "Language")]
    assert all(m.a_text.split() != m.b_text.split() for m in result.mistakes)


def test_a_pure_word_or_pure_punctuation_difference_is_not_split():
    comparison = compare_paragraphs(["जल भी कहां था"], ["जल भी कहाँ था"])
    assert [h.kind for h in split_all(comparison.diffs)] == ["word"]
    comparison = compare_paragraphs(["खूब, बहुत"], ["खूब! बहुत"])
    assert [h.kind for h in split_all(comparison.diffs)] == ["other"]


# what every mistake carries --------------------------------------------------

def test_every_mistake_has_a_rule_id_a_reason_and_a_confidence():
    a = ["जल भी कहां था", "बहुत खूब", "आओ [हवा]", "उसके मामा के पोते"]
    b = ["जल भी कहाँ था", "बहुत खूब।", "आओ [संगीत]", "उसके मामा"]
    for mistake in analysis(a, b, "strict").mistakes:
        assert mistake.rule_id in RULE_IDS | {"REPEATED_PAIR"}
        assert mistake.note
        assert 0.5 <= mistake.confidence <= 1.0


def test_exact_rules_are_fully_confident_and_threshold_cases_less_so():
    exact = only(analysis(["बहुत खूब"], ["बहुत खूब।"]))
    assert exact.confidence == 1.0
    borderline = only(analysis(["अगर आया"], ["मगर आया"]))   # distance 0.33, next to the 0.4 cut
    clear = only(analysis(["उसने कहा"], ["उसने खाना"]))      # far from it
    assert borderline.confidence < clear.confidence


def test_a_distance_in_the_note_never_contradicts_the_verdict():
    # उंचे / ऊँचे are 0.5 apart letter by letter but count as the same letters, so the note
    # must not quote 0.5 next to a Language verdict
    mistake = only(analysis(["वाह उंचे"], ["वा ऊँचे"], "strict"))
    assert mistake.category == "Language"
    assert "distance 0.50" not in mistake.note
    pairs = analysis(["अगर आया", "वही सच मुझमें"], ["मगर आया", "वही सचमुच में"], "strict")
    for m in pairs.mistakes:
        found = re.search(r"distance (\d\.\d\d)", m.note)
        assert found, m.note
        assert (float(found[1]) <= 0.4) == (m.category == "Language")


def test_spacing_inside_a_sound_tag_is_not_shown_in_the_text():
    mistake = only(analysis(["आओ"], ["आओ [नाटकीय   संगीत]"], "strict"))
    assert mistake.b_text == "[नाटकीय संगीत]"


def test_the_note_says_in_plain_words_what_is_different():
    assert "missing in A" in only(analysis(["खूब"], ["खूब।"])).note
    assert "not in the reference" in only(analysis(["खूब।"], ["खूब"])).note
    assert "kahaan" not in only(analysis(["कहां"], ["कहाँ"])).note
    assert "कहां" in only(analysis(["कहां"], ["कहाँ"])).note


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_category_is_a_known_name(category):
    assert category in {"Major", "Language", "Punctuation", "CC", "Repeated", "Minor"}
