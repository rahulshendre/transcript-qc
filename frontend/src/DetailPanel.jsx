import React, { useEffect, useState } from "react";
import { CATEGORIES, lineOf, statusLabel } from "./model.js";

export default function DetailPanel({ item, noteRef, onAction, selection, onAdd }) {
  const [picked, setPicked] = useState([]);
  const [note, setNote] = useState("");
  const [choosing, setChoosing] = useState(false);
  useEffect(() => {
    setPicked([]);
    setChoosing(false);
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
  const reason = item.engine_note || (item.source === "manual" ? "Added by you." : "");
  return (
    <aside className="detail-pane" data-testid="detail" data-item={item.id}>
      <h2 className="pane-title">
        Mistake #{item.id}
        <span className={`badge st-${item.status}`} data-testid="detail-status">{statusLabel(item.status)}</span>
      </h2>
      <p className="d-line">
        File A: <span lang="hi" className="a-text" data-testid="detail-a">{item.a_text || "-"}</span>
      </p>
      <p className="d-line">
        File B: <span lang="hi" className="b-text" data-testid="detail-b">{item.b_text || "-"}</span>
      </p>
      <p className="d-line">
        <strong>Category: <span data-testid="detail-category">{item.category}</span></strong>
        {item.engine_category && item.engine_category !== item.category && (
          <span className="was-note"> (tool said {item.engine_category})</span>
        )}
      </p>
      <p className="rule">
        {reason && `Rule: ${reason}`}
        {item.confidence < 0.8 && <span className="unsure"> Not very sure ({Math.round(item.confidence * 100)}%).</span>}
      </p>
      <p className="where">Line {lineOf(item)} in {item.line_no ? "file A" : "file B"}</p>
      {ignored && <p className="rule">Not counted: {item.ignored_because}</p>}

      {ignored ? (
        <div className="stack">
          <button className="strong" onClick={() => onAction("promote", {}, false)} data-testid="promote">
            Count it (P)
          </button>
        </div>
      ) : (
        <div className="stack">
          <button className="strong" onClick={() => onAction("confirm")} data-testid="confirm">
            Confirm (Enter)
          </button>
          <button onClick={() => setChoosing((on) => !on)} data-testid="change-category" aria-expanded={choosing}>
            Change category (1-6)
          </button>
          {choosing && (
            <div className="categories" role="group" aria-label="Change category">
              {CATEGORIES.map((c, i) => (
                <button
                  key={c}
                  className={`cat-btn ${item.category === c ? "on" : ""}`}
                  data-testid={`set-${c}`}
                  onClick={() => onAction("category", { category: c })}
                >
                  {i + 1} {c}
                </button>
              ))}
            </div>
          )}
          <button onClick={() => onAction("reject")} data-testid="reject">
            Not a mistake (X)
          </button>
          <textarea
            ref={noteRef}
            rows="1"
            value={note}
            data-testid="note"
            placeholder="Add a note (N)"
            onChange={(e) => setNote(e.target.value)}
            onBlur={saveNote}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) e.currentTarget.blur();
            }}
          />
          {item.status !== "pending" && (
            <button className="link" onClick={() => onAction("reset", {}, false)} data-testid="reset">
              Undo (U)
            </button>
          )}
        </div>
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
