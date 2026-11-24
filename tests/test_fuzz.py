"""Random transcript pairs: the tracked-change file must always round-trip.

Each case builds a made-up file A, makes B by random edits (changed, dropped and
added words, punctuation, ♪ markers and sound tags), then lays B out with
different line breaks and double spaces, as the real files differ. Whatever the
edits, Reject All must give A back exactly and Accept All must give B (spacing
aside).
"""

import random

import pytest
from helpers import make_qc

from transcript_qc.revisions import comparable, revision_texts

WORDS = "जल भी कहां था सच मुझमें जानता वह वो ना न राम राज गांधी जी हम सब तुम क्या है नहीं".split()
MARKS = [",", "।", "?", "!", "-", "…"]
EXTRAS = ["♪", "[हवा चलने की आवाज़]", "[नाटकीय संगीत]"]


def random_token(rng):
    roll = rng.random()
    if roll < 0.7:
        return rng.choice(WORDS)
    if roll < 0.9:
        return rng.choice(MARKS)
    return rng.choice(EXTRAS)


def edit(tokens, rng):
    out = []
    for token in tokens:
        roll = rng.random()
        if roll < 0.08:
            out.append(random_token(rng))          # replaced
        elif roll < 0.14:
            continue                               # dropped
        elif roll < 0.20:
            out.extend([token, random_token(rng)])  # something added after it
        elif roll < 0.23 and token in WORDS:
            out.append(token + "ा")                # a matra added
        else:
            out.append(token)
    if rng.random() < 0.3:
        out.insert(0, "♪")
    if rng.random() < 0.3:
        out.append("♪")
    return out


def layout(tokens, rng, double_spaces):
    """Tokens into lines: random breaks, blank paragraphs between, punctuation attached."""
    lines, current = [], []
    for token in tokens:
        current.append(token)
        if rng.random() < 0.18:
            lines.append(current)
            current = []
    if current:
        lines.append(current)
    paragraphs = []
    for line in lines:
        gap = "  " if double_spaces and rng.random() < 0.5 else " "
        text = ""
        for token in line:
            attach = token in MARKS and text
            text += token if attach else (gap if text else "") + token
        paragraphs += [text, ""]
    return paragraphs


@pytest.mark.parametrize("seed", range(120))
def test_random_pairs_round_trip(tmp_path, seed):
    rng = random.Random(seed)
    base = [random_token(rng) for _ in range(rng.randint(3, 40))]
    a = layout(base, rng, double_spaces=False)
    b = layout(edit(base, rng), rng, double_spaces=True)
    out, comparison, _ = make_qc(tmp_path, a, b)
    rejected, accepted = revision_texts(out)
    assert rejected == comparison.a_paragraphs, f"seed {seed}: Reject All is not A"
    wanted = comparable(comparison.b_paragraphs)
    assert comparable(accepted) == wanted, f"seed {seed}: Accept All is not B"
