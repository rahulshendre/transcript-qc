import csv
import dataclasses

import pytest
from docx import Document
from helpers import analysis, build, document_root, make_qc, w

from transcript_qc.accuracy import (
    EPISODE_50,
    Gap,
    format_table,
    gaps,
    parse_reference,
    total_within,
)
from transcript_qc.compare import compare_files, compare_paragraphs
from transcript_qc.count import analyse
from transcript_qc.report import COLUMNS, write_csv
from transcript_qc.revisions import comparable, revision_texts
from transcript_qc.rules import CATEGORIES, load_rules
from transcript_qc.summary import Details, details_from_name, summary_elements, summary_rows
from transcript_qc.writer import write_qc

MOVIES = {"BEK": "Bharat Ek Khoj"}


def sample():
    a = ["जल भी कहां था", "बहुत खूब", "आओ [हवा]", "उसके मामा के पोते", "ठीक है", "राम राज आया"]
    b = ["जल भी कहाँ था", "बहुत खूब।", "आओ [संगीत]", "उसके मामा", "ठीक है", "रामराज आया"]
    return a, b


# mistakes.csv ----------------------------------------------------------------

def read_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle))


def test_the_csv_has_the_agreed_columns_and_one_row_per_counted_mistake(tmp_path):
    result = analysis(*sample())
    path = tmp_path / "mistakes.csv"
    assert write_csv(result, path) == result.total == 5
    rows = read_rows(path)
    assert tuple(rows[0]) == COLUMNS == (
        "line_no", "a_text", "b_text", "category", "rule_id", "note",
    )
    assert len(rows) - 1 == result.total
    assert [r[3] for r in rows[1:]].count("Language") == result.counts["Language"]


def test_csv_rows_carry_the_texts_the_category_the_rule_and_a_reason(tmp_path):
    result = analysis(*sample())
    path = tmp_path / "mistakes.csv"
    write_csv(result, path)
    by_text = {r[1]: r for r in read_rows(path)[1:]}
    row = by_text["कहां"]
    assert (row[0], row[2], row[3], row[4]) == ("1", "कहाँ", "Language", "LANG_MARKS")
    assert row[5]


def test_the_csv_reads_back_hindi_correctly_and_opens_in_excel(tmp_path):
    path = tmp_path / "mistakes.csv"
    write_csv(analysis(*sample()), path)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # a BOM so Excel shows Devanagari


def test_ignored_and_repeated_copies_are_not_in_the_csv(tmp_path):
    a = ["वह आया", "वह गया", "वह बैठा", "सृष्टि"]
    b = ["बह आया", "बह गया", "बह बैठा", "♪ सृष्टि"]
    rules = dataclasses.replace(load_rules("default"), repeated_min=3)
    result = analyse(compare_paragraphs(a, b), rules)
    path = tmp_path / "mistakes.csv"
    write_csv(result, path)
    rows = read_rows(path)[1:]
    assert len(rows) == result.total
    assert any(r[3] == "Repeated" for r in rows)
    assert not any("♪" in r[2] for r in rows)   # the ignored song marker


def test_every_csv_row_names_a_rule(tmp_path):
    path = tmp_path / "mistakes.csv"
    write_csv(analysis(*sample()), path)
    assert all(r[4] for r in read_rows(path)[1:])


# the summary table -----------------------------------------------------------

def test_movie_writer_and_episode_come_from_a_s_file_name():
    d = details_from_name("LE1 BEK_50_Feltiv.sushila.docx", MOVIES)
    assert d == Details("Bharat Ek Khoj", "Sushila", "50")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("BEK EP-50_Sushila_LE1.docx", ("Bharat Ek Khoj", "", "50")),
        ("LE2 XYZ_7_Foo.mala.docx", ("XYZ", "Mala", "7")),
        ("notes.docx", ("", "", "")),
    ],
)
def test_other_file_name_shapes_do_not_break_it(name, expected):
    d = details_from_name(name, MOVIES)
    assert (d.movie, d.writer, d.episode) == expected


def test_flags_override_what_the_file_name_says():
    d = details_from_name(
        "LE1 BEK_50_Feltiv.sushila.docx", MOVIES, movie="Other", writer="Mala", episode="51"
    )
    assert d == Details("Other", "Mala", "51")


def test_counts_are_padded_to_two_digits_in_the_reviewers_layout():
    counts = dict(zip(CATEGORIES, (9, 12, 66, 2, 4, 4), strict=True))
    rows = summary_rows(Details("Bharat Ek Khoj", "Sushila", "50"), counts)
    assert rows == [
        [("Movie Name:", "Bharat Ek Khoj"), ("Written By:", "Sushila"), ("Episode:", "50")],
        [("Major Mistakes:", "09"), ("Language Mistakes:", "12"), ("Punctuation Mistakes:", "66")],
        [("Cc mistakes:", "02"), ("Repeated Mistakes:", "04"), ("Minor Mistakes:", "04")],
        [("Total Mistakes:", "97"), ("", ""), ("", "")],
    ]


def test_the_table_is_four_rows_by_three_columns_at_the_end_of_the_document(tmp_path):
    a, b = sample()
    a_path, b_path = build(tmp_path / "a.docx", a), build(tmp_path / "b.docx", b)
    comparison = compare_files(a_path, b_path)
    result = analyse(comparison, load_rules("strict"))
    out = tmp_path / "qc.docx"
    details = Details("Bharat Ek Khoj", "Sushila", "50")
    write_qc(a_path, comparison, out, append=summary_elements(details, result.counts))
    table = Document(str(out)).tables[0]
    assert (len(table.rows), len(table.columns)) == (4, 3)
    text = [[cell.text for cell in row.cells] for row in table.rows]
    assert text[0] == ["Movie Name: Bharat Ek Khoj", "Written By: Sushila", "Episode: 50"]
    assert text[1][0] == "Major Mistakes: 01"
    assert text[3][0] == "Total Mistakes: 05"
    body = document_root(out).find(w("body"))
    kinds = [c.tag.rsplit("}", 1)[1] for c in body]
    assert kinds[-3:] == ["tbl", "p", "sectPr"]


def test_the_table_does_not_disturb_reject_all_or_accept_all(tmp_path):
    a, b = sample()
    a_path, b_path = build(tmp_path / "a.docx", a), build(tmp_path / "b.docx", b)
    comparison = compare_files(a_path, b_path)
    out = tmp_path / "qc.docx"
    write_qc(
        a_path, comparison, out,
        append=summary_elements(Details("M", "W", "1"), analyse(comparison, load_rules()).counts),
    )
    rejected, accepted = revision_texts(out)
    assert rejected[: len(comparison.a_paragraphs)] == comparison.a_paragraphs
    assert comparable(accepted) == comparable(comparison.b_paragraphs)


def test_the_table_cells_use_the_reviewers_look(tmp_path):
    out, _, _ = make_qc(tmp_path, ["एक"], ["एक"])
    root = document_root(out)
    assert root.find(f".//{w('tbl')}") is None  # no table unless the summary is appended
    elements = summary_elements(Details("M", "W", "1"), dict.fromkeys(CATEGORIES, 0))
    cell = elements[0].find(f".//{w('tc')}")
    assert cell.find(f".//{w('tcBorders')}") is not None
    assert cell.find(f".//{w('rFonts')}").get(w("ascii")) == "Helvetica"


# comparing with the reviewer's table -----------------------------------------

def test_a_category_may_be_off_by_twenty_percent_or_three_whichever_is_larger():
    assert Gap("Major", 12, 9).within and not Gap("Major", 13, 9).within       # +/-3
    assert Gap("Punctuation", 79, 66).within and not Gap("Punctuation", 80, 66).within  # 13.2
    assert Gap("CC", 5, 2).within and not Gap("CC", 6, 2).within


def test_the_total_may_be_off_by_ten_percent():
    assert total_within(107, 97) and total_within(87, 97)
    assert not total_within(108, 97) and not total_within(86, 97)


def test_a_reference_is_ep50_or_six_numbers_in_a_fixed_order():
    assert parse_reference("ep50") == EPISODE_50
    assert parse_reference("1, 2,3,4,5,6")["Language"] == 2
    with pytest.raises(ValueError, match="six|6"):
        parse_reference("1,2,3")


def test_the_table_lists_each_category_the_total_and_whether_it_is_in_bounds():
    counts = {"Major": 9, "Language": 12, "Punctuation": 66, "CC": 2, "Repeated": 4, "Minor": 4}
    text = format_table(counts, EPISODE_50)
    assert text.count("yes") == 7 and text.count(" no (") == 0
    off = dict(counts, Major=50)
    assert [g.within for g in gaps(off, EPISODE_50)][0] is False
