import csv
import json
import re
from datetime import datetime

import pytest
from docx import Document
from helpers import build

from transcript_qc.review import ACTIONS, ReviewError, SessionStore
from transcript_qc.rules import CATEGORIES

FILLER = "ठीक है"


def lines(pairs):
    """Interleave lines with a matching line between them, so each change stays its own hunk."""
    a, b = [], []
    for left, right in pairs:
        a += [left, FILLER]
        b += [right, FILLER]
    return a, b


PAIRS = [
    ("जल भी कहां था", "जल भी कहाँ था"),                  # Language
    ("बहुत खूब", "बहुत खूब।"),                           # Punctuation
    ("आओ [हवा]", "आओ [संगीत]"),                         # CC
    ("उसके मामा के पोते", "उसके मामा"),                   # Major
    ("राम राज आया", "रामराज आया"),                       # Minor
    *[(f"वह आया {n}", f"बह आया {n}") for n in range(5)],   # a repeated pair, five times
    ("सृष्टि से पहले", "♪ सृष्टि से पहले ♪"),             # song markers (ignored by default)
]


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path / "sessions")


_BUILT: dict = {}


def make(store, tmp_path, pairs=PAIRS, rules="default", name="LE1 BEK_50_Feltiv.sushila.docx"):
    """Open a session for the two files. The files are built once per test, because python-docx
    stamps the current time into each file and a rebuilt file would be a different file."""
    key = (str(tmp_path), tuple(pairs))
    if key not in _BUILT:
        a, b = lines(pairs)
        _BUILT[key] = (
            build(tmp_path / f"a{len(_BUILT)}.docx", a).read_bytes(),
            build(tmp_path / f"b{len(_BUILT)}.docx", b).read_bytes(),
        )
    a_bytes, b_bytes = _BUILT[key]
    return store.open(a_bytes, b_bytes, name, "LE2 b.docx", rules_name=rules)


@pytest.fixture
def session(store, tmp_path):
    return make(store, tmp_path)[0]


def by_category(session, category, **match):
    found = [i for i in session.items if i.category == category and i.in_play]
    return [i for i in found if all(getattr(i, k) == v for k, v in match.items())]


# the starting point ----------------------------------------------------------

def test_the_reviewed_counts_start_equal_to_the_engine_counts_and_everything_is_pending(session):
    assert session.counts() == session.engine_counts
    assert session.progress() == {
        "reviewed": 0, "total": sum(session.engine_counts.values()),
        "pending": sum(session.engine_counts.values()),
    }
    assert all(i.status in ("pending", "ignored") for i in session.items)


def test_every_count_is_the_number_of_rows_behind_it(session):
    for category in CATEGORIES:
        rows = [i for i in session.items if i.counts and i.category == category]
        assert len(rows) == session.counts()[category]


def test_ignored_differences_are_listed_but_not_counted(session):
    ignored = [i for i in session.items if i.status == "ignored"]
    assert ignored and all(not i.counts for i in ignored)
    assert all(i.ignored_because for i in ignored)
    assert sum(1 for i in session.items if i.counts) == sum(session.counts().values())


def test_items_know_their_row_on_the_screen(session):
    assert all(0 <= i.row < len(session.rows) for i in session.items)


# deciding --------------------------------------------------------------------

def test_confirm_marks_it_reviewed_without_changing_any_count(session):
    item = by_category(session, "Language")[0]
    before = session.counts()
    session.apply("confirm", item.id)
    assert item.status == "confirmed"
    assert session.counts() == before
    assert session.progress()["reviewed"] == 1


def test_changing_the_category_moves_the_counts_at_once_and_the_engine_number_stays(session):
    item = by_category(session, "Language")[0]
    engine = session.engine_counts
    session.apply("category", item.id, category="Major")
    assert item.status == "changed" and item.category == "Major"
    assert session.counts()["Language"] == engine["Language"] - 1
    assert session.counts()["Major"] == engine["Major"] + 1
    assert session.engine_counts == engine
    assert sum(session.counts().values()) == sum(engine.values())


def test_changing_back_to_the_engine_category_reads_as_confirmed(session):
    item = by_category(session, "Language")[0]
    session.apply("category", item.id, category="Major")
    session.apply("category", item.id, category="Language")
    assert item.status == "confirmed"


def test_not_a_mistake_takes_it_out_of_the_counts_but_keeps_it_visible(session):
    item = by_category(session, "Punctuation")[0]
    before = session.counts()["Punctuation"]
    session.apply("reject", item.id)
    assert item.status == "rejected"
    assert session.counts()["Punctuation"] == before - 1
    assert item in [i for i in session.items if i.status == "rejected"]
    assert sum(session.counts().values()) == sum(session.engine_counts.values()) - 1
    assert session.progress()["reviewed"] == 1


def test_reset_puts_a_decision_back_to_pending(session):
    item = by_category(session, "Punctuation")[0]
    session.apply("reject", item.id)
    session.apply("reset", item.id)
    assert item.status == "pending"
    assert session.counts() == session.engine_counts
    changed = by_category(session, "Language")[0]
    session.apply("category", changed.id, category="Minor")
    session.apply("reset", changed.id)
    assert changed.category == "Language" and changed.status == "pending"


def test_changing_your_mind_after_rejecting_puts_it_back_in_the_counts(session):
    item = by_category(session, "Punctuation")[0]
    before = session.counts()["Punctuation"]
    session.apply("reject", item.id)
    session.apply("confirm", item.id)                      # Enter on a rejected one: it is a mistake after all
    assert item.status == "confirmed" and not item.rejected
    assert session.counts()["Punctuation"] == before
    session.apply("reject", item.id)
    session.apply("category", item.id, category="Minor")   # or pick a category instead
    assert item.status == "changed" and session.counts()["Minor"] == session.engine_counts["Minor"] + 1


def test_a_note_is_kept_and_stripped(session):
    item = by_category(session, "CC")[0]
    session.apply("note", item.id, note="  tag wording is the editor's choice  ")
    assert item.reviewer_note == "tag wording is the editor's choice"
    assert item.status == "pending"


def test_a_bad_category_or_action_or_item_is_refused_in_plain_words(session):
    item = by_category(session, "Language")[0]
    with pytest.raises(ReviewError, match="six categories"):
        session.apply("category", item.id, category="Spelling")
    with pytest.raises(ReviewError, match="Unknown action"):
        session.apply("explode", item.id)
    with pytest.raises(ReviewError, match="no mistake number"):
        session.apply("confirm", 9999)
    assert session.counts() == session.engine_counts


# ignored differences ---------------------------------------------------------

def test_promoting_an_ignored_difference_counts_it(session):
    ignored = next(i for i in session.items if i.status == "ignored")
    before = dict(session.counts())
    session.apply("promote", ignored.id)
    assert ignored.status == "promoted" and ignored.counts
    assert session.counts()[ignored.category] == before[ignored.category] + 1
    assert session.progress()["total"] == sum(before.values()) + 1


def test_a_promoted_difference_can_take_another_category_and_be_put_back(session):
    ignored = next(i for i in session.items if i.status == "ignored")
    session.apply("promote", ignored.id, category="Minor")
    assert ignored.category == "Minor"
    session.apply("reset", ignored.id)
    assert ignored.status == "ignored" and not ignored.counts


def test_a_difference_that_is_already_counted_cannot_be_promoted_and_ignored_ones_cannot_be_judged(
    session,
):
    counted = by_category(session, "Language")[0]
    with pytest.raises(ReviewError, match="already counted"):
        session.apply("promote", counted.id)
    ignored = next(i for i in session.items if i.status == "ignored")
    with pytest.raises(ReviewError, match="not counted"):
        session.apply("confirm", ignored.id)


# repeated mistakes -----------------------------------------------------------

def repeated(session):
    (item,) = [i for i in session.items if i.category == "Repeated"]
    return item


def test_a_repeated_mistake_lists_every_occurrence_with_its_line(session):
    item = repeated(session)
    assert len(item.occurrences) == 5
    assert [o["a_text"] for o in item.occurrences] == ["वह"] * 5
    lines_seen = [o["line_no"] for o in item.occurrences]
    assert lines_seen == sorted(lines_seen)
    assert item.diffs == [o["diff"] for o in item.occurrences]


def test_splitting_off_an_occurrence_makes_it_its_own_mistake(session):
    item = repeated(session)
    engine = session.engine_counts
    created = session.apply("split", item.id, occurrences=[2])
    assert len(created) == 1 and len(item.occurrences) == 4
    (new,) = created
    assert new.source == "split" and new.category == item.base_category
    assert session.counts()["Repeated"] == engine["Repeated"]          # the group is still one
    assert session.counts()[new.category] == engine[new.category] + 1  # plus the split-off one


def test_splitting_several_leaves_the_group_and_can_be_confirmed_or_rejected_on_its_own(session):
    item = repeated(session)
    created = session.apply("split", item.id, occurrences=[1, 3])
    assert len(created) == 2 and len(item.occurrences) == 3
    session.apply("reject", created[0].id)
    session.apply("confirm", item.id)
    assert item.status == "confirmed" and created[0].status == "rejected"


def test_a_group_down_to_one_occurrence_goes_back_to_its_own_category(session):
    item = repeated(session)
    session.apply("split", item.id, occurrences=[1, 2, 3, 4])
    assert len(item.occurrences) == 1
    assert item.category == item.base_category != "Repeated"
    assert session.counts()["Repeated"] == 0


def test_the_group_is_split_by_position_so_the_first_occurrence_can_go_too(session):
    item = repeated(session)
    second_line = item.occurrences[1]["line_no"]
    session.apply("split", item.id, occurrences=[0])
    assert item.line_no == second_line          # the next occurrence now stands for the group


def test_a_split_must_leave_something_and_name_real_occurrences(session):
    item = repeated(session)
    with pytest.raises(ReviewError, match="stay in the group"):
        session.apply("split", item.id, occurrences=[0, 1, 2, 3, 4])
    with pytest.raises(ReviewError, match="Choose which"):
        session.apply("split", item.id, occurrences=[])
    with pytest.raises(ReviewError, match="Choose which"):
        session.apply("split", item.id, occurrences=[9])
    with pytest.raises(ReviewError, match="Only a repeated"):
        session.apply("split", by_category(session, "Language")[0].id, occurrences=[0])


# mistakes the engine missed --------------------------------------------------

def test_a_reviewer_can_add_a_mistake_from_selected_text(session):
    before = session.counts()["Major"]
    item = session.add_mistake("a", "  जल  भी  ", line_no=1, row=0, category="Major", note="why")
    assert item.a_text == "जल भी" and item.status == "added" and item.counts
    assert session.counts()["Major"] == before + 1
    assert session.progress()["total"] == sum(session.engine_counts.values()) + 1
    b_item = session.add_mistake("b", "हैं", line_no=3, row=1, category="Language")
    assert b_item.b_text == "हैं" and b_item.a_text == "" and b_item.b_line == 3


def test_adding_needs_text_a_real_side_and_a_real_category(session):
    with pytest.raises(ReviewError, match="Select some text"):
        session.add_mistake("a", "   ", 1, 0, "Major")
    with pytest.raises(ReviewError, match="file A or file B"):
        session.add_mistake("c", "x", 1, 0, "Major")
    with pytest.raises(ReviewError, match="six categories"):
        session.add_mistake("a", "x", 1, 0, "Nope")


def test_an_added_mistake_can_be_deleted_but_an_engine_one_cannot(session):
    item = session.add_mistake("a", "जल", 1, 0, "Major")
    before = session.counts()["Major"]
    session.apply("delete", item.id)
    assert session.counts()["Major"] == before - 1
    assert item.id not in [i["id"] for i in session.state()["items"]]
    with pytest.raises(ReviewError, match="Reject it instead"):
        session.apply("delete", by_category(session, "Language")[0].id)


# the log ---------------------------------------------------------------------

def test_every_decision_is_logged_with_the_time_the_action_and_what_changed(session):
    item = by_category(session, "Language")[0]
    session.apply("category", item.id, category="Major")
    session.apply("reject", item.id)
    session.add_mistake("a", "जल", 1, 0, "Minor")
    actions = [e["action"] for e in session.log]
    assert actions == ["category", "reject", "add"]
    first = session.log[0]
    assert datetime.strptime(first["t"], "%Y-%m-%dT%H:%M:%SZ").year >= 2026
    assert first["before"]["category"] == "Language" and first["after"]["category"] == "Major"
    assert first["id"] == item.id and first["key"] == item.key


def test_a_refused_action_leaves_no_log_entry(session):
    with pytest.raises(ReviewError):
        session.apply("category", by_category(session, "Language")[0].id, category="Bad")
    assert session.log == []


def test_all_actions_are_known():
    assert set(ACTIONS) >= {"confirm", "category", "reject", "reset", "note", "promote", "split"}


# saving and coming back ------------------------------------------------------

def test_the_same_two_files_get_the_same_id_and_different_files_do_not(store, tmp_path):
    first, _ = make(store, tmp_path)
    again, _ = make(store, tmp_path)
    other, _ = make(store, tmp_path, pairs=PAIRS[:3])
    assert first.id == again.id != other.id


def test_a_review_comes_back_where_it_stopped(store, tmp_path):
    session, outcome = make(store, tmp_path)
    assert outcome is None
    language = by_category(session, "Language")[0]
    punct = by_category(session, "Punctuation")[0]
    session.apply("category", language.id, category="Major")
    session.apply("reject", punct.id)
    session.apply("note", punct.id, note="comma is fine")
    store.save(session)
    counts, progress = session.counts(), session.progress()

    reopened, outcome = make(store, tmp_path)
    assert outcome == (len(session.items), 0)
    assert reopened.counts() == counts and reopened.progress() == progress
    assert reopened.items[language.id].category == "Major"
    assert reopened.items[punct.id].status == "rejected"
    assert reopened.items[punct.id].reviewer_note == "comma is fine"
    assert len(reopened.log) == 3


def test_added_mistakes_split_items_and_promotions_survive_a_restart(store, tmp_path):
    session, _ = make(store, tmp_path)
    group = repeated(session)
    (split,) = session.apply("split", group.id, occurrences=[1])
    ignored = next(i for i in session.items if i.status == "ignored")
    session.apply("promote", ignored.id, category="Minor")
    added = session.add_mistake("a", "जल", 1, 0, "Major", note="missed")
    store.save(session)
    expected = session.counts()

    reopened, outcome = make(store, tmp_path)
    assert reopened.counts() == expected
    assert outcome[1] == 0
    assert len(repeated(reopened).occurrences) == 4
    assert any(i.source == "split" and i.counts for i in reopened.items)
    assert any(i.source == "manual" and i.reviewer_note == "missed" for i in reopened.items)
    assert reopened.items[ignored.id].status == "promoted"
    assert split.category == "Language" or split.category  # created item restored with a category
    assert added.a_text == "जल"


def test_a_saved_review_can_be_opened_by_id_without_the_files(store, tmp_path):
    session, _ = make(store, tmp_path)
    session.apply("confirm", by_category(session, "Language")[0].id)
    store.save(session)
    reopened, _ = store.load(session.id)
    assert reopened.progress() == session.progress()
    with pytest.raises(ReviewError, match="not found"):
        store.load("nope")


def test_saving_writes_a_state_file_and_a_plain_decision_log(store, tmp_path):
    session, _ = make(store, tmp_path)
    session.apply("confirm", by_category(session, "Language")[0].id)
    session.apply("reject", by_category(session, "CC")[0].id)
    path = store.save(session)
    assert path.name == "state.json" and not list(path.parent.glob("*.tmp"))
    log_lines = (path.parent / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["action"] for line in log_lines] == ["confirm", "reject"]


def test_the_listing_shows_saved_reviews_with_their_progress(store, tmp_path):
    session, _ = make(store, tmp_path)
    session.apply("confirm", by_category(session, "Language")[0].id)
    store.save(session)
    (entry,) = store.listing()
    assert entry["id"] == session.id and entry["reviewed"] == 1
    assert entry["total"] == sum(session.engine_counts.values())


def test_a_saved_item_that_no_longer_exists_is_reported_not_crashed_on(store, tmp_path):
    session, _ = make(store, tmp_path)
    store.save(session)
    state = store.folder(session.id) / "state.json"
    saved = json.loads(state.read_text(encoding="utf-8"))
    saved["items"].append({
        "key": "gone", "source": "engine", "category": "Major", "reviewed": True,
        "rejected": False, "in_play": True, "note": "", "occurrences": [],
    })
    state.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    _, outcome = make(store, tmp_path)
    assert outcome[1] == 1


def test_a_review_saved_by_another_version_is_refused(store, tmp_path):
    session, _ = make(store, tmp_path)
    store.save(session)
    state = store.folder(session.id) / "state.json"
    saved = json.loads(state.read_text(encoding="utf-8"))
    saved["schema"] = 99
    state.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(ReviewError, match="different version"):
        make(store, tmp_path)


# exporting -------------------------------------------------------------------

def table_counts(path):
    cells = [c.text for row in Document(str(path)).tables[0].rows for c in row.cells]
    return {
        name: int(re.search(rf"{label}: (\d+)", " | ".join(cells)).group(1))
        for name, label in (
            ("Major", "Major Mistakes"), ("Language", "Language Mistakes"),
            ("Punctuation", "Punctuation Mistakes"), ("CC", "Cc mistakes"),
            ("Repeated", "Repeated Mistakes"), ("Minor", "Minor Mistakes"),
        )
    } | {"Total": int(re.search(r"Total Mistakes: (\d+)", " | ".join(cells)).group(1))}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_the_exported_table_has_the_reviewed_counts_not_the_engine_ones(session, tmp_path):
    session.apply("category", by_category(session, "Language")[0].id, category="Major")
    session.apply("reject", by_category(session, "Punctuation")[0].id)
    out = tmp_path / "qc.docx"
    session.export_docx(out)
    shown = table_counts(out)
    reviewed = session.counts()
    assert {k: shown[k] for k in CATEGORIES} == reviewed
    assert shown["Total"] == sum(reviewed.values()) == sum(session.engine_counts.values()) - 1
    assert shown != {**session.engine_counts, "Total": sum(session.engine_counts.values())}


def test_the_exported_document_still_tracks_every_difference_even_rejected_ones(session, tmp_path):
    from transcript_qc.revisions import comparable, revision_texts

    session.apply("reject", by_category(session, "Punctuation")[0].id)
    out = tmp_path / "qc.docx"
    session.export_docx(out, author="Reviewer")
    rejected, accepted = revision_texts(out)
    assert rejected[: len(session.comparison.a_paragraphs)] == session.comparison.a_paragraphs
    assert comparable(accepted) == comparable(session.comparison.b_paragraphs)


def test_the_csv_rows_marked_counted_are_exactly_the_rows_behind_the_reviewed_counts(
    session, tmp_path
):
    session.apply("category", by_category(session, "Language")[0].id, category="Minor")
    session.apply("reject", by_category(session, "CC")[0].id)
    session.add_mistake("a", "जल", 1, 0, "Major")
    ignored = next(i for i in session.items if i.status == "ignored")
    session.apply("promote", ignored.id)
    out = tmp_path / "m.csv"
    total = session.export_csv(out)
    rows = read_csv(out)
    assert len(rows) == total
    counted = [r for r in rows if r["counted"] == "yes"]
    for category in CATEGORIES:
        assert sum(1 for r in counted if r["final_category"] == category) == session.counts()[
            category
        ]
    assert len(counted) == sum(session.counts().values())


def test_the_csv_carries_engine_category_final_category_status_and_notes(session, tmp_path):
    language = by_category(session, "Language")[0]
    session.apply("category", language.id, category="Major")
    session.apply("note", language.id, note="really a different word")
    out = tmp_path / "m.csv"
    session.export_csv(out)
    assert tuple(read_csv(out)[0]) == session.CSV_COLUMNS
    row = next(r for r in read_csv(out) if r["a_text"] == "कहां")
    assert (row["engine_category"], row["final_category"], row["status"]) == (
        "Language", "Major", "changed",
    )
    assert row["reviewer_note"] == "really a different word" and row["rule_id"] == "LANG_MARKS"


def test_the_csv_lists_ignored_and_repeated_copies_but_does_not_count_them(session, tmp_path):
    out = tmp_path / "m.csv"
    session.export_csv(out)
    rows = read_csv(out)
    assert any(r["status"] == "ignored" and r["counted"] == "no" for r in rows)
    assert sum(1 for r in rows if r["status"] == "repeat") == 4
    assert all(r["counted"] == "no" for r in rows if r["status"] in ("repeat", "ignored"))


def test_the_summary_details_can_be_edited_before_export(session, tmp_path):
    assert session.details.writer == "Sushila" and session.details.episode == "50"
    session.set_details("Other Show", None, "51")
    out = tmp_path / "qc.docx"
    session.export_docx(out)
    cells = [c.text for c in Document(str(out)).tables[0].rows[0].cells]
    assert cells == ["Movie Name: Other Show", "Written By: Sushila", "Episode: 51"]


# the state the screen reads --------------------------------------------------

def test_the_state_is_plain_json_and_has_what_the_screen_needs(session):
    state = json.loads(json.dumps(session.state(), ensure_ascii=False))
    wanted = {"id", "details", "engine_counts", "counts", "progress", "items", "row_count"}
    assert wanted <= set(state)
    item = state["items"][0]
    assert {"id", "status", "category", "engine_category", "a_text", "b_text", "line_no", "rule_id",
            "engine_note", "confidence", "row", "counts", "occurrences"} <= set(item)
    rows = json.loads(json.dumps(session.rows_json(), ensure_ascii=False))
    assert len(rows) == state["row_count"]
    assert rows[0]["a"][0]["segments"][0][1] in (-1, 0)


def test_files_that_are_not_word_documents_are_refused_with_a_plain_message(store):
    with pytest.raises(ReviewError, match="a.docx is not a Word .docx file"):
        store.open(b"not a docx", b"also not", "a.docx", "b.docx")


def test_a_file_with_no_text_is_refused(store, tmp_path):
    empty = build(tmp_path / "empty.docx", ["", ""])
    full = build(tmp_path / "full.docx", ["एक दो"])
    with pytest.raises(ReviewError, match="has no text"):
        store.open(empty.read_bytes(), full.read_bytes(), "empty.docx", "full.docx")
    with pytest.raises(ReviewError, match="has no text"):
        store.open(full.read_bytes(), empty.read_bytes(), "full.docx", "empty.docx")
