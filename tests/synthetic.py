"""Build a transcript pair where the mistakes are known, so the tool can be checked against the truth.

B is a clean transcript. A is B with a chosen number of each kind of mistake put in, one per line
unless a test says otherwise. The expected counts follow from what was put in, not from running the tool.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# Plain Hindi words, none close to another in spelling, so no two can be mistaken for a variant of each other.
VOCAB = """पानी आकाश घर जंगल रोटी पुस्तक सुबह रात नदी पहाड़ गाँव शहर बच्चा बूढ़ा किसान राजा रानी सिपाही
मंदिर बाज़ार खेत सड़क पेड़ फूल पत्ता चिड़िया शेर हाथी घोड़ा गाय बकरी दूध घी चावल दाल नमक चीनी आग हवा
धूप छाँव बादल बारिश तारा चाँद सूरज धरती समुद्र रेत पत्थर लोहा सोना चाँदी कपड़ा जूता टोपी छाता किताब
कलम कागज़ स्कूल गुरु शिष्य दोस्त पड़ोसी मेहमान त्योहार मेला गीत कहानी सपना नींद थकान भूख प्यास खुशी
डर साहस सच झूठ न्याय धन मेहनत इंतज़ार रास्ता मंज़िल सफ़र आवाज़ ख़ामोशी रोशनी अँधेरा बचपन जवानी बुढ़ापा""".split()

CONNECT = ["और", "से", "में", "पर", "को", "का", "की", "के", "भी", "तो", "ही", "फिर", "जब", "तब"]
VERBS = ["जाता", "आता", "देखता", "सुनता", "कहता", "रहता", "चलता", "बोलता", "सोचता", "मिलता"]

# (what B has, what A has). Chosen by hand as plainly different words: a different word is Major.
DIFFERENT_WORDS = [("पानी", "आकाश"), ("घर", "जंगल"), ("रोटी", "पुस्तक"), ("नदी", "सिपाही"),
                   ("शेर", "कलम"), ("दूध", "मंदिर"), ("चाँद", "किसान"), ("गुरु", "समुद्र"),
                   ("चावल", "चाकू"), ("पत्ता", "फूलों")]
# Same letters with other marks, or a long and short vowel: a spelling slip is Language.
SPELLING = [("कहाँ", "कहां"), ("ऊँचे", "उंचे"), ("मूँछें", "मूछें"), ("पलीता", "पलिता"),
            ("कर्ता", "करता"), ("गाँव", "गांव"), ("दुनिया", "दुनीया"), ("चाँदनी", "चांदनी"),
            # one wrong letter, no marks involved: only the "spelled almost the same" rule catches these
            ("बादल", "बादर"), ("किसान", "किसाण"), ("सड़क", "सड़ग")]
# One word written as two, or two as one: a space slip is Minor.
SPACING = [("रामराज", "राम राज"), ("सचमुच", "सच मुच"), ("हममें", "हम में"), ("कबका", "कब का")]
# Different marks, so no one mark turns up often enough to be a repeated pattern.
MARKS = ["?", "!", ":", ";", "-", "…"]
TAGS = [("[संगीत]", "[नाटकीय संगीत]"), ("[हवा की आवाज़]", "[हवा का शोर]"), ("[तालियाँ]", "[ताली]"),
        ("[घंटी की आवाज़]", "[घंटी का शोर]"), ("[हँसी]", "[हंसी]")]


@dataclass
class Plan:
    """How many of each mistake to put in. Repeated is a pair put in `repeat_times` times."""
    major_different: int = 0
    major_missing: int = 0
    language: int = 0
    punctuation: int = 0
    cc: int = 0
    minor: int = 0
    repeat_pair: tuple[str, str] | None = None  # (B form, A form); ("न", "ना") is a listed variant
    repeat_times: int = 0
    lines: int = 150
    noise: bool = True  # also put in things that must NOT count

    def expected(self) -> dict[str, int]:
        repeated = 1 if self.repeat_pair and self.repeat_times >= 5 else 0
        alone = 0 if repeated else self.repeat_times  # too few to be a pattern: one mistake each
        return {
            "Major": self.major_different + self.major_missing,
            "Language": self.language + alone,  # the pair used is a spelling variant
            "Punctuation": self.punctuation,
            "CC": self.cc,
            "Repeated": repeated,
            "Minor": self.minor,
        }


@dataclass
class Pair:
    a: list[str]
    b: list[str]
    plan: Plan
    log: list[str] = field(default_factory=list)


def _sentence(rng: random.Random, commas: bool) -> list[str]:
    words = rng.sample(VOCAB, rng.randint(4, 6))
    words.insert(rng.randint(1, len(words) - 1), rng.choice(CONNECT))
    words.append(rng.choice(VERBS))
    if commas and len(words) > 5:
        words[2] += ","
    return words


def build(plan: Plan, seed: int) -> Pair:
    rng = random.Random(seed)
    b_words = [_sentence(rng, commas=i % 4 == 0) for i in range(plan.lines)]
    a_words = [list(w) for w in b_words]
    free = list(range(plan.lines))
    rng.shuffle(free)
    log: list[str] = []

    def take() -> int:
        return free.pop()

    def put(line: int, b_word: str, a_word: str, what: str) -> None:
        """Put the B form into B and the A form into A at one spot of one line."""
        # never the first or last word: a changed last word and a changed first word on neighbouring
        # lines touch across the line break and count as one run (the brief's rule 1)
        spot = rng.randint(1, len(b_words[line]) - 2)
        word = b_words[line][spot]
        mark = word[-1] if word.endswith(",") else ""
        b_words[line][spot] = b_word + mark
        a_words[line][spot] = a_word + mark
        log.append(f"line {line + 1}: {what}: {b_word} -> {a_word}")

    for k in range(plan.major_different):
        put(take(), *DIFFERENT_WORDS[k % len(DIFFERENT_WORDS)], "major different")
    for _ in range(plan.major_missing):
        line = take()
        # a word with a comma on it would cost A the comma too: the brief counts that as two mistakes
        spots = [i for i in range(1, len(a_words[line]) - 1) if not a_words[line][i].endswith(",")]
        spot = rng.choice(spots)
        log.append(f"line {line + 1}: major missing: {a_words[line][spot]}")
        del a_words[line][spot]
    for k in range(plan.language):
        put(take(), *SPELLING[k % len(SPELLING)], "language")
    for k in range(plan.minor):
        put(take(), *SPACING[k % len(SPACING)], "minor")
    for k in range(plan.punctuation):
        line = take()
        mark = MARKS[k % len(MARKS)]
        spot = rng.randint(0, len(a_words[line]) - 2)
        b_words[line][spot] = b_words[line][spot].rstrip(",") + mark  # B has a mark A lacks
        a_words[line][spot] = a_words[line][spot].rstrip(",")
        log.append(f"line {line + 1}: punctuation: {mark}")
    for k in range(plan.cc):
        line = take()
        b_tag, a_tag = TAGS[k % len(TAGS)]
        b_words[line].append(b_tag)
        a_words[line].append(a_tag)
        log.append(f"line {line + 1}: cc: {b_tag} -> {a_tag}")
    if plan.repeat_pair:
        b_form, a_form = plan.repeat_pair
        for _ in range(plan.repeat_times):
            line = take()
            b_words[line].insert(1, b_form)
            a_words[line].insert(1, a_form)
            log.append(f"line {line + 1}: repeated: {b_form} -> {a_form}")

    b_lines = [" ".join(w) for w in b_words]
    a_lines = [" ".join(w) for w in a_words]
    if plan.noise:
        # none of this may count: B marks songs with ♪, spacing differs, invisible characters
        for _ in range(8):
            line = take()
            b_lines[line] = "♪ " + b_lines[line] + " ♪"
        for _ in range(4):
            line = take()
            a_lines[line] = a_lines[line].replace(" ", "  ", 1)
        line = take()
        a_lines[line] = a_lines[line] + "​"
        line = take()
        a_lines[line] = a_lines[line].replace(" ", " ", 1)
    # real files have a blank paragraph between lines
    a = [x for line in a_lines for x in (line, "")]
    b = [x for line in b_lines for x in (line, "")]
    return Pair(a, b, plan, log)
