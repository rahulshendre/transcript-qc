from docx import Document

from transcript_qc.reader import read_paragraphs


def test_reads_every_paragraph_including_blank_ones(tmp_path):
    path = tmp_path / "a.docx"
    doc = Document()
    for text in ["पहली पंक्ति", "", "दूसरी पंक्ति"]:
        doc.add_paragraph(text)
    doc.save(path)
    lines = read_paragraphs(path)
    assert lines[-3:] == ["पहली पंक्ति", "", "दूसरी पंक्ति"]
