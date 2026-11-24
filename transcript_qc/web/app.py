"""The review screen's server: FastAPI, running on the reviewer's own computer.

Nothing leaves the machine and nothing needs the internet. The browser page is built once and
served from transcript_qc/web/static, so the reviewer only needs Python.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from transcript_qc.review import ReviewError, ReviewSession, SessionStore
from transcript_qc.rules import PROFILES, load_rules
from transcript_qc.summary import details_from_name
from transcript_qc.writer import DEFAULT_AUTHOR

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 50 * 1024 * 1024
_NO_BUILD = """<!doctype html><meta charset="utf-8"><title>Transcript QC</title>
<body style="font:16px system-ui;max-width:40em;margin:3em auto">
<h1>The review screen has not been built yet</h1>
<p>Run <code>npm install &amp;&amp; npm run build</code> in the <code>frontend</code> folder,
then reload this page. The API is already running at <a href="/docs">/docs</a>.</p></body>"""


def default_home() -> Path:
    return Path(os.environ.get("TRANSCRIPT_QC_HOME") or Path.home() / "Transcript QC")


class ActionBody(BaseModel):
    action: str
    category: str | None = None
    note: str | None = None
    occurrences: list[int] | None = None


class AddBody(BaseModel):
    side: str
    text: str
    line_no: int
    row: int = -1
    category: str
    note: str = ""


class DetailsBody(BaseModel):
    movie: str | None = None
    writer: str | None = None
    episode: str | None = None


def create_app(sessions_dir: Path | None = None) -> FastAPI:
    store = SessionStore(sessions_dir or default_home() / "sessions")
    open_sessions: dict[str, ReviewSession] = {}
    lock = threading.RLock()
    app = FastAPI(title="Transcript QC", docs_url="/docs", redoc_url=None)

    def get(session_id: str) -> ReviewSession:
        with lock:
            if session_id not in open_sessions:
                open_sessions[session_id], _ = store.load(session_id)
            return open_sessions[session_id]

    def result(session: ReviewSession, item=None, created=()) -> dict:
        return {
            "item": item.as_dict() if item else None,
            "created": [c.as_dict() for c in created],
            "counts": session.counts(),
            "progress": session.progress(),
            "details": {
                "movie": session.details.movie, "writer": session.details.writer,
                "episode": session.details.episode,
            },
        }

    @app.exception_handler(ReviewError)
    async def review_error(_: Request, error: ReviewError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "profiles": sorted(PROFILES)}

    @app.get("/api/sessions")
    def sessions() -> list[dict]:
        return store.listing()

    @app.get("/api/details")
    def details_for(file_name: str, rules: str = "default") -> dict:
        """Movie, writer and episode as the exports will read them from A's file name."""
        if rules not in PROFILES:
            raise ReviewError(f"Unknown rules {rules!r}.")
        found = details_from_name(file_name, load_rules(rules).movies)
        return {"movie": found.movie, "writer": found.writer, "episode": found.episode}

    @app.post("/api/sessions")
    async def upload(
        file_a: UploadFile = File(...),
        file_b: UploadFile = File(...),
        movie: str = Form(""),
        writer: str = Form(""),
        episode: str = Form(""),
        rules: str = Form("default"),
    ) -> dict:
        a_bytes, b_bytes = await file_a.read(), await file_b.read()
        if not a_bytes or not b_bytes:
            raise ReviewError("Choose both files, A and B.")
        if len(a_bytes) > MAX_UPLOAD or len(b_bytes) > MAX_UPLOAD:
            raise ReviewError("A file is larger than 50 MB.")
        if rules not in PROFILES:
            raise ReviewError(f"Unknown rules {rules!r}. Use one of {sorted(PROFILES)}.")
        a_name = file_a.filename or "A.docx"
        b_name = file_b.filename or "B.docx"
        details = details_from_name(
            a_name, load_rules(rules).movies, movie or None, writer or None, episode or None
        )
        with lock:
            session, outcome = store.open(a_bytes, b_bytes, a_name, b_name, rules, details)
            if outcome is not None and (movie or writer or episode):
                session.set_details(movie or None, writer or None, episode or None)
            open_sessions[session.id] = session
            store.save(session)
        state = session.state()
        state["restored"] = (
            {"items": outcome[0], "missing": outcome[1]} if outcome and outcome[0] else None
        )
        return state

    @app.get("/api/sessions/{session_id}")
    def state(session_id: str) -> dict:
        return get(session_id).state()

    @app.get("/api/sessions/{session_id}/rows")
    def rows(session_id: str) -> list[dict]:
        return get(session_id).rows_json()

    @app.post("/api/sessions/{session_id}/items/{item_id}")
    def act(session_id: str, item_id: int, body: ActionBody) -> dict:
        with lock:
            session = get(session_id)
            created = session.apply(
                body.action, item_id, body.category, body.note, body.occurrences
            )
            store.save(session)
            item = session.items[item_id] if not session.items[item_id].deleted else None
            return result(session, item, created)

    @app.post("/api/sessions/{session_id}/items")
    def add(session_id: str, body: AddBody) -> dict:
        with lock:
            session = get(session_id)
            item = session.add_mistake(
                body.side, body.text, body.line_no, body.row, body.category, body.note
            )
            store.save(session)
            return result(session, item, [])

    @app.patch("/api/sessions/{session_id}/details")
    def details(session_id: str, body: DetailsBody) -> dict:
        with lock:
            session = get(session_id)
            session.set_details(body.movie, body.writer, body.episode)
            store.save(session)
            return result(session)

    @app.post("/api/sessions/{session_id}/save")
    def save(session_id: str) -> dict:
        with lock:
            path = store.save(get(session_id))
        return {"saved": True, "path": str(path)}

    def refuse_if_pending(session: ReviewSession, force: bool) -> None:
        pending = session.progress()["pending"]
        if pending and not force:
            raise ReviewError(
                f"{pending} mistakes are still pending. Export anyway, or keep reviewing.", 409
            )

    def attachment(path: Path, name: str, media: str) -> FileResponse:
        return FileResponse(path, media_type=media, filename=name)

    @app.get("/api/sessions/{session_id}/export/docx")
    def export_docx(session_id: str, force: bool = False, author: str = DEFAULT_AUTHOR):
        with lock:
            session = get(session_id)
            refuse_if_pending(session, force)
            folder = store.folder(session_id) / "export"
            folder.mkdir(exist_ok=True)
            stem = Path(session.a_name).stem
            out = folder / f"{stem}_QC.docx"
            session.export_docx(out, author=author or DEFAULT_AUTHOR)
        return attachment(
            out, out.name,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @app.get("/api/sessions/{session_id}/export/csv")
    def export_csv(session_id: str, force: bool = False):
        with lock:
            session = get(session_id)
            refuse_if_pending(session, force)
            folder = store.folder(session_id) / "export"
            folder.mkdir(exist_ok=True)
            out = folder / f"{Path(session.a_name).stem}_mistakes.csv"
            session.export_csv(out)
        return attachment(out, out.name, "text/csv")

    @app.get("/api/sessions/{session_id}/log")
    def log(session_id: str) -> list[dict]:
        return get(session_id).log

    if (STATIC / "index.html").is_file():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    else:
        @app.get("/", response_class=HTMLResponse)
        def placeholder() -> str:
            return _NO_BUILD

    return app
