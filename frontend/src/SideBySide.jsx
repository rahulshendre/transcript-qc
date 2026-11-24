import React, { memo, useEffect, useRef } from "react";

const NONE = [];

const Cell = memo(function Cell({ side, lines, rowIndex, activeDiffs }) {
  return (
    <div className={`cell cell-${side}`}>
      {lines.map((line) => (
        <p key={line.para} className="line" lang="hi" data-side={side} data-para={line.para} data-row={rowIndex}>
          <span className="lineno" aria-hidden="true">{line.para}</span>
          {line.segments.map(([text, diff], i) =>
            diff < 0 ? (
              <span key={i}>{text}</span>
            ) : (
              <mark
                key={i}
                className={`seg ${side}-only ${activeDiffs.includes(diff) ? "active" : ""}`}
                data-diff={diff}
              >
                {text}
              </mark>
            ),
          )}
        </p>
      ))}
    </div>
  );
});

const RowView = memo(function RowView({ row, active, diffs }) {
  return (
    <div className={`row ${active ? "row-active" : ""}`} id={`row-${row.index}`} data-testid={`row-${row.index}`}>
      <Cell side="a" lines={row.a} rowIndex={row.index} activeDiffs={diffs} />
      <Cell side="b" lines={row.b} rowIndex={row.index} activeDiffs={diffs} />
    </div>
  );
});

function readSelection() {
  const selection = window.getSelection();
  const text = selection ? selection.toString().trim() : "";
  if (!text || selection.rangeCount === 0) return null;
  const owner = (node) => {
    const element = node && node.nodeType === 3 ? node.parentElement : node;
    return element && element.closest ? element.closest("[data-side]") : null;
  };
  // A triple click can end at the start of the next block, so go by where the selection starts.
  const range = selection.getRangeAt(0);
  const start = owner(selection.anchorNode) || owner(range.startContainer);
  if (!start) return null;
  const side = start.dataset.side;
  const end = owner(selection.focusNode);
  if (end && end.dataset.side !== side && text.split("\n").length > 1) return null;
  return { side, text, line_no: Number(start.dataset.para), row: Number(start.dataset.row) };
}

export default function SideBySide({ rows, selected, aName, bName, onSelection }) {
  const paneRef = useRef(null);
  const activeRow = selected ? selected.row : -1;
  useEffect(() => {
    if (activeRow < 0 || !paneRef.current) return;
    const element = paneRef.current.querySelector(`#row-${activeRow}`);
    if (element) element.scrollIntoView({ block: "center" });
  }, [activeRow, selected && selected.id, rows.length]);
  return (
    <section className="side-pane" aria-label="Side by side">
      <div className="side-head">
        <span>File A ({aName})</span>
        <span>File B ({bName})</span>
        <span className="legend">
          <mark className="seg a-only">only in A</mark> <mark className="seg b-only">only in B</mark>
        </span>
      </div>
      <div
        className="rows"
        ref={paneRef}
        data-testid="rows"
        onMouseUp={() => onSelection(readSelection())}
        onKeyUp={() => onSelection(readSelection())}
      >
        {rows.map((row) => (
          <RowView
            key={row.index}
            row={row}
            active={row.index === activeRow}
            diffs={row.index === activeRow && selected ? selected.diffs : NONE}
          />
        ))}
      </div>
    </section>
  );
}
