# Accuracy note: Episode 50

Bharat Ek Khoj, Episode 50. File A is Sushila's transcript, file B is Chandrakala's corrected one.
The reviewer's table is Major 9, Language 12, Punctuation 66, CC 2, Repeated 4, Minor 4, total 97.

## Result

| | Major | Language | Punctuation | CC | Repeated | Minor | Total |
|---|---|---|---|---|---|---|---|
| Reviewer | 9 | 12 | 66 | 2 | 4 | 4 | 97 |
| Allowed range | 6 to 12 | 9 to 15 | 53 to 79 | 0 to 5 | 1 to 7 | 1 to 7 | 87 to 107 |
| Tool, the brief's rules literally (`--rules strict`) | 65 | 19 | 19 | 44 | 46 | 5 | 198 |
| Tool, tuned rules (default `rules.yaml`) | 52 | 29 | 66 | 10 | 6 | 11 | 174 |

Tuned rules land in range for **Punctuation (66) and Repeated (6)**. Major, Language, CC, Minor and the
total are out of range. **The Episode 50 acceptance bounds are not met.**

```
python qc_compare.py --a "LE1 BEK_50_Feltiv.sushila.docx" --b "LE2 BHARAT EK KHOJ_EP_50_Chandrakala.docx" \
    --out out/ep50_QC.docx --reference ep50                # tuned rules
python qc_compare.py ... --rules strict --reference ep50   # the brief's rules literally
```

## Why the gap

The reviewer's own file tracks **687 changes** (363 word, 150 song marker, 61 sound tag, 113 punctuation)
and counts **97**. About 86 percent of what the reviewer saw was not counted, and the file has no mark
showing which ones were. The tool finds 510 differences. Under the tuned rules 174 are counted, 145 are
later copies of a repeated pair and 220 are listed as ignored. A rule can see that two texts differ. It
cannot see that B cut a crowd chant for pacing or chose another sound tag on purpose.

## What was changed from the brief

Counts after each step, applied in order:

| Step | Major | Lang | Punct | CC | Rep | Minor | Total |
|---|---|---|---|---|---|---|---|
| Strict: the brief's rules literally | 65 | 19 | 19 | 44 | 46 | 5 | 198 |
| 1. Song markers are formatting, not counted (108 differences; the reviewer counted 2 CC in all) | 65 | 19 | 19 | 40 | 39 | 5 | 187 |
| 2. A sound tag counts only when both files have one and they differ | 65 | 19 | 19 | 10 | 33 | 5 | 151 |
| 3. A mark B drops where it breaks the line is a line break (the brief: never a mistake) | 65 | 19 | 14 | 10 | 32 | 5 | 145 |
| 4. A cut of 4 or more words only one file has is not a word mistake (crowd chants) | 38 | 19 | 14 | 10 | 32 | 5 | 118 |
| 5. Repeated needs 5 occurrences for words, 10 for punctuation and CC (the brief says 2) | 52 | 29 | 66 | 10 | 6 | 11 | 174 |

Step 5 matters most: with a threshold of 2, a comma turning into "!" counts as Repeated 44 times, against
the reviewer's 4. Single missing words still count, because the brief's own Major example is one.

Changes made to follow the brief more closely, not to tune: each word of a changed run is judged on its
own; Minor and the spelling rules are checked before Major's distance rule (otherwise ना to न is Major);
उ and ऊ are one letter; a mixed word and punctuation change is split in two.

## Where each gap comes from

* **Major, 52 against 9.** 40 are a word or phrase only one file has (24 single words), 12 are different
  words. A person decides which cut is a mistake.
* **Language, 29 against 12.** Plausible spelling differences (कहां and कहाँ, पलिता and पलीता). The tool
  cannot tell which ones the reviewer chose to count.
* **CC, 10 against 2.** Ten sound tags are worded differently in B ("शोर" and "आवाज"). Which wording is wrong is a judgement.
* **Minor, 11 against 4.** Real, small space differences (गांधीजी and गांधी जी, हम में and हममें).
* **A brief example not matched.** वाह करता to वा अकर्ता is a Major example in the brief, but the words are
  only 0.33 apart, so the tool calls it Language.

## What this does not show

* **Tuned on one episode.** Steps 1 to 5 were chosen by looking at this episode's table. Punctuation
  matching to the unit is partly luck. A second episode with its QC table is the real test.
* **Word.** Reject All gives A back at 100.00 percent and Accept All gives B at 100.00 percent. The file
  opens in python-docx, macOS QuickLook and ONLYOFFICE (its reader keeps all 344 insertions, 466 deletions,
  the table and the 11 font parts). Opening in Word without a repair prompt is unverified.
* **No reviewer test yet.** The keyboard-only pass from the brief has not been done by a reviewer.

## Questions for Abinash

1. Are missing ♪ markers CC mistakes? The brief says yes; the reviewer's CC of 2 suggests the team does not count them.
2. For a repeated pair, is the first occurrence also counted in its own category? The tool counts only Repeated.
3. Does the reviewer count words missing because B cut a crowd chant?
4. Can there be a second episode with its QC table?
