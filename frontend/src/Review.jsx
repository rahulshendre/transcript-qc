import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, download } from "./api.js";
import DetailPanel from "./DetailPanel.jsx";
import Help from "./Help.jsx";
import MistakeList from "./MistakeList.jsx";
import Scorecard from "./Scorecard.jsx";
import SideBySide from "./SideBySide.jsx";
import { advanceAfter, keyAction, mergeResult, moveSelection, visibleItems } from "./model.js";

const shortName = (name) => name.replace(/\.docx$/i, "");

export default function Review({ initial, onClose }) {
  const id = initial.id;
  const [items, setItems] = useState(initial.items);
  const [counts, setCounts] = useState(initial.counts);
  const [progress, setProgress] = useState(initial.progress);
  const [details, setDetails] = useState(initial.details);
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ status: "counted", category: null, sort: "line" });
  const [selectedId, setSelectedId] = useState(null);
  const [selection, setSelection] = useState(null);
  const [help, setHelp] = useState(false);
  const [message, setMessage] = useState(
    initial.restored ? `Picked up where you stopped (${initial.restored.items} decisions restored).` : "",
  );
  const [confirmExport, setConfirmExport] = useState(null);
  const [savedAt, setSavedAt] = useState(null);
  const noteRef = useRef(null);
  const timer = useRef(null);

  const list = useMemo(() => visibleItems(items, filter), [items, filter]);
  const selected = items.find((item) => item.id === selectedId) || null;
  const live = useRef({});
  live.current = { list, selected, selection, help, confirmExport };

  useEffect(() => {
    api.rows(id).then(setRows).catch((e) => flash(e.message));
  }, [id]);

  useEffect(() => {
    if (selectedId === null && list.length) {
      setSelectedId((list.find((item) => item.status === "pending") || list[0]).id);
    }
  }, [list, selectedId]);

  const flash = (text) => {
    setMessage(text);
    clearTimeout(timer.current);
    if (text) timer.current = setTimeout(() => setMessage(""), 6000);
  };

  const commit = (result, nextId) => {
    setItems((previous) => mergeResult(previous, result));
    setCounts(result.counts);
    setProgress(result.progress);
    if (result.details) setDetails(result.details);
    if (nextId !== undefined && nextId !== null) setSelectedId(nextId);
    setSavedAt(new Date());
  };

  const decide = async (action, extra = {}, advance = true) => {
    const { selected: current, list: shown } = live.current;
    if (!current) return;
    const nextId = advance ? advanceAfter(shown, current.id) : current.id;
    try {
      const result = await api.act(id, current.id, { action, ...extra });
      if (action === "delete") result.removedId = current.id;
      commit(result, nextId);
    } catch (error) {
      flash(error.message);
    }
  };

  const addMistake = async (category) => {
    const { selection: chosen } = live.current;
    if (!chosen) return;
    try {
      const result = await api.add(id, {
        side: chosen.side, text: chosen.text, line_no: chosen.line_no, row: chosen.row, category,
      });
      window.getSelection()?.removeAllRanges();
      setSelection(null);
      setFilter((f) => ({ ...f, status: "counted", category: null }));
      commit(result, result.item.id);
    } catch (error) {
      flash(error.message);
    }
  };

  const save = async () => {
    try {
      await api.save(id);
      setSavedAt(new Date());
      flash("Saved.");
    } catch (error) {
      flash(error.message);
    }
  };

  const exportFile = async (kind, force = false) => {
    try {
      const outcome = await download(id, kind, force);
      if (outcome.pending) {
        setConfirmExport({ kind, pending: outcome.pending });
      } else {
        setConfirmExport(null);
        flash(`Exported ${outcome.name}.`);
      }
    } catch (error) {
      flash(error.message);
    }
  };

  const run = (action) => {
    const { list: shown, selected: current } = live.current;
    switch (action.type) {
      case "move":
        setSelectedId(moveSelection(shown, current ? current.id : null, action.delta));
        break;
      case "confirm":
        decide("confirm");
        break;
      case "category":
        decide("category", { category: action.category });
        break;
      case "reject":
        decide("reject");
        break;
      case "reset":
        decide("reset", {}, false);
        break;
      case "promote":
        decide("promote", {}, false);
        break;
      case "delete":
        if (current && (current.source === "manual" || current.source === "split")) decide("delete");
        break;
      case "note":
        noteRef.current?.focus();
        break;
      case "add":
        addMistake(action.category);
        break;
      case "save":
        save();
        break;
      case "help":
        setHelp((open) => !open);
        break;
      case "escape":
        if (live.current.help) setHelp(false);
        else if (live.current.confirmExport) setConfirmExport(null);
        else {
          window.getSelection()?.removeAllRanges();
          setSelection(null);
          document.activeElement?.blur?.();
        }
        break;
      default:
    }
  };

  const handlers = useRef(run);
  handlers.current = run;
  useEffect(() => {
    const onKey = (event) => {
      const target = event.target;
      const typing =
        ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) ||
        target.isContentEditable === true;
      const { selected: current, selection: chosen, help: helpOpen } = live.current;
      const action = keyAction(event, {
        typing,
        hasSelection: Boolean(chosen),
        hasItem: Boolean(current),
        itemStatus: current ? current.status : null,
        helpOpen,
      });
      if (!action) return;
      event.preventDefault();
      handlers.current(action);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const changeDetails = async (key, value) => {
    const next = { ...details, [key]: value };
    setDetails(next);
    try {
      await api.setDetails(id, { [key]: value });
    } catch (error) {
      flash(error.message);
    }
  };

  const pick = (category) =>
    setFilter((f) => ({ ...f, status: "counted", category: category === f.category ? null : category }));

  return (
    <div className="app">
      <header className="top">
        <strong className="brand">Transcript QC</strong>
        <span className="files" title={`${initial.a_name} with ${initial.b_name}`}>
          {shortName(initial.a_name)} with {shortName(initial.b_name)}
        </span>
        <div className="details">
          {[["movie", "Movie"], ["writer", "Written by"], ["episode", "Episode"]].map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                value={details[key]}
                data-testid={`review-${key}`}
                onChange={(e) => setDetails({ ...details, [key]: e.target.value })}
                onBlur={(e) => changeDetails(key, e.target.value)}
              />
            </label>
          ))}
        </div>
        <button className="link" onClick={() => setHelp(true)} data-testid="open-help">Keys ?</button>
        <button className="link" onClick={onClose}>Close review</button>
      </header>

      <Scorecard
        counts={counts}
        engineCounts={initial.engine_counts}
        progress={progress}
        filter={filter}
        onPick={pick}
        onPending={() => setFilter((f) => ({ ...f, status: "pending", category: null }))}
      />

      <main className="panes">
        <MistakeList
          list={list}
          selectedId={selectedId}
          onSelect={setSelectedId}
          filter={filter}
          onFilter={setFilter}
        />
        <SideBySide
          rows={rows}
          selected={selected}
          aName={shortName(initial.a_name)}
          bName={shortName(initial.b_name)}
          onSelection={setSelection}
        />
        <DetailPanel
          item={selected}
          noteRef={noteRef}
          onAction={decide}
          selection={selection}
          onAdd={addMistake}
        />
      </main>

      <footer className="exports">
        <button onClick={save} data-testid="save">Save session</button>
        <span className="saved" data-testid="saved-at">
          {savedAt ? `Saved ${savedAt.toLocaleTimeString()}` : "Saved automatically after every decision"}
        </span>
        <span className="spacer" />
        <a className="loglink" href={`api/sessions/${id}/log`} target="_blank" rel="noreferrer" data-testid="log-link">
          Decision log
        </a>
        <button onClick={() => exportFile("csv")} data-testid="export-csv">Export CSV</button>
        <span className="note-text">Exports use the reviewed counts</span>
        <button className="primary" onClick={() => exportFile("docx")} data-testid="export-docx">
          Export QC .docx
        </button>
      </footer>

      {message && (
        <div className="toast" role="status" data-testid="toast">
          {message}
        </div>
      )}
      {help && <Help onClose={() => setHelp(false)} />}
      {confirmExport && (
        <div className="overlay" role="alertdialog" data-testid="confirm-export">
          <div className="dialog">
            <h2>Still pending</h2>
            <p>
              {confirmExport.pending} {confirmExport.pending === 1 ? "mistake is" : "mistakes are"} still
              pending. They are exported with the engine's category.
            </p>
            <div className="buttons">
              <button onClick={() => setConfirmExport(null)} data-testid="keep-reviewing">
                Keep reviewing
              </button>
              <button
                className="primary"
                onClick={() => exportFile(confirmExport.kind, true)}
                data-testid="export-anyway"
              >
                Export anyway
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
