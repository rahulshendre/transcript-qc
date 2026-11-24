"""Smoke test on the real Episode 50 files. Skipped when the files are not present."""

import time
from pathlib import Path

import pytest

from transcript_qc.compare import compare_files

DATA = Path(__file__).resolve().parent.parent / "data" / "ep50"
A = DATA / "LE1 BEK_50_Feltiv.sushila.docx"
B = DATA / "LE2 BHARAT EK KHOJ_EP_50_Chandrakala.docx"

pytestmark = pytest.mark.skipif(not (A.is_file() and B.is_file()), reason="Episode 50 not found")


def test_episode_50_aligns_quickly_and_sanely():
    started = time.perf_counter()
    result = compare_files(A, B)
    elapsed = time.perf_counter() - started
    assert elapsed < 60
    assert 300 < len(result.diffs) < 800
    assert all(d.a or d.b for d in result.diffs)
    # a known spelling change from the brief pairs up as one replace
    pairs = {(d.a_text, d.b_text) for d in result.diffs if d.tag == "replace"}
    assert ("कहां", "कहाँ") in pairs


def test_episode_50_has_no_spacing_only_differences():
    result = compare_files(A, B)
    for d in result.diffs:
        assert d.a_text.split() != d.b_text.split()
