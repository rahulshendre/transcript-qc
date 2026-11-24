"""Load the rules that decide how differences are classified and counted."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml

CATEGORIES = ("Major", "Language", "Punctuation", "CC", "Repeated", "Minor")


@dataclass(frozen=True, slots=True)
class Rules:
    order: tuple[str, ...]
    language_max_distance: float
    ignore_marks: frozenset[str]
    fold_vowel_length: bool
    variants: frozenset[tuple[str, str]]
    repeated_min: int
    repeated_min_by_category: dict[str, int]
    repeated_categories: frozenset[str]
    ignore_music_markers: bool
    ignore_line_break_marks: bool
    ignore_long_cuts_words: int
    count_tags: str  # "all" or "changed_only"
    movies: dict[str, str]


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def parse_rules(data: dict) -> Rules:
    from transcript_qc.classify import RULE_IDS  # imported here: classify imports Rules

    order = tuple(data["order"])
    unknown = [r for r in order if r not in RULE_IDS]
    if unknown:
        raise ValueError(f"unknown rule ids in rules.yaml: {unknown}; known: {sorted(RULE_IDS)}")
    distance = float(data["similarity"]["language_max_distance"])
    if not 0.0 <= distance <= 1.0:
        raise ValueError("similarity.language_max_distance must be between 0 and 1")
    by_category = data["repeated"].get("min_occurrences_by_category") or {}
    overrides = {str(k): int(v) for k, v in by_category.items()}
    categories = frozenset(data["repeated"]["categories"])
    bad = (categories | set(overrides)) - set(CATEGORIES)
    if bad:
        raise ValueError(f"unknown categories in the repeated settings: {sorted(bad)}")
    ignore = data.get("ignore") or {}
    count_tags = str((data.get("tags") or {}).get("count", "all"))
    if count_tags not in ("all", "changed_only"):
        raise ValueError("tags.count must be 'all' or 'changed_only'")
    variants = set()
    for pair in data.get("variants") or []:
        if len(pair) != 2:
            raise ValueError(f"a variant must be a pair of words, got {pair!r}")
        left, right = _norm(pair[0]), _norm(pair[1])
        variants.add((left, right))
        variants.add((right, left))
    return Rules(
        order=order,
        language_max_distance=distance,
        ignore_marks=frozenset(data.get("ignore_marks") or []),
        fold_vowel_length=bool(data.get("fold_vowel_length", True)),
        variants=frozenset(variants),
        repeated_min=int(data["repeated"]["min_occurrences"]),
        repeated_min_by_category=overrides,
        repeated_categories=categories,
        ignore_music_markers=bool(ignore.get("music_markers", False)),
        ignore_line_break_marks=bool(ignore.get("line_break_punctuation", False)),
        ignore_long_cuts_words=int(ignore.get("long_cuts_words", 0)),
        count_tags=count_tags,
        movies={str(k).upper(): str(v) for k, v in (data.get("movies") or {}).items()},
    )


def repeat_threshold(rules: Rules, category: str) -> int:
    """How many times a pair must appear to be Repeated, for a pair that would count as category."""
    return rules.repeated_min_by_category.get(category, rules.repeated_min)


PROFILES = {"default": "rules.yaml", "strict": "rules_strict.yaml"}


def load_rules(source: str | Path | None = None) -> Rules:
    """Rules from a YAML file, a named profile ("default", "strict"), or the shipped default."""
    name = "default" if source is None else str(source)
    if name in PROFILES:
        text = (resources.files("transcript_qc") / PROFILES[name]).read_text(encoding="utf-8")
    else:
        text = Path(source).read_text(encoding="utf-8")
    return parse_rules(yaml.safe_load(text))
