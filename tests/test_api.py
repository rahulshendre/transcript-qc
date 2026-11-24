import csv
import io
import json
import re

import pytest
from docx import Document
from fastapi.testclient import TestClient
from helpers import build
from test_review import PAIRS, lines

from transcript_qc.revisions import comparable, revision_texts
from transcript_qc.rules import CATEGORIES
from transcript_qc.web.app import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "sessions"))


@pytest.fixture
def docs(tmp_path):
    a, b = lines(PAIRS)
    return (
        build(tmp_path / "LE1 BEK_50_Feltiv.sushila.docx", a).read_bytes(),
        build(tmp_path / "LE2 BEK_50_Chandrakala.docx", b).read_bytes(),
    )


def upload(client, docs, **form):
    files = {
        "file_a": ("LE1 BEK_50_Feltiv.sushila.docx", docs[0]),
        "file_b": ("LE2 BEK_50_Chandrakala.docx", docs[1]),
    }
    return client.post("/api/sessions", files=files, data=form)


def first(state, category):
    return next(i for i in state["items"] if i["category"] == category and i["counts"])


# uploading -------------------------------------------------------------------

def test_uploading_two_files_returns_the_review_state(client, docs):
    response = upload(client, docs)
    assert response.status_code == 200
    state = response.json()
    assert state["engine_counts"] == state["counts"]
    assert state["progress"]["reviewed"] == 0 and state["progress"]["total"] > 0
    assert state["details"] == {"movie": "Bharat Ek Khoj", "writer": "Sushila", "episode": "50"}
    assert state["restored"] is None
    assert len(state["items"]) >= state["progress"]["total"]


def test_the_details_can_be_edited_on_the_start_screen(client, docs):
    state = upload(client, docs, movie="Other Show", writer="Mala", episode="51").json()
    assert state["details"] == {"movie": "Other Show", "writer": "Mala", "episode": "51"}


def test_the_strict_profile_can_be_chosen(client, docs):
    default = upload(client, docs).json()
    strict = upload(client, docs, rules="strict").json()
    assert strict["counts"] != default["counts"] and strict["rules"] == "strict"


def test_bad_uploads_get_plain_messages(client, docs):
    bad = upload(client, (b"nope", docs[1])).json()["detail"]
    assert bad == "LE1 BEK_50_Feltiv.sushila.docx is not a Word .docx file, or it is damaged."
    nothing = {"file_a": ("a.docx", b""), "file_b": ("b.docx", b"")}
    empty = client.post("/api/sessions", files=nothing)
    assert empty.status_code == 400 and "both files" in empty.json()["detail"]
    assert upload(client, docs, rules="loose").json()["detail"].startswith("Unknown rules")
    assert client.post("/api/sessions").status_code == 422


# the rows and the state ------------------------------------------------------

def test_the_start_screen_can_ask_what_a_file_name_says(client):
    found = client.get("/api/details", params={"file_name": "LE1 BEK_50_Feltiv.sushila.docx"})
    assert found.json() == {"movie": "Bharat Ek Khoj", "writer": "Sushila", "episode": "50"}
    assert client.get("/api/details", params={"file_name": "x.docx", "rules": "no"}).status_code == 400


def test_the_side_by_side_rows_are_served(client, docs):
    state = upload(client, docs).json()
    rows = client.get(f"/api/sessions/{state['id']}/rows").json()
    assert len(rows) == state["row_count"]
    assert all({"index", "a", "b"} <= set(r) for r in rows)
    assert all(0 <= i["row"] < len(rows) for i in state["items"])


def test_an_unknown_review_is_a_clear_404(client):
    response = client.get("/api/sessions/nope")
    assert response.status_code == 404 and "not found" in response.json()["detail"]


# deciding, live counts -------------------------------------------------------

def act(client, state, item, **body):
    return client.post(f"/api/sessions/{state['id']}/items/{item['id']}", json=body)


def test_a_decision_returns_the_new_counts_at_once(client, docs):
    state = upload(client, docs).json()
    item = first(state, "Language")
    response = act(client, state, item, action="category", category="Major")
    data = response.json()
    assert response.status_code == 200
    assert data["item"]["category"] == "Major" and data["item"]["status"] == "changed"
    assert data["counts"]["Language"] == state["counts"]["Language"] - 1
    assert data["counts"]["Major"] == state["counts"]["Major"] + 1
    assert data["progress"]["reviewed"] == 1


def test_confirm_reject_reset_and_note_over_the_api(client, docs):
    state = upload(client, docs).json()
    item = first(state, "Punctuation")
    assert act(client, state, item, action="confirm").json()["item"]["status"] == "confirmed"
    rejected = act(client, state, item, action="reject").json()
    assert rejected["item"]["status"] == "rejected"
    assert rejected["counts"]["Punctuation"] == state["counts"]["Punctuation"] - 1
    assert act(client, state, item, action="reset").json()["item"]["status"] == "pending"
    noted = act(client, state, item, action="note", note="fine as it is").json()
    assert noted["item"]["reviewer_note"] == "fine as it is"


def test_a_refused_decision_is_a_400_with_the_reason(client, docs):
    state = upload(client, docs).json()
    response = act(client, state, first(state, "Language"), action="category", category="Nope")
    assert response.status_code == 400 and "six categories" in response.json()["detail"]
    assert act(client, state, {"id": 9999}, action="confirm").status_code == 404
    assert act(client, state, first(state, "Language"), action="explode").status_code == 400


def test_promoting_an_ignored_difference(client, docs):
    state = upload(client, docs).json()
    ignored = next(i for i in state["items"] if i["status"] == "ignored")
    data = act(client, state, ignored, action="promote").json()
    assert data["item"]["status"] == "promoted"
    assert sum(data["counts"].values()) == sum(state["counts"].values()) + 1


def test_splitting_a_repeated_mistake_returns_the_new_item(client, docs):
    state = upload(client, docs).json()
    group = first(state, "Repeated")
    assert len(group["occurrences"]) == 5
    data = act(client, state, group, action="split", occurrences=[1]).json()
    assert len(data["created"]) == 1 and data["created"][0]["source"] == "split"
    assert len(data["item"]["occurrences"]) == 4


def test_adding_a_mistake_from_selected_text(client, docs):
    state = upload(client, docs).json()
    body = {"side": "a", "text": "जल भी", "line_no": 1, "row": 0, "category": "Major", "note": "x"}
    data = client.post(f"/api/sessions/{state['id']}/items", json=body).json()
    assert data["item"]["status"] == "added"
    assert data["counts"]["Major"] == state["counts"]["Major"] + 1
    bad = client.post(f"/api/sessions/{state['id']}/items", json={**body, "text": " "})
    assert bad.status_code == 400


# saving and coming back ------------------------------------------------------

def test_decisions_are_saved_as_they_are_made_and_come_back_on_a_new_server(tmp_path, docs):
    sessions = tmp_path / "keep"
    first_client = TestClient(create_app(sessions))
    state = upload(first_client, docs).json()
    act(first_client, state, first(state, "Language"), action="category", category="Minor")

    second_client = TestClient(create_app(sessions))          # the app was closed and reopened
    reopened = upload(second_client, docs).json()
    assert reopened["restored"]["items"] > 0 and reopened["restored"]["missing"] == 0
    assert reopened["progress"]["reviewed"] == 1
    assert reopened["counts"]["Minor"] == state["counts"]["Minor"] + 1
    listing = second_client.get("/api/sessions").json()
    assert [e["id"] for e in listing] == [state["id"]]
    by_id = second_client.get(f"/api/sessions/{state['id']}").json()
    assert by_id["counts"] == reopened["counts"]


def test_the_save_button_writes_the_session(client, docs, tmp_path):
    state = upload(client, docs).json()
    response = client.post(f"/api/sessions/{state['id']}/save")
    assert response.json()["saved"] is True


def test_the_decision_log_is_available(client, docs):
    state = upload(client, docs).json()
    act(client, state, first(state, "Language"), action="confirm")
    log = client.get(f"/api/sessions/{state['id']}/log").json()
    assert [e["action"] for e in log] == ["confirm"]


# exporting -------------------------------------------------------------------

def table_total(content):
    cells = [c.text for row in Document(io.BytesIO(content)).tables[0].rows for c in row.cells]
    return int(re.search(r"Total Mistakes: (\d+)", " | ".join(cells))[1])


def test_exporting_with_pending_mistakes_is_refused_until_forced(client, docs):
    state = upload(client, docs).json()
    refused = client.get(f"/api/sessions/{state['id']}/export/docx")
    assert refused.status_code == 409 and "still pending" in refused.json()["detail"]
    assert client.get(f"/api/sessions/{state['id']}/export/csv").status_code == 409
    assert client.get(f"/api/sessions/{state['id']}/export/docx?force=true").status_code == 200


def test_the_exported_document_matches_the_reviewed_counts_and_the_csv(client, docs):
    state = upload(client, docs).json()
    act(client, state, first(state, "Language"), action="category", category="Major")
    act(client, state, first(state, "Punctuation"), action="reject")
    live = client.get(f"/api/sessions/{state['id']}").json()["counts"]

    docx = client.get(f"/api/sessions/{state['id']}/export/docx?force=true")
    assert docx.status_code == 200
    assert "filename" in docx.headers["content-disposition"] and "_QC.docx" in (
        docx.headers["content-disposition"]
    )
    assert table_total(docx.content) == sum(live.values())

    csv_response = client.get(f"/api/sessions/{state['id']}/export/csv?force=true")
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    counted = [r for r in rows if r["counted"] == "yes"]
    assert {c: sum(1 for r in counted if r["final_category"] == c) for c in CATEGORIES} == live


def test_the_exported_document_round_trips(client, docs, tmp_path):
    state = upload(client, docs).json()
    docx = client.get(f"/api/sessions/{state['id']}/export/docx?force=true&author=Reviewer")
    path = tmp_path / "out.docx"
    path.write_bytes(docx.content)
    rejected, accepted = revision_texts(path)
    a_paragraphs = [p.text for p in Document(io.BytesIO(docs[0])).paragraphs]
    b_paragraphs = [p.text for p in Document(io.BytesIO(docs[1])).paragraphs]
    assert rejected[: len(a_paragraphs)] == a_paragraphs
    assert comparable(accepted) == comparable(b_paragraphs)
    assert b"Reviewer" in __import__("zipfile").ZipFile(path).read("word/document.xml")


def test_editing_the_details_changes_the_exported_table(client, docs):
    state = upload(client, docs).json()
    changed = client.patch(
        f"/api/sessions/{state['id']}/details", json={"movie": "Another", "episode": "7"}
    ).json()
    assert changed["details"] == {"movie": "Another", "writer": "Sushila", "episode": "7"}
    content = client.get(f"/api/sessions/{state['id']}/export/docx?force=true").content
    cells = [c.text for c in Document(io.BytesIO(content)).tables[0].rows[0].cells]
    assert cells == ["Movie Name: Another", "Written By: Sushila", "Episode: 7"]


def test_everything_is_json(client, docs):
    state = upload(client, docs).json()
    json.dumps(state, ensure_ascii=False)
    assert client.get("/api/health").json()["ok"] is True


def test_without_a_built_page_the_root_explains_what_to_do(tmp_path, monkeypatch):
    from transcript_qc.web import app as web_app

    monkeypatch.setattr(web_app, "STATIC", tmp_path / "missing")
    page = TestClient(web_app.create_app(tmp_path / "s")).get("/")
    assert page.status_code == 200 and "has not been built" in page.text


def test_upload_refuses_a_file_with_tracked_changes_by_its_real_name(client, docs, tmp_path):
    from helpers import make_qc

    qc, _, _ = make_qc(tmp_path, ["जल भी कहां था"], ["जल भी कहाँ था"])
    files = {"file_a": ("already_reviewed.docx", qc.read_bytes()), "file_b": ("B.docx", docs[1])}
    response = client.post("/api/sessions", files=files)
    assert response.status_code == 400
    assert "already_reviewed.docx has tracked changes" in response.json()["detail"]


def test_upload_reports_a_table_instead_of_hiding_it(client, docs, tmp_path):
    path = tmp_path / "with_table.docx"
    path.write_bytes(docs[0])
    doc = Document(str(path))
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "तालिका"
    doc.save(path)
    files = {"file_a": ("My transcript.docx", path.read_bytes()), "file_b": ("B.docx", docs[1])}
    state = client.post("/api/sessions", files=files).json()
    assert state["warnings"] == ["My transcript.docx has 1 table. Text inside tables is not compared."]
    assert upload(client, docs).json()["warnings"] == []
