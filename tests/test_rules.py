import copy

import pytest
import yaml

from transcript_qc.rules import PROFILES, load_rules, parse_rules


def shipped():
    from importlib import resources

    text = (resources.files("transcript_qc") / "rules.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_the_shipped_profiles_load(name):
    rules = load_rules(name)
    assert rules.order and 0 <= rules.language_max_distance <= 1


def test_no_argument_loads_the_default_profile():
    assert load_rules() == load_rules("default")


def test_a_rules_file_path_is_loaded(tmp_path):
    data = shipped()
    data["similarity"]["language_max_distance"] = 0.25
    path = tmp_path / "mine.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert load_rules(path).language_max_distance == 0.25
    assert load_rules(str(path)).language_max_distance == 0.25


def test_variants_are_stored_in_both_directions_and_normalised():
    rules = load_rules("strict")
    assert ("वह", "वो") in rules.variants and ("वो", "वह") in rules.variants


def test_an_unknown_rule_id_is_refused_with_the_known_ones_listed():
    data = copy.deepcopy(shipped())
    data["order"].append("NOT_A_RULE")
    with pytest.raises(ValueError, match="NOT_A_RULE"):
        parse_rules(data)


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_a_distance_outside_zero_to_one_is_refused(bad):
    data = copy.deepcopy(shipped())
    data["similarity"]["language_max_distance"] = bad
    with pytest.raises(ValueError, match="language_max_distance"):
        parse_rules(data)


def test_an_unknown_repeated_category_is_refused():
    data = copy.deepcopy(shipped())
    data["repeated"]["categories"] = ["Major", "Nonsense"]
    with pytest.raises(ValueError, match="Nonsense"):
        parse_rules(data)


def test_a_variant_that_is_not_a_pair_is_refused():
    data = copy.deepcopy(shipped())
    data["variants"] = [["वह"]]
    with pytest.raises(ValueError, match="pair"):
        parse_rules(data)


def test_tags_count_must_be_all_or_changed_only():
    data = copy.deepcopy(shipped())
    data["tags"] = {"count": "sometimes"}
    with pytest.raises(ValueError, match="tags.count"):
        parse_rules(data)


def test_movie_codes_are_case_insensitive():
    assert load_rules().movies["BEK"] == "Bharat Ek Khoj"


def test_a_repeat_threshold_can_be_set_for_one_category():
    rules = load_rules()
    assert rules.repeated_min_by_category == {"Punctuation": 10, "CC": 10}


def test_a_threshold_for_an_unknown_category_is_refused():
    data = copy.deepcopy(shipped())
    data["repeated"]["min_occurrences_by_category"] = {"Nonsense": 3}
    with pytest.raises(ValueError, match="Nonsense"):
        parse_rules(data)


def test_the_strict_profile_has_no_per_category_thresholds():
    assert load_rules("strict").repeated_min_by_category == {}
