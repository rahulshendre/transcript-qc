"""The tracked-change file for the real Episode 50. Skipped when the files are not present."""

import time
import zipfile
from pathlib import Path

import pytest
from docx import Document
from helpers import revision_text, w

from transcript_qc.compare import compare_files
from transcript_qc.revisions import comparable, revision_texts
from transcript_qc.writer import DOCUMENT_XML, write_qc

DATA = Path(__file__).resolve().parent.parent / "data" / "ep50"
A = DATA / "LE1 BEK_50_Feltiv.sushila.docx"
B = DATA / "LE2 BHARAT EK KHOJ_EP_50_Chandrakala.docx"

pytestmark = pytest.mark.skipif(not (A.is_file() and B.is_file()), reason="Episode 50 not found")


@pytest.fixture(scope="module")
def episode(tmp_path_factory):
    out = tmp_path_factory.mktemp("ep50") / "ep50_QC.docx"
    started = time.perf_counter()
    comparison = compare_files(A, B)
    stats = write_qc(A, comparison, out)
    return out, comparison, stats, time.perf_counter() - started


def root_of_bytes(data):
    from lxml import etree

    return etree.fromstring(data)


def root_of(path):
    with zipfile.ZipFile(path) as package:
        return root_of_bytes(package.read(DOCUMENT_XML))


def test_reject_all_gives_file_a_exactly(episode):
    out, comparison, _, _ = episode
    rejected, _ = revision_texts(out)
    assert rejected == comparison.a_paragraphs


def test_accept_all_gives_file_b_apart_from_spacing(episode):
    out, comparison, _, _ = episode
    _, accepted = revision_texts(out)
    assert comparable(accepted) == comparable(comparison.b_paragraphs)


def test_it_runs_well_inside_a_minute(episode):
    assert episode[3] < 60


def test_the_embedded_fonts_and_every_other_part_are_untouched(episode):
    out = episode[0]
    with zipfile.ZipFile(A) as a_zip, zipfile.ZipFile(out) as out_zip:
        assert a_zip.namelist() == out_zip.namelist()
        fonts = [n for n in a_zip.namelist() if n.startswith("word/fonts/")]
        assert len(fonts) == 9
        for name in a_zip.namelist():
            if name != DOCUMENT_XML:
                assert a_zip.read(name) == out_zip.read(name), name


def test_revisions_are_well_formed(episode):
    root = root_of(episode[0])
    marks = [e for e in root.iter() if e.tag in (w("ins"), w("del"))]
    ids = [e.get(w("id")) for e in marks]
    assert len(ids) == len(set(ids)) > 500
    assert {e.get(w("author")) for e in marks} == {"QC-Bot"}
    assert all(e.get(w("date")) for e in marks)
    for e in marks:
        text = revision_text(e)
        assert text.strip(), "a revision that only changes spacing"
        if e.tag == w("del"):
            assert not list(e.iter(w("t")))
        else:
            assert not list(e.iter(w("delText")))


def test_stats_match_the_document(episode):
    out, _, stats, _ = episode
    root = root_of(out)
    assert len(list(root.iter(w("ins")))) == stats.insertions
    assert len(list(root.iter(w("del")))) == stats.deletions
    changed = [p for p in root.iter(w("p")) if list(p.iter(w("ins"), w("del")))]
    assert len(changed) == stats.changed_paragraphs


def test_the_paragraph_count_and_unchanged_paragraphs_are_kept(episode):
    out, comparison, stats, _ = episode
    assert len(Document(str(out)).paragraphs) == len(comparison.a_paragraphs)
    assert stats.changed_paragraphs < len(comparison.a_paragraphs) / 2


def test_the_document_root_is_unchanged(episode):
    """Namespaces and the mc:Ignorable list must survive, or Word may ask to repair the file."""
    with zipfile.ZipFile(A) as source:
        before = root_of_bytes(source.read(DOCUMENT_XML))
    after = root_of(episode[0])
    assert after.tag == before.tag
    assert dict(after.attrib) == dict(before.attrib)
    assert after.nsmap == before.nsmap
    ignorable = after.get("{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable")
    assert all(prefix in after.nsmap for prefix in ignorable.split())


def test_the_xml_declaration_is_kept(episode):
    with zipfile.ZipFile(episode[0]) as package:
        head = package.read(DOCUMENT_XML)[:80]
    assert head.startswith(b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>")
