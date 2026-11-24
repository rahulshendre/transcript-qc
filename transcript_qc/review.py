"""A review session: the engine's mistakes plus every decision the reviewer makes.

The reviewer never has to trust a number blindly. Every count is just the number of rows
behind it, so the reviewed counts are computed from the items below and nothing else:

    an item counts when it is in play (the engine counted it, or the reviewer promoted or
    added it) and has not been rejected.

Decisions are applied one at a time, each is written to a log with the time and what changed,
and the whole session can be saved and restored for the same two files.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from transcript_qc.compare import Comparison, compare_files
from transcript_qc.count import Analysis, analyse
from transcript_qc.rules import CATEGORIES, Rules, load_rules
from transcript_qc.sidebyside import Row, build_rows
from transcript_qc.summary import Details, details_from_name, summary_elements
from transcript_qc.writer import DEFAULT_AUTHOR, write_qc

SCHEMA = 1
ACTIONS = ("confirm", "category", "reject", "reset", "note", "promote", "split", "delete")


class ReviewError(Exception):
    """Something the reviewer asked for cannot be done. The message is shown as it is."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(slots=True)
class Item:
    id: int
    key: str
    source: str              # engine, ignored, manual or split
    line_no: int             # 1-based paragraph in file A
    b_line: int              # 1-based paragraph in file B
    a_text: str
    b_text: str
    engine_category: str     # what the rules said ("" for a mistake the reviewer added)
    category: str            # what it counts as now
    base_category: str       # what a Repeated mistake would be on its own
    rule_id: str
    engine_note: str
    confidence: float
    in_play: bool
    reviewed: bool = False
    rejected: bool = False
    reviewer_note: str = ""
    ignored_because: str = ""
    diffs: list[int] = field(default_factory=list)
    row: int = -1
    occurrences: list[dict] = field(default_factory=list)
    deleted: bool = False

    @property
    def status(self) -> str:
        if self.deleted:
            return "deleted"
        if not self.in_play:
            return "ignored"
        if self.rejected:
            return "rejected"
        if self.source == "manual":
            return "added"
        if not self.reviewed:
            return "pending"
        if self.source == "ignored":
            return "promoted"
        return "confirmed" if self.category == self.engine_category else "changed"

    @property
    def counts(self) -> bool:
        return self.in_play and not self.rejected and not self.deleted

    @property
    def done(self) -> bool:
        return self.in_play and not self.deleted and (self.reviewed or self.rejected)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status
        data["counts"] = self.counts
        return data


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snapshot(item: Item) -> dict:
    return {
        "category": item.category, "reviewed": item.reviewed, "rejected": item.rejected,
        "in_play": item.in_play, "note": item.reviewer_note, "deleted": item.deleted,
    }


def _unique_key(raw: str, taken: set[str]) -> str:
    key = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    suffix = 1
    while key in taken:
        suffix += 1
        key = hashlib.sha1(f"{raw}#{suffix}".encode()).hexdigest()[:12]
    taken.add(key)
    return key


class ReviewSession:
    def __init__(
        self,
        session_id: str,
        comparison: Comparison,
        analysis: Analysis,
        details: Details,
        a_path: Path,
        b_path: Path,
        a_name: str,
        b_name: str,
        rules_name: str = "default",
    ) -> None:
        self.id = session_id
        self.comparison, self.analysis, self.details = comparison, analysis, details
        self.a_path, self.b_path, self.a_name, self.b_name = a_path, b_path, a_name, b_name
        self.rules_name = rules_name
        self.rows, self.row_of_diff = build_rows(comparison)
        self.items: list[Item] = []
        self.log: list[dict] = []
        self._keys: set[str] = set()
        self._build_items()

    # ---- building -------------------------------------------------------------------------

    def _build_items(self) -> None:
        copies = defaultdict(list)
        for m in self.analysis.repeats:
            copies[m.repeat_of].append(m)
        for m in self.analysis.mistakes:
            if m.status == "repeat":
                continue
            ignored = m.status == "ignored"
            occurrences = []
            if m.category == "Repeated":
                for o in [m, *copies[m.index]]:
                    occurrences.append({
                        "line_no": o.line_no, "b_line": o.b_line, "a_text": o.a_text,
                        "b_text": o.b_text, "diff": o.hunk.diff_index,
                    })
            raw = f"{m.status}|{m.line_no}|{m.b_line}|{m.a_text}|{m.b_text}|{m.rule_id}"
            self.items.append(Item(
                id=len(self.items),
                key=_unique_key(raw, self._keys),
                source="ignored" if ignored else "engine",
                line_no=m.line_no, b_line=m.b_line, a_text=m.a_text, b_text=m.b_text,
                engine_category=m.base_category if ignored else m.category,
                category=m.base_category if ignored else m.category,
                base_category=m.base_category, rule_id=m.rule_id, engine_note=m.note,
                confidence=m.confidence, in_play=not ignored,
                ignored_because=m.ignored_because,
                diffs=[o["diff"] for o in occurrences] or [m.hunk.diff_index],
                row=self.row_of_diff.get(m.hunk.diff_index, -1),
                occurrences=occurrences,
            ))

    # ---- numbers --------------------------------------------------------------------------

    @property
    def engine_counts(self) -> dict[str, int]:
        return dict(self.analysis.counts)

    def counts(self) -> dict[str, int]:
        """The reviewed counts: how many items are behind each category right now."""
        tally = dict.fromkeys(CATEGORIES, 0)
        for item in self.items:
            if item.counts:
                tally[item.category] += 1
        return tally

    def progress(self) -> dict[str, int]:
        in_play = [i for i in self.items if i.in_play and not i.deleted]
        done = sum(1 for i in in_play if i.done)
        return {"reviewed": done, "total": len(in_play), "pending": len(in_play) - done}

    def item(self, item_id: int) -> Item:
        if not 0 <= item_id < len(self.items) or self.items[item_id].deleted:
            raise ReviewError(f"There is no mistake number {item_id}.", 404)
        return self.items[item_id]

    # ---- decisions ------------------------------------------------------------------------

    def _record(self, action: str, item: Item, before: dict, extra: dict | None = None) -> None:
        entry = {
            "t": _now(), "action": action, "id": item.id, "key": item.key,
            "line_no": item.line_no, "before": before, "after": _snapshot(item),
        }
        if extra:
            entry.update(extra)
        self.log.append(entry)

    def apply(
        self,
        action: str,
        item_id: int,
        category: str | None = None,
        note: str | None = None,
        occurrences: list[int] | None = None,
    ) -> list[Item]:
        """Apply one decision. Returns the items it created (a split can create several)."""
        if action not in ACTIONS:
            raise ReviewError(f"Unknown action {action!r}.")
        item = self.item(item_id)
        before = _snapshot(item)
        created: list[Item] = []
        if action == "confirm":
            self._need_in_play(item)
            item.reviewed, item.rejected = True, False
        elif action == "category":
            self._need_in_play(item)
            if category not in CATEGORIES:
                raise ReviewError(f"{category!r} is not one of the six categories.")
            item.category, item.reviewed, item.rejected = category, True, False
        elif action == "reject":
            self._need_in_play(item)
            item.rejected, item.reviewed = True, True
        elif action == "reset":
            self._reset(item)
        elif action == "note":
            item.reviewer_note = (note or "").strip()
        elif action == "promote":
            if item.in_play:
                raise ReviewError("This difference is already counted.")
            item.in_play, item.reviewed, item.rejected = True, True, False
            if category in CATEGORIES:
                item.category = category
        elif action == "split":
            created = self._split(item, occurrences or [])
        elif action == "delete":
            if item.source not in ("manual", "split"):
                raise ReviewError("Only a mistake you added can be deleted. Reject it instead.")
            item.deleted = True
        extra = {"created": [c.id for c in created]} if created else None
        self._record(action, item, before, extra)
        return created

    @staticmethod
    def _need_in_play(item: Item) -> None:
        if not item.in_play:
            raise ReviewError("This difference is not counted. Promote it to count it.")

    @staticmethod
    def _reset(item: Item) -> None:
        item.rejected = False
        item.reviewed = False
        item.category = item.engine_category if item.source != "manual" else item.category
        if item.source == "ignored":
            item.in_play = False

    def _split(self, item: Item, indexes: list[int]) -> list[Item]:
        if item.category != "Repeated" and item.engine_category != "Repeated":
            raise ReviewError("Only a repeated mistake can be split.")
        if len(item.occurrences) < 2:
            raise ReviewError("This repeated mistake has only one occurrence left.")
        chosen = sorted(set(indexes))
        if not chosen or any(not 0 <= i < len(item.occurrences) for i in chosen):
            raise ReviewError("Choose which occurrences to split off.")
        if len(chosen) >= len(item.occurrences):
            raise ReviewError("At least one occurrence has to stay in the group.")
        created = []
        for index in chosen:
            occ = item.occurrences[index]
            row = self.row_of_diff.get(occ["diff"], -1)
            created.append(self._new_item(
                source="split", line_no=occ["line_no"], b_line=occ["b_line"],
                a_text=occ["a_text"], b_text=occ["b_text"],
                category=item.base_category, engine_category=item.base_category,
                base_category=item.base_category, rule_id="SPLIT_FROM_REPEATED",
                engine_note=f"split off a repeated pair ({occ['a_text'] or '-'} to "
                f"{occ['b_text'] or '-'})", confidence=0.5, diffs=[occ["diff"]], row=row,
            ))
        item.occurrences = [o for k, o in enumerate(item.occurrences) if k not in chosen]
        first = item.occurrences[0]
        item.line_no, item.b_line = first["line_no"], first["b_line"]
        item.a_text, item.b_text, item.diffs = first["a_text"], first["b_text"], [
            o["diff"] for o in item.occurrences
        ]
        item.row = self.row_of_diff.get(first["diff"], item.row)
        if len(item.occurrences) == 1 and item.category == "Repeated":
            item.category = item.engine_category = item.base_category
        return created

    def _new_item(self, **kw) -> Item:
        raw = f"{kw['source']}|{kw['line_no']}|{kw['b_line']}|{kw['a_text']}|{kw['b_text']}"
        item = Item(id=len(self.items), key=_unique_key(raw, self._keys), in_play=True, **kw)
        self.items.append(item)
        return item

    def add_mistake(
        self, side: str, text: str, line_no: int, row: int, category: str, note: str = ""
    ) -> Item:
        """A mistake the reviewer found that the engine missed, from selected text."""
        if category not in CATEGORIES:
            raise ReviewError(f"{category!r} is not one of the six categories.")
        text = " ".join(text.split())
        if not text:
            raise ReviewError("Select some text first.")
        if side not in ("a", "b"):
            raise ReviewError("The selection must be in file A or file B.")
        item = self._new_item(
            source="manual",
            line_no=line_no if side == "a" else 0, b_line=line_no if side == "b" else 0,
            a_text=text if side == "a" else "", b_text=text if side == "b" else "",
            engine_category="", category=category, base_category=category,
            rule_id="REVIEWER_ADDED", engine_note="added by the reviewer", confidence=1.0,
            diffs=[], row=row, reviewed=True, reviewer_note=note.strip(),
        )
        self._record("add", item, {}, {"side": side})
        return item

    def set_details(self, movie: str | None, writer: str | None, episode: str | None) -> None:
        self.details = Details(
            movie if movie is not None else self.details.movie,
            writer if writer is not None else self.details.writer,
            episode if episode is not None else self.details.episode,
        )

    # ---- saving ---------------------------------------------------------------------------

    def to_saved(self) -> dict:
        items = []
        for it in self.items:
            data = {
                "key": it.key, "source": it.source, "category": it.category,
                "reviewed": it.reviewed, "rejected": it.rejected, "in_play": it.in_play,
                "note": it.reviewer_note, "deleted": it.deleted,
                "occurrences": [o["diff"] for o in it.occurrences],
            }
            if it.source in ("manual", "split"):
                data["full"] = asdict(it)
            items.append(data)
        return {
            "schema": SCHEMA, "id": self.id, "saved": _now(), "rules": self.rules_name,
            "a_name": self.a_name, "b_name": self.b_name,
            "details": asdict(self.details), "items": items, "log": self.log,
        }

    def restore(self, saved: dict) -> tuple[int, int]:
        """Put a saved review back. Returns (items restored, saved items that no longer exist)."""
        if saved.get("schema") != SCHEMA:
            raise ReviewError("This saved review was made by a different version of the tool.")
        by_key = {it.key: it for it in self.items}
        restored = orphans = 0
        for data in saved.get("items", []):
            item = by_key.get(data["key"])
            if item is None and data.get("full"):
                item = self._revive(data["full"])
            if item is None:
                orphans += 1
                continue
            item.category = data["category"] if data["category"] in CATEGORIES else item.category
            item.reviewed, item.rejected = bool(data["reviewed"]), bool(data["rejected"])
            item.in_play, item.reviewer_note = bool(data["in_play"]), data.get("note", "")
            item.deleted = bool(data.get("deleted"))
            if item.occurrences and data.get("occurrences"):
                keep = set(data["occurrences"])
                item.occurrences = [o for o in item.occurrences if o["diff"] in keep] or (
                    item.occurrences
                )
                first = item.occurrences[0]
                item.line_no, item.b_line = first["line_no"], first["b_line"]
                item.a_text, item.b_text = first["a_text"], first["b_text"]
                item.diffs = [o["diff"] for o in item.occurrences]
            restored += 1
        self.log = list(saved.get("log", []))
        saved_details = saved.get("details")
        if saved_details:
            self.details = Details(**saved_details)
        return restored, orphans

    def _revive(self, full: dict) -> Item:
        data = {k: v for k, v in full.items() if k not in ("status", "counts")}
        data["id"] = len(self.items)
        item = Item(**data)
        self._keys.add(item.key)
        self.items.append(item)
        return item

    # ---- what the screen needs ----------------------------------------------------------------

    def state(self) -> dict:
        return {
            "id": self.id, "a_name": self.a_name, "b_name": self.b_name,
            "rules": self.rules_name, "details": asdict(self.details),
            "engine_counts": self.engine_counts, "counts": self.counts(),
            "progress": self.progress(),
            "items": [i.as_dict() for i in self.items if not i.deleted],
            "row_count": len(self.rows),
            "paragraphs": {"a": len(self.comparison.a_paragraphs),
                           "b": len(self.comparison.b_paragraphs)},
        }

    def rows_json(self) -> list[dict]:
        def lines(side: list) -> list[dict]:
            return [{"para": ln.para, "segments": [[s.text, s.diff] for s in ln.segments]}
                    for ln in side]
        return [{"index": r.index, "a": lines(r.a), "b": lines(r.b)} for r in self.rows]

    # ---- exporting ------------------------------------------------------------------------

    def export_docx(self, out_path: str | Path, author: str = DEFAULT_AUTHOR) -> None:
        """The QC document: every difference tracked, the summary table from reviewed counts."""
        write_qc(
            self.a_path, self.comparison, out_path, author=author,
            append=summary_elements(self.details, self.counts()),
        )

    CSV_COLUMNS = (
        "line_no", "a_text", "b_text", "engine_category", "final_category", "status",
        "counted", "rule_id", "engine_note", "reviewer_note", "source",
    )

    def export_csv(self, out_path: str | Path) -> int:
        """Every mistake with its engine category, final category, status and note.

        The rows marked counted=yes are exactly the rows behind the reviewed counts.
        """
        rows = []
        for it in self.items:
            if it.deleted:
                continue
            rows.append([
                it.line_no or it.b_line, it.a_text, it.b_text, it.engine_category or "-",
                it.category if it.in_play else "", it.status, "yes" if it.counts else "no",
                it.rule_id, it.engine_note, it.reviewer_note, it.source,
            ])
            for occ in it.occurrences[1:]:
                rows.append([
                    occ["line_no"], occ["a_text"], occ["b_text"], it.engine_category,
                    it.category, "repeat", "no", it.rule_id,
                    f"another occurrence of mistake {it.id}", "", it.source,
                ])
        with open(out_path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.CSV_COLUMNS)
            writer.writerows(rows)
        return len(rows)


def session_id_for(a_bytes: bytes, b_bytes: bytes) -> str:
    """The same two files always give the same id, so a review can be found again."""
    digest = hashlib.sha256(hashlib.sha256(a_bytes).digest() + hashlib.sha256(b_bytes).digest())
    return digest.hexdigest()[:16]


class SessionStore:
    """Saved sessions on disk: the two files, the decisions and a plain log."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, session_id: str) -> Path:
        return self.root / session_id

    def open(
        self, a_bytes: bytes, b_bytes: bytes, a_name: str, b_name: str,
        rules_name: str = "default", details: Details | None = None,
    ) -> tuple[ReviewSession, tuple[int, int] | None]:
        """Compare two files and bring back an earlier review of the same two files."""
        session_id = session_id_for(a_bytes, b_bytes)
        folder = self.folder(session_id)
        folder.mkdir(parents=True, exist_ok=True)
        a_path, b_path = folder / "a.docx", folder / "b.docx"
        a_path.write_bytes(a_bytes)
        b_path.write_bytes(b_bytes)
        return self._build(session_id, a_path, b_path, a_name, b_name, rules_name, details)

    def load(self, session_id: str) -> tuple[ReviewSession, tuple[int, int] | None]:
        folder = self.folder(session_id)
        state = folder / "state.json"
        if not state.is_file():
            raise ReviewError("That review was not found.", 404)
        saved = json.loads(state.read_text(encoding="utf-8"))
        return self._build(
            session_id, folder / "a.docx", folder / "b.docx", saved["a_name"], saved["b_name"],
            saved.get("rules", "default"), None,
        )

    def _build(self, session_id, a_path, b_path, a_name, b_name, rules_name, details):
        rules: Rules = load_rules(rules_name)
        try:
            comparison = compare_files(a_path, b_path)
        except Exception as error:  # a file that is not a Word document
            raise ReviewError(
                "One of the files could not be read as a Word (.docx) document."
            ) from error
        if not any(p.strip() for p in comparison.a_paragraphs):
            raise ReviewError(f"{a_name} has no text.")
        if not any(p.strip() for p in comparison.b_paragraphs):
            raise ReviewError(f"{b_name} has no text.")
        analysis = analyse(comparison, rules)
        details = details or details_from_name(a_name, rules.movies)
        session = ReviewSession(
            session_id, comparison, analysis, details, a_path, b_path, a_name, b_name, rules_name
        )
        state = self.folder(session_id) / "state.json"
        outcome = None
        if state.is_file():
            outcome = session.restore(json.loads(state.read_text(encoding="utf-8")))
        return session, outcome

    def save(self, session: ReviewSession) -> Path:
        """Write the session atomically, and append the latest decision to the plain log."""
        folder = self.folder(session.id)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "state.json"
        handle, temp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(session.to_saved(), out, ensure_ascii=False)
        os.replace(temp, target)
        with open(folder / "decisions.jsonl", "w", encoding="utf-8") as log:
            for entry in session.log:
                log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return target

    def listing(self) -> list[dict]:
        found = []
        for state in sorted(self.root.glob("*/state.json"), key=lambda p: -p.stat().st_mtime):
            try:
                saved = json.loads(state.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            items = [i for i in saved.get("items", []) if i.get("in_play") and not i.get("deleted")]
            done = sum(1 for i in items if i.get("reviewed") or i.get("rejected"))
            found.append({
                "id": saved.get("id"), "a_name": saved.get("a_name"),
                "b_name": saved.get("b_name"), "saved": saved.get("saved"),
                "reviewed": done, "total": len(items),
            })
        return found


__all__ = [
    "ACTIONS", "Item", "ReviewError", "ReviewSession", "Row", "SessionStore", "session_id_for",
]
