import React from "react";
import { CATEGORIES } from "./model.js";

export default function Scorecard({ counts, engineCounts, progress, filter, onPick, onPending }) {
  const engineTotal = Object.values(engineCounts).reduce((a, b) => a + b, 0);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const percent = progress.total ? Math.round((progress.reviewed / progress.total) * 100) : 0;
  const anyChanged = Object.keys(counts).some((name) => counts[name] !== engineCounts[name]);
  const card = (name, reviewed, engine, active, onClick) => {
    const changed = reviewed !== engine;
    return (
      <button
        key={name}
        className={`card cat-${name} ${active ? "active" : ""} ${changed ? "changed" : ""}`}
        data-testid={`card-${name}`}
        data-engine={engine}
        data-reviewed={reviewed}
        onClick={onClick}
        title={changed ? `The engine counted ${engine}. After your review: ${reviewed}.` : ""}
      >
        <span className="card-name">{name === "CC" ? "CC" : name}</span>
        <span className="card-number">
          {changed && <span className="was">{engine}</span>}
          {changed && <span className="arrow" aria-hidden="true">{"→"}</span>}
          <strong>{reviewed}</strong>
        </span>
      </button>
    );
  };
  return (
    <section className="scorecard" aria-label="Counts">
      <div className="cards">
        {CATEGORIES.map((name) =>
          card(name, counts[name], engineCounts[name], filter.category === name, () => onPick(name)),
        )}
        {card("Total", total, engineTotal, false, () => onPick(null))}
      </div>
      <div className="progress-text">
        <button className="link" onClick={onPending} data-testid="progress">
          Reviewed {progress.reviewed} of {progress.total}
        </button>
        <span className="hint">
          {" "}{"·"} click any count to filter the list
          {anyChanged ? ". A crossed-out number is what the tool counted." : ""}
        </span>
      </div>
      <div className="bar" role="progressbar" aria-valuenow={percent} aria-valuemin="0" aria-valuemax="100">
        <div className="bar-fill" style={{ width: `${percent}%` }} />
      </div>
    </section>
  );
}
