import zipfile
from datetime import datetime

import pytest
from docx import Document
from helpers import build, document_root, make_qc, revision_text, revisions, w

from transcript_qc.compare import compare_files
from transcript_qc.revisions import comparable, match_ratio, revision_texts, round_trip
from transcript_qc.writer import DEFAULT_AUTHOR, write_qc


def check_round_trip(out, comparison):
    """Reject All gives A exactly; Accept All gives B, spacing aside."""
    rejected, accepted = revision_texts(out)
    assert rejected == comparison.a_paragraphs
    assert comparable(accepted) == comparable(comparison.b_paragraphs)
    return rejected, accepted


def test_identical_files_give_a_document_with_no_revisions(tmp_path):
    out, comparison, stats = make_qc(tmp_path, ["एक दो", "", "तीन"], ["एक दो", "", "तीन"])
    assert (stats.insertions, stats.deletions, stats.changed_paragraphs) == (0, 0, 0)
    assert revisions(out) == []
    check_round_trip(out, comparison)


def test_a_replacement_is_a_delete_followed_by_an_insert(tmp_path):
    out, comparison, stats = make_qc(tmp_path, ["जल भी कहां था"], ["जल भी कहाँ था"])
    assert (stats.deletions, stats.insertions) == (1, 1)
    deleted, inserted = revisions(out)
    assert (deleted.tag, revision_text(deleted)) == (w("del"), "कहां")
    assert (inserted.tag, revision_text(inserted)) == (w("ins"), "कहाँ")
    assert deleted.getnext() is inserted
    rejected, accepted = check_round_trip(out, comparison)
    assert accepted[-1] == "जल भी कहाँ था"


def test_deleted_text_is_in_deltext_and_inserted_text_in_t(tmp_path):
    out, _, _ = make_qc(tmp_path, ["उसके मामा के पोते"], ["उसके मामा हैं"])
    for element in revisions(out):
        if element.tag == w("del"):
            assert list(element.iter(w("delText"))) and not list(element.iter(w("t")))
        else:
            assert list(element.iter(w("t"))) and not list(element.iter(w("delText")))


def test_a_missing_word_is_deleted_and_an_extra_word_is_inserted(tmp_path):
    out, comparison, _ = make_qc(tmp_path, ["उसके मामा के पोते"], ["उसके मामा"])
    check_round_trip(out, comparison)
    out2, comparison2, _ = make_qc(tmp_path, ["उसके मामा"], ["उसके मामा के पोते"])
    _, accepted = check_round_trip(out2, comparison2)
    assert accepted[-1] == "उसके मामा के पोते"


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("बहुत खूब", "बहुत खूब।", "बहुत खूब।"),
        ("खूब, बहुत", "खूब! बहुत", "खूब! बहुत"),
        ("खूब बहुत", "खूब ज़रा बहुत", "खूब ज़रा बहुत"),
        ("सृष्टि से पहले", "♪ सृष्टि से पहले ♪", "♪ सृष्टि से पहले ♪"),
        ("आओ [हवा चलने की आवाज़] चलो", "आओ [नाटकीय संगीत] चलो", "आओ [नाटकीय संगीत] चलो"),
        ("सत नहीं था, असत", "♪ सत नहीं था ♪ ♪ असत", "♪ सत नहीं था ♪ ♪ असत"),
        ("जल भी कहां, था", "जल भी कहाँ, था", "जल भी कहाँ, था"),
        ("क्या कहां?", "क्या कहाँ?", "क्या कहाँ?"),
        ("उंचे आकाश", "ऊँचे, आकाश", "ऊँचे, आकाश"),
    ],
)
def test_accepted_text_reads_naturally(tmp_path, a, b, expected):
    out, comparison, _ = make_qc(tmp_path, [a], [b])
    rejected, accepted = check_round_trip(out, comparison)
    assert accepted[-1] == expected


def test_double_spaces_and_line_breaks_are_not_tracked(tmp_path):
    out, comparison, _ = make_qc(
        tmp_path,
        ["सबसे अहम पहलू था-औरतों का योगदान।"],
        ["सबसे  अहम  पहलू  था-", "", "औरतों  का  योगदान।"],
    )
    assert revisions(out) == []


def test_a_change_across_a_line_break_still_round_trips(tmp_path):
    out, comparison, _ = make_qc(
        tmp_path, ["सबसे अहम", "", "पहलू था यही"], ["सबसे बड़ा पहलू था वही"]
    )
    check_round_trip(out, comparison)


def test_a_whole_new_line_in_b_keeps_its_punctuation_in_order(tmp_path):
    # the new line "पटेल साहब!" and its "!" must land together, not on different lines
    a = ["क्या हुआ?", "", "पुलिस की गाड़ी है।"]
    b = ["क्या हुआ?", "", "पटेल साहब!", "", "पुलिस की गाड़ी है।"]
    out, comparison, _ = make_qc(tmp_path, a, b)
    _, accepted = check_round_trip(out, comparison)
    assert "".join(accepted).replace(" ", "") == "क्या हुआ?पटेल साहब!पुलिस की गाड़ी है।".replace(" ", "")


def test_formatting_is_kept_on_unchanged_text_and_copied_to_changes(tmp_path):
    a = [[("जल भी ", {"bold": True}), ("कहां", {"italic": True}), (" था", {})]]
    out, comparison, _ = make_qc(tmp_path, a, ["जल भी कहाँ था"])
    root = document_root(out)
    deleted = root.find(f".//{w('del')}")
    inserted = root.find(f".//{w('ins')}")
    assert deleted.find(f".//{w('rPr')}/{w('i')}") is not None  # the deleted word was italic
    assert inserted.find(f".//{w('rPr')}/{w('i')}") is not None  # a replacement keeps that look
    assert inserted.find(f".//{w('rPr')}/{w('b')}") is None
    first_kept = root.find(f".//{w('p')}/{w('r')}")
    assert first_kept.find(f"{w('rPr')}/{w('b')}") is not None
    check_round_trip(out, comparison)


def test_added_text_takes_the_formatting_of_the_text_before_it(tmp_path):
    a = [[("खूब ", {"bold": True}), ("बहुत", {"italic": True})]]
    out, comparison, _ = make_qc(tmp_path, a, ["खूब बहुत।"])
    inserted = revisions(out)[0]
    assert revision_text(inserted) == "।"
    assert inserted.find(f".//{w('rPr')}/{w('i')}") is not None
    assert inserted.find(f".//{w('rPr')}/{w('b')}") is None
    check_round_trip(out, comparison)


def test_a_deletion_that_spans_two_runs_keeps_both_runs_formatting(tmp_path):
    a = [[("वही सच ", {"bold": True}), ("मुझमें जानता", {"italic": True})]]
    out, comparison, _ = make_qc(tmp_path, a, ["वही सचमुच में जानता"])
    deleted = revisions(out)[0]
    runs = deleted.findall(w("r"))
    assert [revision_text(r) for r in runs] == ["सच ", "मुझमें"]
    assert runs[0].find(f"{w('rPr')}/{w('b')}") is not None
    assert runs[1].find(f"{w('rPr')}/{w('i')}") is not None
    check_round_trip(out, comparison)


def test_revision_ids_are_unique_and_carry_author_and_date(tmp_path):
    out, _, _ = make_qc(
        tmp_path,
        ["एक दो तीन, चार", "", "पाँच छह"],
        ["एक तो तीन! चार सात", "", "पाँच"],
        author="Reviewer",
        date="2026-11-24T09:30:00Z",
    )
    found = revisions(out)
    assert len(found) >= 4
    ids = [e.get(w("id")) for e in found]
    assert len(set(ids)) == len(ids)
    assert all(i.isdigit() for i in ids)
    assert {e.get(w("author")) for e in found} == {"Reviewer"}
    assert {e.get(w("date")) for e in found} == {"2026-11-24T09:30:00Z"}


def test_default_author_and_a_real_timestamp(tmp_path):
    out, _, _ = make_qc(tmp_path, ["जल भी कहां था"], ["जल भी कहाँ था"])
    for element in revisions(out):
        assert element.get(w("author")) == DEFAULT_AUTHOR == "QC-Bot"
        stamp = datetime.strptime(element.get(w("date")), "%Y-%m-%dT%H:%M:%SZ")
        assert stamp.year >= 2026


def test_spaces_at_the_edges_of_text_are_preserved(tmp_path):
    out, _, _ = make_qc(tmp_path, ["खूब बहुत"], ["खूब ज़रा बहुत"])
    for node in document_root(out).iter(w("t"), w("delText")):
        assert node.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve"


def test_unchanged_paragraphs_are_left_exactly_as_they_were(tmp_path):
    a = ["पहली पंक्ति", "", "जल भी कहां था", "", "आख़िरी पंक्ति"]
    out, comparison, _ = make_qc(tmp_path, a, ["पहली पंक्ति", "", "जल भी कहाँ था", "", "आख़िरी पंक्ति"])
    from lxml import etree

    before = [etree.tostring(p) for p in document_root(tmp_path / "a.docx").iter(w("p"))]
    after = [etree.tostring(p) for p in document_root(out).iter(w("p"))]
    changed = [i for i, (x, y) in enumerate(zip(before, after, strict=True)) if x != y]
    assert len(before) == len(after)
    assert len(changed) == 1  # only the paragraph with the spelling change


def test_every_other_part_of_the_package_is_byte_identical(tmp_path):
    out, _, _ = make_qc(tmp_path, ["जल भी कहां था"], ["जल भी कहाँ था"])
    with zipfile.ZipFile(tmp_path / "a.docx") as a_zip, zipfile.ZipFile(out) as out_zip:
        assert [i.filename for i in a_zip.infolist()] == [i.filename for i in out_zip.infolist()]
        for name in a_zip.namelist():
            if name != "word/document.xml":
                assert a_zip.read(name) == out_zip.read(name), name
        assert a_zip.read("word/document.xml") != out_zip.read("word/document.xml")


def test_the_output_opens_in_python_docx_and_has_a_valid_zip(tmp_path):
    out, _, _ = make_qc(tmp_path, ["जल भी कहां था", "", "एक दो"], ["जल भी कहाँ था", "", "एक"])
    assert zipfile.ZipFile(out).testzip() is None
    assert Document(str(out)).paragraphs  # loads without error


def test_round_trip_check_notices_a_damaged_document(tmp_path):
    out, comparison, _ = make_qc(tmp_path, ["जल भी कहां था"], ["जल भी कहाँ था"])
    assert round_trip(out, comparison.a_paragraphs, comparison.b_paragraphs) == (1.0, 1.0)
    # a document where the insertion was lost no longer matches B
    broken = tmp_path / "broken.docx"
    with zipfile.ZipFile(out) as src, zipfile.ZipFile(broken, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "word/document.xml":
                data = data.replace("कहाँ".encode(), b"x")
            dst.writestr(info.filename, data)
    reject, accept = round_trip(broken, comparison.a_paragraphs, comparison.b_paragraphs)
    assert reject == 1.0
    assert accept < 1.0


def test_match_ratio_ignores_spacing_and_unicode_form():
    assert match_ratio(["क ख  ग"], ["कखग"]) == 1.0
    assert match_ratio(["क़ा"], ["क़ा"]) == 1.0
    assert match_ratio(["कखग"], ["कखघ"]) < 1.0


def test_write_qc_does_not_touch_its_input(tmp_path):
    a_path = build(tmp_path / "a.docx", ["जल भी कहां था"])
    b_path = build(tmp_path / "b.docx", ["जल भी कहाँ था"])
    before = a_path.read_bytes()
    write_qc(a_path, compare_files(a_path, b_path), tmp_path / "qc.docx")
    assert a_path.read_bytes() == before
