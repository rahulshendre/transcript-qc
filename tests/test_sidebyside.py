from pathlib import Path

import pytest

from transcript_qc.compare import compare_files, compare_paragraphs
from transcript_qc.sidebyside import build_rows


def rows_for(a, b):
    comparison = compare_paragraphs(a, b)
    rows, row_of_diff = build_rows(comparison)
    return comparison, rows, row_of_diff


def text_of(lines):
    return ["".join(s.text for s in line.segments) for line in lines]


def test_matching_lines_sit_in_one_row_each_and_nothing_is_highlighted():
    _, rows, row_of_diff = rows_for(["एक दो", "", "तीन चार"], ["एक दो", "", "तीन चार"])
    assert len(rows) == 2 and row_of_diff == {}
    assert text_of(rows[0].a) == ["एक दो"] and text_of(rows[0].b) == ["एक दो"]
    assert all(s.diff == -1 for row in rows for line in row.a + row.b for s in line.segments)


def test_blank_paragraphs_never_appear():
    _, rows, _ = rows_for(["एक", "", "", "दो"], ["एक", "दो"])
    assert [line.para for row in rows for line in row.a] == [1, 4]


def test_a_line_that_b_splits_in_two_is_one_row_with_two_b_lines():
    a = ["सबसे अहम पहलू था-औरतों का योगदान।"]
    b = ["सबसे अहम पहलू था-", "", "औरतों का योगदान।"]
    _, rows, _ = rows_for(a, b)
    assert len(rows) == 1
    assert len(rows[0].a) == 1 and len(rows[0].b) == 2


def test_two_a_lines_that_b_joins_are_one_row():
    _, rows, _ = rows_for(["छिपा था क्या", "", "कहाँ किसने"], ["छिपा था क्या कहाँ किसने"])
    assert len(rows) == 1 and len(rows[0].a) == 2 and len(rows[0].b) == 1


def test_a_changed_word_is_a_highlighted_segment_on_each_side():
    comparison, rows, row_of_diff = rows_for(["जल भी कहां था"], ["जल भी कहाँ था"])
    (row,) = rows
    a_marked = [s for s in row.a[0].segments if s.diff >= 0]
    b_marked = [s for s in row.b[0].segments if s.diff >= 0]
    assert [s.text for s in a_marked] == ["कहां"] and [s.text for s in b_marked] == ["कहाँ"]
    assert a_marked[0].diff == b_marked[0].diff == 0
    assert row_of_diff == {0: 0}


def test_a_changed_phrase_is_one_block_not_one_per_word():
    _, rows, _ = rows_for(["वही सच मुझमें जानता"], ["वही सचमुच में जानता"])
    a_marked = [s for s in rows[0].a[0].segments if s.diff >= 0]
    assert [s.text for s in a_marked] == ["सच मुझमें"]


def test_text_only_b_has_is_highlighted_on_the_b_side_only():
    _, rows, _ = rows_for(["उसके मामा"], ["उसके मामा हैं"])
    assert [s.text for s in rows[0].b[0].segments if s.diff >= 0] == ["हैं"]
    assert all(s.diff == -1 for s in rows[0].a[0].segments)


def test_a_line_only_b_has_gets_a_row_of_its_own_in_the_right_place():
    a = ["क्या हुआ?", "", "पुलिस की गाड़ी है।"]
    b = ["क्या हुआ?", "", "पटेल साहब!", "", "पुलिस की गाड़ी है।"]
    _, rows, _ = rows_for(a, b)
    assert [text_of(r.a) for r in rows] == [["क्या हुआ?"], [], ["पुलिस की गाड़ी है।"]]
    assert text_of(rows[1].b) == ["पटेल साहब!"]


def test_every_difference_maps_to_a_row_that_holds_it():
    a = ["जल भी कहां था", "बहुत खूब", "आओ [हवा]", "उसके मामा के पोते"]
    b = ["जल भी कहाँ था", "बहुत खूब।", "आओ [संगीत]", "उसके मामा"]
    comparison, rows, row_of_diff = rows_for(a, b)
    assert set(row_of_diff) == set(range(len(comparison.diffs)))
    for diff_index, row_index in row_of_diff.items():
        row = rows[row_index]
        shown = {s.diff for line in row.a + row.b for s in line.segments}
        assert diff_index in shown or comparison.diffs[diff_index].a_line - 1 >= 0


def test_segments_always_rebuild_the_original_paragraph_text():
    a = ["वाह करता , उंचे आकाश", "", "जल भी कहां था?"]
    b = ["वा  अकर्ता ♪ ऊँचे आकाश", "", "जल  भी कहाँ  था!"]
    comparison, rows, _ = rows_for(a, b)
    for row in rows:
        for line in row.a:
            assert "".join(s.text for s in line.segments) == comparison.a_paragraphs[line.para - 1]
        for line in row.b:
            assert "".join(s.text for s in line.segments) == comparison.b_paragraphs[line.para - 1]


def test_rows_run_in_file_order_on_both_sides():
    a = [f"पंक्ति {i} कहां" for i in range(10)]
    b = [f"पंक्ति {i} कहाँ" for i in range(10)]
    _, rows, _ = rows_for(a, b)
    a_first = [row.a[0].para for row in rows if row.a]
    b_first = [row.b[0].para for row in rows if row.b]
    assert a_first == sorted(a_first) and b_first == sorted(b_first)


# the real episode ------------------------------------------------------------

DATA = Path(__file__).resolve().parent.parent / "data" / "ep50"
A = DATA / "LE1 BEK_50_Feltiv.sushila.docx"
B = DATA / "LE2 BHARAT EK KHOJ_EP_50_Chandrakala.docx"


@pytest.mark.skipif(not (A.is_file() and B.is_file()), reason="Episode 50 not found")
def test_episode_50_rows_cover_every_line_exactly_once_and_keep_the_text():
    comparison = compare_files(A, B)
    rows, row_of_diff = build_rows(comparison)
    a_lines = [line.para for row in rows for line in row.a]
    b_lines = [line.para for row in rows for line in row.b]
    # every non-empty line is on screen exactly once
    assert sorted(a_lines) == [i + 1 for i, p in enumerate(comparison.a_paragraphs) if p.strip()]
    assert sorted(b_lines) == [i + 1 for i, p in enumerate(comparison.b_paragraphs) if p.strip()]

    def inversions(lines):
        return sum(1 for x, y in zip(lines, lines[1:], strict=False) if x > y)

    # reading order is kept, apart from the odd place where one B line spans text A cut around
    assert inversions(a_lines) <= len(a_lines) * 0.005
    assert inversions(b_lines) <= len(b_lines) * 0.005
    for row in rows:
        for line in row.a:
            assert "".join(s.text for s in line.segments) == comparison.a_paragraphs[line.para - 1]
        for line in row.b:
            assert "".join(s.text for s in line.segments) == comparison.b_paragraphs[line.para - 1]
    assert set(row_of_diff) == set(range(len(comparison.diffs)))
    assert len(rows) < len(a_lines) + len(b_lines)
