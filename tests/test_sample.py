"""The made-up sample pair in examples/ gives the counts its README promises."""

from pathlib import Path

from transcript_qc.compare import compare_files
from transcript_qc.count import analyse
from transcript_qc.rules import load_rules

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_the_sample_pair_gives_the_counts_that_were_put_in():
    result = compare_files(EXAMPLES / "sample_A.docx", EXAMPLES / "sample_B.docx")
    counts = analyse(result, load_rules("default")).counts
    assert counts == {"Major": 5, "Language": 4, "Punctuation": 6, "CC": 3, "Repeated": 1, "Minor": 2}
