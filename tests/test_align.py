from transcript_qc.align import align
from transcript_qc.tokenize import tokenize


def diff(a_lines, b_lines):
    return align(tokenize(a_lines), tokenize(b_lines))


def shape(diffs):
    return [(d.tag, d.a_text, d.b_text) for d in diffs]


def test_identical_files_have_no_differences():
    assert diff(["एक दो तीन", "", "चार"], ["एक दो तीन", "", "चार"]) == []


def test_double_spaces_in_b_are_not_a_difference():
    assert diff(["नहीं भी जानता।"], ["नहीं  भी   जानता।"]) == []


def test_blank_paragraphs_do_not_matter():
    assert diff(["एक", "", "दो"], ["एक", "दो"]) == []


def test_a_line_split_in_two_in_b_still_aligns():
    a = ["सबसे अहम पहलू था-औरतों का योगदान।"]
    b = ["सबसे अहम पहलू था-", "", "औरतों का योगदान।"]
    assert diff(a, b) == []


def test_two_lines_merged_into_one_in_b_still_aligns():
    a = ["छिपा था क्या", "", "कहाँ किसने ढका था"]
    b = ["छिपा था क्या कहाँ किसने ढका था"]
    assert diff(a, b) == []


def test_a_spelling_change_is_one_replace():
    assert shape(diff(["जल भी कहां था"], ["जल भी कहाँ था"])) == [("replace", "कहां", "कहाँ")]


def test_a_run_of_changed_words_is_one_difference():
    result = diff(["वही सच मुझमें जानता"], ["वही सचमुच में जानता"])
    assert shape(result) == [("replace", "सच मुझमें", "सचमुच में")]


def test_a_missing_word_is_a_delete_and_an_extra_word_is_an_insert():
    assert shape(diff(["उसके मामा के पोते"], ["उसके मामा"])) == [("delete", "के पोते", "")]
    assert shape(diff(["उसके मामा"], ["उसके मामा के पोते"])) == [("insert", "", "के पोते")]


def test_punctuation_changes_are_separate_from_word_changes():
    # the comma moved lines in B, but कहां to कहाँ must still pair up as one spelling change
    a = ["छिपा था क्या, कहां किसने ढका था?"]
    b = ["♪ छिपा था क्या ♪", "", "♪ कहाँ, किसने ढका था ♪"]
    result = shape(diff(a, b))
    assert ("replace", "कहां", "कहाँ") in result
    assert not any(tag == "delete" and "कहां" in a_text for tag, a_text, _ in result)


def test_changed_punctuation_next_to_a_matching_word():
    assert shape(diff(["खूब, बहुत"], ["खूब! बहुत"])) == [("replace", ",", "!")]
    assert shape(diff(["बहुत खूब"], ["बहुत खूब।"])) == [("insert", "", "।")]


def test_a_changed_sound_tag_is_a_replace():
    result = diff(["आओ [हवा चलने की आवाज़]"], ["आओ [नाटकीय संगीत]"])
    assert shape(result) == [("replace", "[हवा चलने की आवाज़]", "[नाटकीय संगीत]")]


def test_missing_music_markers_show_up_as_inserts():
    result = diff(["सृष्टि से पहले"], ["♪ सृष्टि से पहले ♪"])
    assert shape(result) == [("insert", "", "♪"), ("insert", "", "♪")]


def test_every_difference_has_something_on_at_least_one_side():
    result = diff(["क ख ग, घ।"], ["क x ग ♪ घ"])
    assert result
    assert all(d.a or d.b for d in result)


def test_line_numbers_are_the_paragraph_numbers_in_each_file():
    a = ["एक दो", "", "तीन चार"]
    b = ["एक दो", "", "", "तीन पाँच"]
    (only,) = diff(a, b)
    assert (only.tag, only.a_text, only.b_text) == ("replace", "चार", "पाँच")
    assert (only.a_line, only.b_line) == (3, 4)


def test_an_insert_reports_the_line_it_goes_into():
    (only,) = diff(["एक दो", "", "तीन"], ["एक दो", "", "तीन चार"])
    assert (only.tag, only.a_line, only.b_line) == ("insert", 3, 3)


def test_spans_index_into_the_token_lists():
    a_tokens = tokenize(["जल भी कहां था"])
    b_tokens = tokenize(["जल भी कहाँ था"])
    (only,) = align(a_tokens, b_tokens)
    assert a_tokens[only.a_span[0] : only.a_span[1]] == list(only.a)
    assert b_tokens[only.b_span[0] : only.b_span[1]] == list(only.b)
