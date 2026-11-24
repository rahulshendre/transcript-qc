import csv

import pytest
from docx import Document
from helpers import build

from transcript_qc.cli import main
from transcript_qc.revisions import comparable, revision_texts

A = ["जल भी कहां था", "बहुत खूब", "आओ [हवा]", "उसके मामा के पोते", "ठीक है", "राम राज आया"]
B = ["जल भी कहाँ था", "बहुत खूब।", "आओ [संगीत]", "उसके मामा", "ठीक है", "रामराज आया"]


@pytest.fixture
def files(tmp_path):
    a = build(tmp_path / "LE1 BEK_50_Feltiv.sushila.docx", A)
    b = build(tmp_path / "LE2 BEK_50_Chandrakala.docx", B)
    return a, b, tmp_path


def run(capsys, *args):
    code = main([str(x) for x in args])
    return code, capsys.readouterr()


def test_it_prints_the_counts_and_the_total(files, capsys):
    a, b, _ = files
    code, out = run(capsys, "--a", a, "--b", b, "--rules", "strict")
    assert code == 0
    expected = "Major 01 | Language 01 | Punctuation 01 | CC 01 | Repeated 00 | Minor 01"
    assert f"mistakes: {expected}" in out.out
    assert "Total 05" in out.out


def test_out_writes_the_qc_document_and_the_csv_beside_it(files, capsys):
    a, b, tmp = files
    out = tmp / "result" / "x_QC.docx"
    out.parent.mkdir()
    code, printed = run(capsys, "--a", a, "--b", b, "--out", out, "--rules", "strict")
    assert code == 0
    assert out.is_file()
    csv_path = out.parent / "mistakes.csv"
    assert csv_path.is_file()
    assert "wrote" in printed.out and "5 rows" in printed.out
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        assert len(list(csv.reader(handle))) == 6   # header + five mistakes
    assert "round trip: Reject All matches A 100.00%, Accept All matches B 100.00%" in printed.out


def test_the_csv_path_can_be_chosen(files, capsys):
    a, b, tmp = files
    run(capsys, "--a", a, "--b", b, "--out", tmp / "q.docx", "--csv", tmp / "mine.csv")
    assert (tmp / "mine.csv").is_file()
    assert not (tmp / "mistakes.csv").exists()


def test_the_summary_table_takes_its_details_from_the_file_name(files, capsys):
    a, b, tmp = files
    out = tmp / "q.docx"
    run(capsys, "--a", a, "--b", b, "--out", out, "--rules", "strict")
    table = Document(str(out)).tables[0]
    cells = [c.text for c in table.rows[0].cells]
    assert cells == ["Movie Name: Bharat Ek Khoj", "Written By: Sushila", "Episode: 50"]
    assert table.rows[3].cells[0].text == "Total Mistakes: 05"


def test_flags_override_the_details_and_the_author(files, capsys):
    a, b, tmp = files
    out = tmp / "q.docx"
    run(capsys, "--a", a, "--b", b, "--out", out, "--movie", "Other Show", "--writer", "Mala",
        "--episode", "7", "--author", "Reviewer")
    table = Document(str(out)).tables[0]
    assert [c.text for c in table.rows[0].cells] == [
        "Movie Name: Other Show", "Written By: Mala", "Episode: 7",
    ]
    from helpers import revisions

    assert {e.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author")
            for e in revisions(out)} == {"Reviewer"}


def test_the_qc_document_still_round_trips_with_the_table_in_it(files, capsys):
    a, b, tmp = files
    out = tmp / "q.docx"
    run(capsys, "--a", a, "--b", b, "--out", out)
    rejected, accepted = revision_texts(out)
    assert rejected[: len(A)] == A
    assert comparable(accepted) == comparable(B)


def test_reference_prints_the_comparison_table(files, capsys):
    a, b, _ = files
    code, out = run(capsys, "--a", a, "--b", b, "--reference", "ep50")
    assert code == 0
    assert "within bound" in out.out and "Total" in out.out


def test_a_profile_or_a_rules_file_can_be_chosen(files, capsys, tmp_path):
    a, b, _ = files
    _, strict = run(capsys, "--a", a, "--b", b, "--rules", "strict")
    _, default = run(capsys, "--a", a, "--b", b, "--rules", "default")
    assert "CC 01" in strict.out
    assert "CC 01" in default.out   # [हवा] -> [संगीत] changes on both sides, so it still counts


def test_a_missing_input_is_reported_not_crashed_on(files, capsys, tmp_path):
    a, _, _ = files
    code, out = run(capsys, "--a", a, "--b", tmp_path / "nope.docx")
    assert code == 2 and "not found" in out.err


def test_bad_rules_or_a_bad_reference_are_reported(files, capsys, tmp_path):
    a, b, _ = files
    code, out = run(capsys, "--a", a, "--b", b, "--rules", tmp_path / "missing.yaml")
    assert code == 2 and "error" in out.err
    code, out = run(capsys, "--a", a, "--b", b, "--reference", "1,2")
    assert code == 2 and "error" in out.err


def test_show_diff_lists_the_differences_with_their_lines(files, capsys):
    a, b, tmp = files
    _, out = run(capsys, "--a", a, "--b", b, "--out", tmp / "q.docx", "--show-diff", "--no-color")
    assert "A:1" in out.out and "[कहां] -> [कहाँ]" in out.out
