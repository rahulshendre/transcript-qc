# Sample pair

Two short made-up transcripts to try the tool with. The text is random plain Hindi words, not taken
from any episode, so they can be shared freely.

* `sample_B.docx` is the reference (File B): 40 clean lines.
* `sample_A.docx` is the transcript being scored (File A): B with a known number of mistakes put in.

| Category | Put in | Tool counts |
|---|---|---|
| Major | 5 (3 different words, 2 missing words) | 5 |
| Language | 4 spelling slips | 4 |
| Punctuation | 6 missing marks | 6 |
| CC | 3 different sound tags | 3 |
| Repeated | 1 (न written as ना five times) | 1 |
| Minor | 2 space slips | 2 |
| **Total** | **21** | **21** |

A also has things that must not count: ♪ song markers only in B, doubled spaces and invisible characters.

Try it:

```
python qc_compare.py --a examples/sample_A.docx --b examples/sample_B.docx --out out/sample_QC.docx
```

Or open the review screen (`python app.py`) and choose the two files.

`make_sample.py` writes both files again. `tests/test_sample.py` checks the counts above.
