"""Write the made-up sample pair in this folder: python examples/make_sample.py

The text is random plain Hindi words, not from any episode. B is the clean reference and A is B
with a known number of each mistake put in, so the tool's counts can be checked against the truth.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tests import helpers, synthetic  # noqa: E402

PLAN = synthetic.Plan(major_different=3, major_missing=2, language=4, punctuation=6, cc=3, minor=2,
            repeat_pair=("न", "ना"), repeat_times=5, lines=40)
SEED = 7


def main() -> None:
    pair = synthetic.build(PLAN, SEED)
    helpers.build(HERE / "sample_A.docx", pair.a)
    helpers.build(HERE / "sample_B.docx", pair.b)
    print("expected:", PLAN.expected())


if __name__ == "__main__":
    main()
