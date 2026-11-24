"""The review screen in a real browser: keyboard only, live counts, exports, save and restore.

These start the actual server and drive Chrome the way a reviewer would. They are skipped when
no browser can be started (set TRANSCRIPT_QC_SKIP_E2E=1 to skip them on purpose).
"""

import csv
import io
import os
import re
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from docx import Document
from helpers import build
from test_review import PAIRS, lines

from transcript_qc.rules import CATEGORIES
from transcript_qc.web.app import create_app

playwright_sync = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(
    bool(os.environ.get("TRANSCRIPT_QC_SKIP_E2E")), reason="end-to-end tests switched off"
)

VIEWPORT = {"width": 1366, "height": 768}
DATA = Path(__file__).resolve().parent.parent / "data" / "ep50"
EP_A = DATA / "LE1 BEK_50_Feltiv.sushila.docx"
EP_B = DATA / "LE2 BHARAT EK KHOJ_EP_50_Chandrakala.docx"


@pytest.fixture(scope="session")
def browser():
    with playwright_sync.sync_playwright() as p:
        try:
            launched = p.chromium.launch(channel="chrome")
        except Exception:
            try:
                launched = p.chromium.launch()
            except Exception as error:
                pytest.skip(f"no browser available: {error}")
        yield launched
        launched.close()


class Server:
    def __init__(self, sessions):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        config = uvicorn.Config(create_app(sessions), host="127.0.0.1", port=self.port,
                                log_level="error")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.fixture
def server(tmp_path):
    started = Server(tmp_path / "sessions")
    yield started
    started.stop()


@pytest.fixture
def files(tmp_path):
    a, b = lines(PAIRS)
    return (
        build(tmp_path / "LE1 BEK_50_Feltiv.sushila.docx", a),
        build(tmp_path / "LE2 BEK_50_Chandrakala.docx", b),
    )


@pytest.fixture
def page(browser, server):
    context = browser.new_context(viewport=VIEWPORT, accept_downloads=True)
    page = context.new_page()
    page.requests = []
    page.errors = []
    page.on("request", lambda r: page.requests.append(r.url))
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.server = server
    yield page
    context.close()


def eventually(page, condition, timeout=5.0):
    """Wait for something on the screen to become true, the way a person would."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if condition():
                return
        except Exception:
            pass
        page.wait_for_timeout(40)
    assert condition()


def open_review(page, a, b):
    page.goto(page.server.url)
    page.set_input_files("[data-testid=file-a]", str(a))
    page.set_input_files("[data-testid=file-b]", str(b))
    page.click("[data-testid=compare]")
    page.wait_for_selector("[data-testid=card-Major]", timeout=60000)
    page.wait_for_selector("[data-testid=row-0]", timeout=60000)


def counts(page):
    return {c: int(page.get_attribute(f"[data-testid=card-{c}]", "data-reviewed"))
            for c in CATEGORIES}


def engine_counts(page):
    return {c: int(page.get_attribute(f"[data-testid=card-{c}]", "data-engine"))
            for c in CATEGORIES}


def progress(page):
    text = page.inner_text("[data-testid=progress]")
    done, total = re.search(r"Reviewed (\d+) of (\d+)", text).groups()
    return int(done), int(total)


def selected_id(page):
    return int(page.get_attribute("[data-testid=detail]", "data-item"))


def selected_category(page):
    return page.inner_text("[data-testid=detail-category]")


def table_counts(content):
    cells = [c.text for row in Document(io.BytesIO(content)).tables[0].rows for c in row.cells]
    joined = " | ".join(cells)
    labels = {"Major": "Major Mistakes", "Language": "Language Mistakes",
              "Punctuation": "Punctuation Mistakes", "CC": "Cc mistakes",
              "Repeated": "Repeated Mistakes", "Minor": "Minor Mistakes"}
    return {k: int(re.search(rf"{v}: (\d+)", joined)[1]) for k, v in labels.items()}


# the start screen --------------------------------------------------------------------------------

def test_the_start_screen_fills_the_details_from_a_s_file_name(page, files):
    page.goto(page.server.url)
    assert page.is_disabled("[data-testid=compare]")
    page.set_input_files("[data-testid=file-a]", str(files[0]))
    page.wait_for_function("document.querySelector('[data-testid=detail-movie]').value !== ''")
    assert page.input_value("[data-testid=detail-movie]") == "Bharat Ek Khoj"
    assert page.input_value("[data-testid=detail-writer]") == "Sushila"
    assert page.input_value("[data-testid=detail-episode]") == "50"
    assert page.is_disabled("[data-testid=compare]")          # still needs file B
    page.fill("[data-testid=detail-episode]", "51")
    page.set_input_files("[data-testid=file-b]", str(files[1]))
    assert not page.is_disabled("[data-testid=compare]")


def test_a_file_that_is_not_a_word_document_gets_a_plain_message(page, tmp_path, files):
    bad = tmp_path / "notes.docx"
    bad.write_bytes(b"this is not a docx")
    page.goto(page.server.url)
    page.set_input_files("[data-testid=file-a]", str(bad))
    page.set_input_files("[data-testid=file-b]", str(files[1]))
    page.click("[data-testid=compare]")
    page.wait_for_selector("[data-testid=upload-error]")
    assert "could not be read as a Word" in page.inner_text("[data-testid=upload-error]")


# scorecard and filtering -------------------------------------------------------------------------------

def test_the_scorecard_starts_at_the_engine_counts_with_everything_pending(page, files):
    open_review(page, *files)
    assert counts(page) == engine_counts(page)
    done, total = progress(page)
    assert done == 0 and total == sum(counts(page).values())
    assert int(page.get_attribute("[data-testid=card-Total]", "data-reviewed")) == total


def test_clicking_a_count_lists_exactly_that_many_mistakes(page, files):
    open_review(page, *files)
    for category in CATEGORIES:
        page.click(f"[data-testid=card-{category}]")
        shown = page.locator("[data-testid^=item-]").count()
        assert shown == counts(page)[category], category
        assert page.inner_text("[data-testid=list-count]").startswith(f"{shown} ")
        cats = page.locator("[data-testid^=item-]").evaluate_all(
            "els => els.map(e => e.dataset.category)"
        )
        assert set(cats) <= {category}


def test_every_count_can_be_drilled_into_and_the_list_can_be_sorted(page, files):
    open_review(page, *files)
    page.select_option("[data-testid=sort]", "category")
    cats = page.locator("[data-testid^=item-]").evaluate_all("els => els.map(e => e.dataset.category)")
    assert cats == sorted(cats, key=CATEGORIES.index)
    page.select_option("[data-testid=sort]", "uncertain")
    assert page.locator("[data-testid^=item-]").count() == sum(counts(page).values())


# keyboard only -----------------------------------------------------------------------------------------------

def test_a_whole_review_can_be_done_with_the_keyboard_alone(page, files, tmp_path):
    open_review(page, *files)
    first = selected_id(page)
    start = counts(page)

    page.keyboard.press("j")                                  # next
    eventually(page, lambda: selected_id(page) != first)
    page.keyboard.press("k")                                  # back
    eventually(page, lambda: selected_id(page) == first)

    # change the category of the selected mistake: the count moves at once
    before_category = selected_category(page)
    target = "Minor" if before_category != "Minor" else "Major"
    key = str(CATEGORIES.index(target) + 1)
    page.keyboard.press(key)
    eventually(page, lambda: counts(page)[target] == start[target] + 1)
    after = counts(page)
    assert after[before_category] == start[before_category] - 1
    card = page.locator(f"[data-testid=card-{target}]")
    assert "changed" in card.get_attribute("class")           # the difference is highlighted
    assert card.get_attribute("data-engine") == str(start[target])
    eventually(page, lambda: progress(page)[0] == 1)

    # reject the next one with X: out of the counts
    eventually(page, lambda: selected_id(page) != first)       # moved on to the next pending one
    rejected_id = selected_id(page)
    rejected_category = selected_category(page)
    page.keyboard.press("x")
    eventually(page, lambda: counts(page)[rejected_category] == after[rejected_category] - 1)
    page.click("[data-testid=filter-rejected]")
    eventually(page, lambda: page.locator(f"[data-testid=item-{rejected_id}]").count() == 1)
    page.click("[data-testid=filter-counted]")

    # confirm everything left with Enter, nothing but the keyboard
    while progress(page)[0] < progress(page)[1]:
        before = progress(page)[0]
        page.keyboard.press("Enter")
        eventually(page, lambda before=before: progress(page)[0] == before + 1)
    done, total = progress(page)
    assert done == total

    # export: no warning now that nothing is pending, and the files match the screen
    live = counts(page)
    with page.expect_download() as download:
        page.click("[data-testid=export-docx]")
    docx = tmp_path / "out.docx"
    download.value.save_as(docx)
    assert table_counts(docx.read_bytes()) == live
    with page.expect_download() as download:
        page.click("[data-testid=export-csv]")
    path = tmp_path / "out.csv"
    download.value.save_as(path)
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    counted = [r for r in rows if r["counted"] == "yes"]
    assert {c: sum(1 for r in counted if r["final_category"] == c) for c in CATEGORIES} == live
    changed = next(r for r in rows if r["status"] == "changed")
    assert changed["final_category"] == target and changed["engine_category"] == before_category


def test_typing_a_note_does_not_trigger_the_shortcuts(page, files):
    open_review(page, *files)
    item = selected_id(page)
    start = (counts(page), progress(page))
    page.keyboard.press("n")
    assert page.evaluate("document.activeElement.dataset.testid") == "note"
    page.keyboard.type("jxu1 kEnter 2")
    page.wait_for_timeout(300)
    assert selected_id(page) == item and (counts(page), progress(page)) == start
    page.keyboard.press("Control+Enter")
    page.wait_for_function("document.activeElement.tagName !== 'TEXTAREA'")
    page.click("[data-testid=filter-counted]")
    assert page.input_value("[data-testid=note]") == "jxu1 kEnter 2"


def test_undo_and_the_help_overlay(page, files):
    open_review(page, *files)
    page.keyboard.press("x")
    page.keyboard.press("k")
    page.keyboard.press("u")
    assert page.get_attribute("[data-testid=detail]", "data-item") is not None
    page.keyboard.press("?")
    eventually(page, lambda: page.is_visible("[data-testid=help]"))
    page.keyboard.press("j")                                   # ignored while help is open
    page.keyboard.press("Escape")
    eventually(page, lambda: not page.is_visible("[data-testid=help]"))


# the decisions behind the numbers ---------------------------------------------------------------------------------

def test_not_a_mistake_removes_it_from_the_count_but_keeps_it_listed(page, files):
    open_review(page, *files)
    page.click("[data-testid=card-Punctuation]")
    item = int(page.locator("[data-testid^=item-]").first.get_attribute("data-testid").split("-")[1])
    page.click(f"[data-testid=item-{item}]")
    before = counts(page)["Punctuation"]
    page.click("[data-testid=reject]")
    eventually(page, lambda: counts(page)["Punctuation"] == before - 1)
    page.click("[data-testid=filter-rejected]")
    eventually(page, lambda: page.locator(f"[data-testid=item-{item}]").count() == 1)
    page.click(f"[data-testid=item-{item}]")
    page.click("[data-testid=reset]")
    eventually(page, lambda: counts(page)["Punctuation"] == before)


def test_an_ignored_difference_can_be_counted_by_the_reviewer(page, files):
    open_review(page, *files)
    page.click("[data-testid=filter-ignored]")
    assert page.locator("[data-testid^=item-]").count() >= 1
    page.locator("[data-testid^=item-]").first.click()
    assert page.is_visible("[data-testid=promote]")
    total = sum(counts(page).values())
    page.keyboard.press("p")
    eventually(page, lambda: sum(counts(page).values()) == total + 1)


def test_a_repeated_mistake_can_be_split_into_separate_mistakes(page, files):
    open_review(page, *files)
    page.click("[data-testid=card-Repeated]")
    page.locator("[data-testid^=item-]").first.click()
    assert page.locator("[data-testid=occurrences] li").count() == 5
    page.check("[data-testid=occ-1]")
    page.check("[data-testid=occ-3]")
    base_before = sum(counts(page).values())
    page.click("[data-testid=split]")
    eventually(page, lambda: sum(counts(page).values()) == base_before + 2)
    eventually(page, lambda: page.locator("[data-testid=occurrences] li").count() == 3)


def test_selecting_text_and_pressing_a_number_adds_a_mistake(page, files):
    open_review(page, *files)
    before = counts(page)
    page.locator("[data-testid=rows] .cell-a .line").first.click(click_count=3)
    assert page.is_visible("[data-testid=add-box]")
    page.keyboard.press("2")                                    # Language
    eventually(page, lambda: counts(page)["Language"] == before["Language"] + 1)
    eventually(page, lambda: page.inner_text("[data-testid=detail-status]") == "added by you")
    eventually(page, lambda: not page.is_visible("[data-testid=add-box]"))


# warnings, saving, restoring ----------------------------------------------------------------------------------------

def test_exporting_with_pending_mistakes_asks_first(page, files, tmp_path):
    open_review(page, *files)
    page.click("[data-testid=export-docx]")
    eventually(page, lambda: page.is_visible("[data-testid=confirm-export]"))
    assert "still pending" in page.inner_text("[data-testid=confirm-export]")
    page.click("[data-testid=keep-reviewing]")
    eventually(page, lambda: not page.is_visible("[data-testid=confirm-export]"))
    page.click("[data-testid=export-docx]")
    eventually(page, lambda: page.is_visible("[data-testid=export-anyway]"))
    with page.expect_download() as download:
        page.click("[data-testid=export-anyway]")
    saved = tmp_path / "x.docx"
    download.value.save_as(saved)
    assert table_counts(saved.read_bytes()) == counts(page)


def test_a_review_comes_back_where_it_stopped_after_the_page_is_reloaded(page, files):
    open_review(page, *files)
    page.keyboard.press("5")                                    # change the first item to Repeated
    eventually(page, lambda: progress(page)[0] == 1)
    page.keyboard.press("x")
    eventually(page, lambda: progress(page)[0] == 2)
    stopped = (counts(page), progress(page))
    page.reload()
    assert page.is_visible("text=Pick up where you stopped")
    page.set_input_files("[data-testid=file-a]", str(files[0]))
    page.set_input_files("[data-testid=file-b]", str(files[1]))
    page.click("[data-testid=compare]")
    page.wait_for_selector("[data-testid=card-Major]")
    assert page.is_visible("text=Picked up where you stopped")
    assert (counts(page), progress(page)) == stopped


def test_a_saved_review_can_be_resumed_from_the_start_screen(page, files):
    open_review(page, *files)
    page.keyboard.press("Enter")
    eventually(page, lambda: progress(page)[0] == 1)
    stopped = (counts(page), progress(page))
    page.keyboard.press("Control+s")
    page.wait_for_selector("text=Saved.")
    page.reload()
    page.click("text=with LE2")
    page.wait_for_selector("[data-testid=card-Major]")
    assert (counts(page), progress(page)) == stopped


# layout, scrolling, fonts, offline ---------------------------------------------------------------------------------------

def test_everything_fits_a_1366_by_768_screen_without_page_scrolling(page, files):
    open_review(page, *files)
    sizes = page.evaluate(
        "[document.documentElement.scrollWidth, document.documentElement.clientWidth,"
        " document.documentElement.scrollHeight, document.documentElement.clientHeight]"
    )
    assert sizes == [1366, 1366, 768, 768]
    for selector in ("[data-testid=export-docx]", "[data-testid=card-Total]",
                     "[data-testid=rows]", "[data-testid=detail]", "[data-testid=item-0]"):
        box = page.locator(selector).first.bounding_box()
        assert box and box["width"] > 40 and box["height"] > 10, selector
        assert 0 <= box["x"] and box["x"] + box["width"] <= 1366 + 1, selector
        assert 0 <= box["y"] and box["y"] + box["height"] <= 768 + 1, selector


def test_it_works_with_no_internet_and_the_devanagari_font_comes_from_the_app(page, files):
    external = []
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(
        page.server.url) or route.request.url.startswith("data:") else
        (external.append(route.request.url), route.abort()))
    open_review(page, *files)
    assert external == []
    assert page.evaluate("document.fonts.check('16px \"Noto Sans Devanagari\"')")
    loaded = page.evaluate(
        "[...document.fonts].filter(f => f.family.includes('Noto Sans Devanagari') "
        "&& f.status === 'loaded').length"
    )
    assert loaded >= 1
    assert all(u.startswith(page.server.url) or u.startswith("data:") for u in page.requests)
    assert page.errors == []


# the real episode ------------------------------------------------------------------------------------------------------------

episode = pytest.mark.skipif(not (EP_A.is_file() and EP_B.is_file()), reason="Episode 50 not found")


@episode
def test_episode_50_opens_in_well_under_a_minute_and_every_card_drills_down(page):
    started = time.perf_counter()
    open_review(page, EP_A, EP_B)
    assert time.perf_counter() - started < 60
    assert counts(page) == {"Major": 52, "Language": 29, "Punctuation": 66, "CC": 10,
                            "Repeated": 6, "Minor": 11}
    for category in CATEGORIES:
        page.click(f"[data-testid=card-{category}]")
        assert page.locator("[data-testid^=item-]").count() == counts(page)[category]


@episode
def test_episode_50_scrolls_the_side_by_side_view_to_the_selected_mistake(page):
    open_review(page, EP_A, EP_B)
    page.select_option("[data-testid=sort]", "line")
    pane = page.locator("[data-testid=rows]")
    positions = []
    for index in (-1, len(page.locator("[data-testid^=item-]").all()) // 2, 0):
        page.locator("[data-testid^=item-]").nth(index).click()
        eventually(page, lambda: page.locator(".row-active").count() == 1)
        page.wait_for_timeout(150)
        box, bounds = page.locator(".row-active").bounding_box(), pane.bounding_box()
        assert bounds["y"] - 2 <= box["y"] <= bounds["y"] + bounds["height"] + 2
        positions.append(page.evaluate("document.querySelector('[data-testid=rows]').scrollTop"))
    assert len(set(positions)) == 3                       # the view really moved each time


@episode
def test_episode_50_keyboard_review_of_forty_mistakes_is_quick_and_exports_match(page, tmp_path):
    open_review(page, EP_A, EP_B)
    started = time.perf_counter()
    for _ in range(40):
        before = progress(page)[0]
        page.keyboard.press("Enter")
        eventually(page, lambda before=before: progress(page)[0] == before + 1)
    elapsed = time.perf_counter() - started
    assert progress(page) == (40, 174)
    assert elapsed < 60
    live = counts(page)
    page.click("[data-testid=export-docx]")
    eventually(page, lambda: page.is_visible("[data-testid=export-anyway]"))
    with page.expect_download() as download:
        page.click("[data-testid=export-anyway]")
    docx = tmp_path / "ep.docx"
    download.value.save_as(docx)
    assert table_counts(docx.read_bytes()) == live
