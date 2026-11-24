from transcript_qc.tokenize import MUSIC, PUNCT, TAG, WORD, tokenize, tokenize_line


def texts(tokens):
    return [t.text for t in tokens]


def kinds(tokens):
    return [t.kind for t in tokens]


def test_words_keep_their_matras_nukta_and_chandrabindu():
    tokens = tokenize_line("कहाँ वो ज़रूर संस्कृति", 0)
    assert texts(tokens) == ["कहाँ", "वो", "ज़रूर", "संस्कृति"]
    assert set(kinds(tokens)) == {WORD}


def test_punctuation_marks_are_separate_tokens():
    tokens = tokenize_line("खूब, बहुत खूब! क्या? है।", 0)
    assert texts(tokens) == ["खूब", ",", "बहुत", "खूब", "!", "क्या", "?", "है", "।"]
    assert kinds(tokens).count(PUNCT) == 4


def test_hyphen_and_ellipsis_are_punctuation():
    tokens = tokenize_line("देखते-देखते… रुको-", 0)
    assert texts(tokens) == ["देखते", "-", "देखते", "…", "रुको", "-"]


def test_music_markers_are_their_own_tokens():
    tokens = tokenize_line("♪ सृष्टि से पहले ♪", 0)
    assert kinds(tokens) == [MUSIC, WORD, WORD, WORD, MUSIC]


def test_a_sound_tag_is_one_token_even_with_spaces_inside():
    tokens = tokenize_line("आओ [हवा चलने की आवाज़] चलो", 0)
    assert texts(tokens) == ["आओ", "[हवा चलने की आवाज़]", "चलो"]
    assert tokens[1].kind == TAG


def test_spacing_inside_a_tag_does_not_change_the_matching_form():
    one = tokenize_line("[मिट्टी खोदने की आवाज़]", 0)[0]
    two = tokenize_line("[मिट्टी  खोदने  की  आवाज़]", 0)[0]
    assert one.norm == two.norm
    assert one.text != two.text  # the original text is never altered


def test_spaces_between_words_do_not_create_tokens():
    single = tokenize_line("नहीं भी जानता", 0)
    double = tokenize_line("नहीं  भी   जानता", 0)
    assert [t.norm for t in single] == [t.norm for t in double]


def test_precomposed_and_decomposed_nukta_match():
    assert tokenize_line("क़ा", 0)[0].norm == tokenize_line("क़ा", 0)[0].norm


def test_spans_point_back_into_the_original_text():
    line = "वह  वो ,  है"
    for token in tokenize_line(line, 3):
        assert line[token.start : token.end] == token.text
        assert token.para == 3


def test_an_unclosed_bracket_is_just_punctuation():
    tokens = tokenize_line("आओ [चलो", 0)
    assert texts(tokens) == ["आओ", "[", "चलो"]
    assert tokens[1].kind == PUNCT


def test_tokenize_keeps_paragraph_numbers_across_blank_lines():
    tokens = tokenize(["एक", "", "दो तीन"])
    assert [(t.text, t.para) for t in tokens] == [("एक", 0), ("दो", 2), ("तीन", 2)]
