"""Command line: print the word-by-word difference between two transcripts."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from transcript_qc.accuracy import format_table, parse_reference
from transcript_qc.align import Diff
from transcript_qc.compare import Comparison, compare_files
from transcript_qc.count import Analysis, analyse
from transcript_qc.reader import InputError, docx_warnings
from transcript_qc.report import write_csv
from transcript_qc.revisions import round_trip
from transcript_qc.rules import CATEGORIES, load_rules
from transcript_qc.summary import details_from_name, summary_elements
from transcript_qc.tokenize import Token
from transcript_qc.writer import DEFAULT_AUTHOR, write_qc

_RED, _GREEN, _DIM, _OFF = "\033[31m", "\033[32m", "\033[2m", "\033[0m"


def format_diff(diff: Diff, a_tokens: list[Token], words: int, color: bool) -> str:
    """One line: lines in A and B, the kind of change, then the change in context.

    Words before and after come from file A. The change reads [in A] -> [in B]:
    red is only in A, green is only in B, an empty bracket means nothing there.
    """
    red, green, dim, off = (_RED, _GREEN, _DIM, _OFF) if color else ("", "", "", "")
    start, end = diff.a_span
    before = " ".join(t.text for t in a_tokens[max(start - words, 0) : start])
    after = " ".join(t.text for t in a_tokens[end : end + words])
    change = f"{red}[{diff.a_text}]{off} -> {green}[{diff.b_text}]{off}"
    return (
        f"A:{diff.a_line:<5} B:{diff.b_line:<5} {diff.tag:<8} "
        f"{dim}{before}{off} {change} {dim}{after}{off}"
    )


def _file_line(name: str, paragraphs: list[str], tokens: list[Token]) -> str:
    filled = sum(1 for p in paragraphs if p.strip())
    return f"{name}: {len(paragraphs)} paragraphs ({filled} with text), {len(tokens)} tokens"


def summary(result: Comparison) -> str:
    kinds = Counter(d.tag for d in result.diffs)
    return "\n".join(
        [
            _file_line("A", result.a_paragraphs, result.a_tokens),
            _file_line("B", result.b_paragraphs, result.b_tokens),
            f"differences: {len(result.diffs)} "
            f"({kinds['replace']} replace, {kinds['delete']} delete, {kinds['insert']} insert)",
        ]
    )


def counts_line(analysis: Analysis) -> str:
    parts = [f"{name} {analysis.counts[name]:02d}" for name in CATEGORIES]
    return " | ".join(parts) + f" | Total {analysis.total:02d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qc_compare",
        description="Compare transcript A against reference B, count the mistakes in A by "
        "category and write the QC document.",
    )
    parser.add_argument("--a", required=True, type=Path, help="transcript being scored (LE1)")
    parser.add_argument("--b", required=True, type=Path, help="reference transcript (LE2)")
    parser.add_argument("--out", type=Path, help="write the QC document (A with tracked changes)")
    parser.add_argument("--csv", type=Path, help="mistakes.csv path (default: beside --out)")
    parser.add_argument("--rules", default=None, help="rules file, or a profile: default, strict")
    parser.add_argument("--author", default=DEFAULT_AUTHOR, help="author name on every revision")
    parser.add_argument("--movie", help="movie name for the summary table")
    parser.add_argument("--writer", help="writer name for the summary table")
    parser.add_argument("--episode", help="episode number for the summary table")
    parser.add_argument("--reference", help="compare the counts with a reference: ep50 or six "
                        "numbers (Major,Language,Punctuation,CC,Repeated,Minor)")
    parser.add_argument("--show-diff", action="store_true", help="print the differences too")
    parser.add_argument("--context", type=int, default=3, help="words of context to show")
    parser.add_argument("--limit", type=int, default=0, help="show only the first N differences")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args(argv)

    for path in (args.a, args.b):
        if not path.is_file():
            print(f"error: {path} not found", file=sys.stderr)
            return 2
    try:
        rules = load_rules(args.rules)
        reference = parse_reference(args.reference) if args.reference else None
    except (ValueError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        for path in (args.a, args.b):
            for warning in docx_warnings(path):
                print(f"warning: {warning}", file=sys.stderr)
        result = compare_files(args.a, args.b)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for path, paragraphs in ((args.a, result.a_paragraphs), (args.b, result.b_paragraphs)):
        if not any(p.strip() for p in paragraphs):
            print(f"error: {path.name} has no text.", file=sys.stderr)
            return 2
    analysis = analyse(result, rules)
    color = sys.stdout.isatty() and not args.no_color
    print(summary(result))
    if args.out is None or args.show_diff:
        print()
        shown = result.diffs[: args.limit] if args.limit else result.diffs
        for diff in shown:
            print(format_diff(diff, result.a_tokens, args.context, color))
        print()
    print(f"mistakes: {counts_line(analysis)}")
    print(
        f"  ({len(analysis.repeats)} later copies of repeated pairs and "
        f"{len(analysis.ignored)} differences not counted)"
    )
    if reference:
        print()
        print(format_table(analysis.counts, reference))
    if args.out is None:
        return 0

    details = details_from_name(args.a.name, rules.movies, args.movie, args.writer, args.episode)
    csv_path = args.csv or args.out.with_name("mistakes.csv")
    target = args.out
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        stats = write_qc(
            args.a, result, args.out, author=args.author,
            append=summary_elements(details, analysis.counts),
        )
        print(
            f"wrote {args.out}: {stats.deletions} deletions and {stats.insertions} insertions "
            f"in {stats.changed_paragraphs} paragraphs"
        )
        target = csv_path
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        rows = write_csv(analysis, csv_path)
    except OSError as error:
        # on Windows a file that is open in Word or Excel cannot be replaced
        print(
            f"error: cannot write {target} ({error.strerror or error}). "
            "If it is open in Word or Excel, close it and run again.",
            file=sys.stderr,
        )
        return 2
    print(f"wrote {csv_path}: {rows} rows")
    rejected, accepted = round_trip(args.out, result.a_paragraphs, result.b_paragraphs)
    print(f"round trip: Reject All matches A {rejected:.2%}, Accept All matches B {accepted:.2%}")
    return 0 if min(rejected, accepted) >= 0.99 else 1


if __name__ == "__main__":
    raise SystemExit(main())
