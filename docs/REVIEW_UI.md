# Review screen (M4)

A reviewer uploads transcript A and reference B, sees every difference side by side, confirms,
re-labels or rejects each counted mistake, watches the counts move, and only then exports the QC
document. The engine does the comparing and counting. The reviewer keeps the final say.

## Run it

```
pip install -e .          # once
python app.py             # opens http://127.0.0.1:8765
```

Needs only Python. The page is built and shipped inside the package (`transcript_qc/web/static`),
with Noto Sans Devanagari bundled, so nothing is fetched from the internet. Reviews are saved in
`~/Transcript QC/sessions` (change it with `--sessions-dir` or `TRANSCRIPT_QC_HOME`).

To change the screen: `cd frontend && npm install && npm run build` (writes into the package).
`npm test` runs the front-end unit tests.

## How a review goes

1. **Start.** Drop File A and File B. Movie, writer and episode are filled from A's file name and
   can be edited. Compare takes about a second for Episode 50. A saved review of the same two files
   is brought back where it stopped.
2. **Scorecard.** Six category counts and the total. Each card shows the reviewed number and, once it
   differs, the engine's number struck through next to it. Clicking a card lists exactly the mistakes
   behind that number.
3. **Check each mistake.** Selecting one scrolls the side-by-side view to its line and shows the A and B
   text, the category, and why the tool chose it in plain words. Red words are only in A, green
   words only in B. The list is filtered by All, Pending, Done, Rejected or Ignored, and can be sorted by
   line number, category or least sure first. The rule id for each mistake is in the CSV, not on the screen.
4. **Decide.** Four buttons in the right-hand panel: Confirm, Change category (opens the six types),
   Not a mistake, and Add a note. Undo appears once a decision is made. The counts update at once.
5. **Repeated mistakes** list every occurrence with its line. Confirm the group, or split off
   occurrences that are really different mistakes.
6. **Catch what the engine missed.** The Ignored filter lists differences the engine did not count
   (song markers, one-sided tags, line-break marks, long cuts). Count any of them with P. Select text in
   the side-by-side view and press 1 to 6 to add a mistake of your own.
7. **Export.** QC .docx (every difference tracked, summary table from the reviewed counts) and CSV
   (every mistake with engine category, final category, status and note; the rows marked
   `counted=yes` are exactly the rows behind the table). If anything is pending the screen asks first.

## Keyboard

| Key | Does |
|---|---|
| J / K, arrows | next / previous mistake |
| Enter | confirm: the engine was right (counts an ignored difference) |
| 1 to 6 | category: Major, Language, Punctuation, CC, Repeated, Minor |
| X | not a mistake (stays under Rejected) |
| N | add a note (Ctrl+Enter to finish) |
| U | undo the decision, back to pending |
| P | count an ignored difference |
| select text, then 1 to 6 | add a mistake the engine missed |
| Ctrl+S | save now (it also saves after every decision) |
| ? | help |

After a decision the screen moves to the next pending mistake.

## What is saved

Every decision is applied on the server, written to `state.json` and appended to
`decisions.jsonl` (time, action, what changed) in the review's folder. `GET
/api/sessions/<id>/log` returns the same log. Decisions are matched back to the mistakes by a
stable key, so a review still restores if the rules are tuned; any saved decision whose mistake no
longer exists is reported, not lost silently.

## Tests

* `tests/test_review.py`, `test_sidebyside.py`, `test_api.py`: the logic, the rows and the HTTP API.
* `tests/test_e2e_review.py`: drives Chrome like a reviewer (keyboard only, live counts, exports that
  match the screen, save and restore, 1366 x 768 layout, no internet). Skipped if no browser starts;
  `TRANSCRIPT_QC_SKIP_E2E=1` skips it on purpose.
* `frontend/src/model.test.js`: filtering, sorting, keyboard mapping and merging in the browser code.

## Limits

* Opened in Chrome only. Word has not been used to open the exported .docx (none installed here).
* One reviewer at a time on one computer; there are no logins.
* A passage where every line differs (the opening verse) is one very tall row. The row stays
  readable, but moving inside it is by scrolling.
* The reviewer test in the brief (a QC reviewer verifies Episode 50 with the keyboard alone, without
  help) still needs a real reviewer. The scripted version of it passes.
