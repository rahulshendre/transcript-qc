"""Files the tool should refuse or warn about, not crash on or quietly mis-read."""

import pytest
from docx import Document
from helpers import build, make_qc

from transcript_qc.cli import main
from transcript_qc.reader import InputError, docx_warnings, read_paragraphs

LINES = ["नमस्ते दुनिया कैसे हो", "", "मैं ठीक हूँ।"]


def test_a_file_that_is_not_a_docx_is_refused_with_a_plain_message(tmp_path):
    junk = tmp_path / "junk.docx"
    junk.write_bytes(b"not a zip at all")
    with pytest.raises(InputError, match=r"junk\.docx is not a Word .docx file"):
        read_paragraphs(junk)


def test_a_file_with_tracked_changes_is_refused(tmp_path):
    qc, _, _ = make_qc(tmp_path, ["जल भी कहां था"], ["जल भी कहाँ था"])
    with pytest.raises(InputError, match=r"qc\.docx has tracked changes.*Accept or reject"):
        read_paragraphs(qc)


def test_a_clean_file_reads_as_before(tmp_path):
    path = build(tmp_path / "a.docx", LINES)
    assert read_paragraphs(path)[-3:] == LINES


def test_tables_and_text_boxes_are_reported_not_silently_skipped(tmp_path):
    path = build(tmp_path / "a.docx", LINES)
    doc = Document(str(path))
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "तालिका"
    doc.save(path)
    warnings = docx_warnings(path)
    assert len(warnings) == 1
    assert "a.docx has 1 table" in warnings[0] and "not compared" in warnings[0]


def test_a_plain_file_has_no_warnings(tmp_path):
    assert docx_warnings(build(tmp_path / "a.docx", LINES)) == []


@pytest.fixture
def pair(tmp_path):
    return build(tmp_path / "a.docx", LINES), build(tmp_path / "b.docx", LINES)


def test_cli_says_a_corrupt_file_is_corrupt(pair, tmp_path, capsys):
    a, _ = pair
    junk = tmp_path / "junk.docx"
    junk.write_bytes(b"nope")
    assert main(["--a", str(a), "--b", str(junk)]) == 2
    assert "junk.docx is not a Word .docx file" in capsys.readouterr().err


def test_cli_refuses_an_empty_file_a_or_b(pair, tmp_path, capsys):
    a, _ = pair
    empty = build(tmp_path / "empty.docx", [])
    assert main(["--a", str(empty), "--b", str(a)]) == 2
    assert "empty.docx has no text" in capsys.readouterr().err
    assert main(["--a", str(a), "--b", str(empty)]) == 2
    assert "empty.docx has no text" in capsys.readouterr().err


def test_cli_prints_a_warning_for_a_table(pair, tmp_path, capsys):
    a, b = pair
    doc = Document(str(a))
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "तालिका"
    doc.save(a)
    assert main(["--a", str(a), "--b", str(b)]) == 0
    assert "warning: a.docx has 1 table" in capsys.readouterr().err
