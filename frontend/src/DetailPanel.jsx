import React, { useEffect, useState } from "react";
import { CATEGORIES, lineOf, statusLabel } from "./model.js";

export default function DetailPanel({ item, noteRef, onAction, selection, onAdd }) {
  const [picked, setPicked] = useState([]);
  const [note, setNote] = useState("");
  useEffect(() => {
    setPicked([]);
    setNote(item ? item.reviewer_note : "");
  }, [item && item.id, item && item.reviewer_note]);

  if (!item) {
    return (
      <aside className="detail-pane" data-testid="detail">
        <p className="empty">Choose a mistake from the list to see it here.</p>
        {selection && <AddBox selection={selection} onAdd={onAdd} />}
      </aside>
    );
  }
  const ignored = item.status === "ignored";
  const saveNote = () => {
    if (note.trim() !== (item.reviewer_note || "")) onAction("note", { note }, false);
  };
  return (
    <aside className="detail-pane" data-testid="detail" data-item={item.id}>
      <h2>
        Mistake #{item.id}
        <span className={`badge st-${item.status}`} data-testid="detail-status">{statusLabel(item.status)}</span>
      </h2>
      <dl>
        <dt>File A</dt>
        <dd lang="hi" className="a-text" data-testid="detail-a">{item.a_text || "-"}</dd>
        <dt>File B</dt>
        <dd lang="hi" className="b-text" data-testid="detail-b">{item.b_text || "-"}</dd>
        <dt>Category</dt>
        <dd>
          <span className={`pill cat-${item.category}`} data-testid="detail-category">{item.category}</span>
          {item.engine_category && item.engine_category !== item.category && (
            <span className="was-note"> engine said {item.engine_category}</span>
          )}
        </dd>
        <dt>Rule</dt>
        <dd>
          <code>{item.rule_id}</code>
          <span className="reason">{item.engine_note}</span>
          {item.confidence < 0.8 && <span className="unsure"> Not very sure ({Math.round(item.confidence * 100)}%).</span>}
        </dd>
        <dt>Line</dt>
        <dd>
          {lineOf(item)} in {item.line_no ? "file A" : "file B"}
        </dd>
        {ignored && (
          <>
            <dt>Not counted</dt>
            <dd>{item.ignored_because}</dd>
          </>
        )}
      </dl>

      {ignored ? (
        <div className="buttons">
          <button className="primary" onClick={() => onAction("promote", {}, false)} data-testid="promote">
            Count it (P)
          </button>
        </div>
      ) : (
        <>
          <div className="buttons">
            <button className="primary" onClick={() => onAction("confirm")} data-testid="confirm">
              Confirm <kbd>Enter</kbd>
            </button>
            <button onClick={() => onAction("reject")} data-testid="reject">
              Not a mistake <kbd>X</kbd>
            </button>
            <button onClick={() => onAction("reset", {}, false)} data-testid="reset">
              Undo <kbd>U</kbd>
            </button>
          </div>
          <div className="categories" role="group" aria-label="Change category">
            {CATEGORIES.map((c, i) => (
              <button
                key={c}
                className={`cat-btn cat-${c} ${item.category === c ? "on" : ""}`}
                data-testid={`set-${c}`}
                onClick={() => onAction("category", { category: c })}
              >
                <kbd>{i + 1}</kbd> {c}
              </button>
            ))}
          </div>
        </>
      )}

      {item.occurrences.length > 1 && (
        <section className="occurrences" data-testid="occurrences">
          <h3>Seen {item.occurrences.length} times</h3>
          <ul>
            {item.occurrences.map((o, i) => (
              <li key={i}>
                <label>
                  <input
                    type="checkbox"
                    checked={picked.includes(i)}
                    data-testid={`occ-${i}`}
                    onChange={() =>
                      setPicked(picked.includes(i) ? picked.filter((x) => x !== i) : [...picked, i])
                    }
                  />
                  line {o.line_no}
                  <span lang="hi">
                    {" "}
                    {o.a_text || "-"} {"→"} {o.b_text || "-"}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <button
            disabled={picked.length === 0 || picked.length >= item.occurrences.length}
            onClick={() => onAction("split", { occurrences: picked }, false)}
            data-testid="split"
          >
            Split off {picked.length || ""} as separate mistakes
          </button>
        </section>
      )}

      <label className="note">
        Note <kbd>N</kbd>
        <textarea
          ref={noteRef}
          rows="2"
          value={note}
          data-testid="note"
          placeholder="Why? Goes into the CSV."
          onChange={(e) => setNote(e.target.value)}
          onBlur={saveNote}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) e.currentTarget.blur();
          }}
        />
      </label>
      {item.source === "manual" || item.source === "split" ? (
        <button className="link danger" onClick={() => onAction("delete", {}, false)}>
          Delete this mistake
        </button>
      ) : null}
      {selection && <AddBox selection={selection} onAdd={onAdd} />}
    </aside>
  );
}

export function AddBox({ selection, onAdd }) {
  return (
    <section className="add-box" data-testid="add-box">
      <h3>Add a mistake</h3>
      <p>
        <q lang="hi">{selection.text.length > 60 ? `${selection.text.slice(0, 60)}...` : selection.text}</q>{" "}
        (file {selection.side.toUpperCase()}, line {selection.line_no}). Press a number, or:
      </p>
      <div className="categories">
        {CATEGORIES.map((c, i) => (
          <button key={c} className={`cat-btn cat-${c}`} data-testid={`add-${c}`} onClick={() => onAdd(c)}>
            <kbd>{i + 1}</kbd> {c}
          </button>
        ))}
      </div>
    </section>
  );
}
