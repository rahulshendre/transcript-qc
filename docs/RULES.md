# Rules

Everything that decides a category or a count lives in `transcript_qc/rules.yaml`. No code change is
needed to tune it. Run with your own copy: `python qc_compare.py ... --rules my_rules.yaml`.
`rules_strict.yaml` is the assignment's rules applied literally, for comparison.

## How a difference becomes a category

Every difference is checked against the rules in the `order:` list, top to bottom. The first rule that
matches decides the category, and its id goes to the CSV. Reorder or delete ids to change the behaviour.

| Rule id | Matches when | Category |
|---|---|---|
| `CC_TAG` | The difference touches a `[sound tag]` | CC |
| `CC_MUSIC` | It touches a ♪ marker | CC |
| `PUNCT_ONLY` | Only punctuation differs | Punctuation |
| `MINOR_SPACE` | The text is the same once spaces are removed (गांधीजी, गांधी जी) | Minor |
| `LANG_VARIANT` | Every word is a listed spelling pair in `variants` | Language |
| `LANG_MARKS` | Same letters, different matra, nukta, anusvara or chandrabindu (कहां, कहाँ) | Language |
| `MAJOR_ADDED` | A whole word was added or removed | Major |
| `LANG_SIMILAR` | Every word is spelled almost the same (distance at or below `language_max_distance`) | Language |
| `MAJOR_DIFFERENT` | A word is a different word | Major |

A changed run of several words is split into word pairs and each pair is judged on its own. A run is
Language only if every pair is. This follows the assignment's "word-level" wording for Major.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `similarity.language_max_distance` | 0.4 | Edit distance (0 identical, 1 nothing shared) up to which a changed word is a spelling mistake. Above it, a different word. |
| `fold_vowel_length` | true | Treat the long and short independent vowels (उ and ऊ, इ and ई, ऋ and ॠ) as one letter, so उंचे to ऊँचे is Language. |
| `ignore_marks` | `[Mn, Mc]` | Unicode mark classes that do not count when asking whether two words have the same letters. |
| `variants` | वह/वो, ना/न | Spelling pairs that always count as Language, in either direction. |
| `repeated.min_occurrences` | 5 | A pair (A text to B text) seen this many times is one Repeated mistake. The assignment says 2. |
| `repeated.min_occurrences_by_category` | Punctuation 10, CC 10 | Per-category override of the line above. |
| `repeated.categories` | Major, Language, Punctuation, CC, Minor | Which categories can turn into Repeated. |
| `ignore.music_markers` | true | A missing or extra ♪ is song formatting, not a mistake. |
| `ignore.line_break_punctuation` | true | A mark B drops where it breaks the line is not a mistake. |
| `ignore.long_cuts_words` | 4 | A run of this many words or more that only one file has is a cut, not a word mistake. 0 turns it off. |
| `tags.count` | `changed_only` | `changed_only` counts a `[tag]` only when both files have one and they differ. `all` counts every tag difference. |
| `movies` | BEK: Bharat Ek Khoj | Short codes in file names mapped to the movie name for the summary table. |

## Counting

One difference is one mistake. A repeated pair counts once, as Repeated, and its later copies are not
counted again. Differences that a switch ignores stay in the tracked-change document and are listed in
the CSV as not counted, so a reviewer can promote one in the review screen.

## Changing a rule safely

1. Run once with the current rules and keep the counts.
2. Change one setting.
3. Run again and compare. Changing one thing at a time shows what each setting does. The step table in
   `docs/ACCURACY_NOTE.md` was made this way.
4. Check a second episode before trusting a change. The current thresholds were set on Episode 50 only.
