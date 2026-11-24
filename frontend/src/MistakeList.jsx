import React, { useEffect, useRef } from "react";
import { SORTS, STATUS_FILTERS, lineOf, pairText, statusLabel } from "./model.js";

export default function MistakeList({ list, selectedId, onSelect, filter, onFilter }) {
  const selectedRef = useRef(null);
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);
  return (
    <section className="list-pane" aria-label="Mistakes">
      <h2 className="pane-title">Mistakes</h2>
      <div className="list-head">
        <div className="filters" role="tablist">
          <span className="filter-label">Filter:</span>
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter.status === f.id}
              className={`filter ${filter.status === f.id ? "on" : ""}`}
              data-testid={`filter-${f.id}`}
              onClick={() => onFilter({ ...filter, status: f.id })}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="list-tools">
          <span data-testid="list-count">
            {list.length} {list.length === 1 ? "item" : "items"}
            {filter.category ? ` in ${filter.category}` : ""}
          </span>
          {filter.category && (
            <button className="link" onClick={() => onFilter({ ...filter, category: null })}>
              clear
            </button>
          )}
          <label className="sort">
            Sort
            <select
              value={filter.sort}
              data-testid="sort"
              onChange={(e) => onFilter({ ...filter, sort: e.target.value })}
            >
              {SORTS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <ul className="items">
        {list.map((item) => (
          <li key={item.id}>
            <button
              ref={item.id === selectedId ? selectedRef : null}
              className={`item cat-${item.category} ${item.id === selectedId ? "sel" : ""}`}
              data-testid={`item-${item.id}`}
              data-status={item.status}
              data-category={item.category}
              onClick={() => onSelect(item.id)}
            >
              <span className="item-top">
                <span className="item-title">
                  #{item.id} {"·"} {item.category}
                </span>
                <span className={`badge st-${item.status}`}>{statusLabel(item.status)}</span>
              </span>
              <span className="item-text" lang="hi" title={`line ${lineOf(item)}`}>{pairText(item)}</span>
            </button>
          </li>
        ))}
        {list.length === 0 && <li className="empty">Nothing here.</li>}
      </ul>
    </section>
  );
}
