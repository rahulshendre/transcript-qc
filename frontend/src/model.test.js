import { describe, expect, it } from "vitest";
import {
  CATEGORIES,
  advanceAfter,
  countsFromItems,
  keyAction,
  mergeResult,
  moveSelection,
  pairText,
  sortItems,
  visibleItems,
} from "./model.js";

const make = (id, over = {}) => ({
  id,
  line_no: id * 10,
  b_line: 0,
  category: "Language",
  status: "pending",
  counts: true,
  confidence: 0.9,
  a_text: "क",
  b_text: "ख",
  ...over,
});

const ITEMS = [
  make(0, { category: "Major", line_no: 50, confidence: 0.6 }),
  make(1, { category: "Language", line_no: 10, confidence: 0.95 }),
  make(2, { category: "Language", line_no: 30, status: "confirmed", confidence: 0.55 }),
  make(3, { category: "Punctuation", line_no: 20, status: "rejected", counts: false }),
  make(4, { category: "CC", line_no: 40, status: "ignored", counts: false }),
];

describe("lists", () => {
  it("shows only counted mistakes by default, in line order", () => {
    expect(visibleItems(ITEMS).map((i) => i.id)).toEqual([1, 2, 0]);
  });
  it("filters by status", () => {
    expect(visibleItems(ITEMS, { status: "pending" }).map((i) => i.id)).toEqual([1, 0]);
    expect(visibleItems(ITEMS, { status: "done" }).map((i) => i.id)).toEqual([2]);
    expect(visibleItems(ITEMS, { status: "rejected" }).map((i) => i.id)).toEqual([3]);
    expect(visibleItems(ITEMS, { status: "ignored" }).map((i) => i.id)).toEqual([4]);
  });
  it("a category filter lists exactly the mistakes behind that count", () => {
    const counts = countsFromItems(ITEMS);
    for (const c of CATEGORIES) {
      expect(visibleItems(ITEMS, { status: "counted", category: c }).length).toBe(counts[c]);
    }
  });
  it("sorts by category, and by confidence with the least sure first", () => {
    expect(visibleItems(ITEMS, { sort: "uncertain" }).map((i) => i.id)).toEqual([2, 0, 1]);
    expect(visibleItems(ITEMS, { sort: "category" }).map((i) => i.category)).toEqual([
      "Major",
      "Language",
      "Language",
    ]);
  });
  it("does not change the list it is given", () => {
    const before = ITEMS.map((i) => i.id);
    sortItems(ITEMS, "uncertain");
    expect(ITEMS.map((i) => i.id)).toEqual(before);
  });
});

describe("counts", () => {
  it("counts items that count, by their category now", () => {
    expect(countsFromItems(ITEMS)).toEqual({
      Major: 1, Language: 2, Punctuation: 0, CC: 0, Repeated: 0, Minor: 0,
    });
  });
  it("moves at once when a category changes or an item is rejected", () => {
    const changed = ITEMS.map((i) => (i.id === 1 ? { ...i, category: "Major" } : i));
    expect(countsFromItems(changed).Major).toBe(2);
    const rejected = changed.map((i) => (i.id === 0 ? { ...i, status: "rejected", counts: false } : i));
    expect(countsFromItems(rejected).Major).toBe(1);
  });
});

describe("moving around", () => {
  const list = visibleItems(ITEMS);
  it("steps through the list and stops at the ends", () => {
    expect(moveSelection(list, 1, 1)).toBe(2);
    expect(moveSelection(list, 0, 1)).toBe(0);
    expect(moveSelection(list, 1, -1)).toBe(1);
    expect(moveSelection([], 1, 1)).toBeNull();
  });
  it("starts from the first or last item when nothing is selected", () => {
    expect(moveSelection(list, null, 1)).toBe(1);
    expect(moveSelection(list, null, -1)).toBe(0);
  });
  it("after a decision goes to the next pending item, wrapping round", () => {
    expect(advanceAfter(list, 1)).toBe(0);   // 2 is already confirmed, so skip it
    expect(advanceAfter(list, 0)).toBe(1);   // wraps to the first pending
  });
  it("stays on the last item when nothing is pending", () => {
    const done = list.map((i) => ({ ...i, status: "confirmed" }));
    expect(advanceAfter(done, 0)).toBe(0);
    expect(advanceAfter(done, 1)).toBe(2);
  });
});

describe("answers from the server", () => {
  it("replaces the changed item and adds new ones once", () => {
    const answer = { item: { ...ITEMS[1], status: "confirmed" }, created: [make(9)] };
    const next = mergeResult(ITEMS, answer);
    expect(next.find((i) => i.id === 1).status).toBe("confirmed");
    expect(next.some((i) => i.id === 9)).toBe(true);
    expect(mergeResult(next, answer).filter((i) => i.id === 9).length).toBe(1);
  });
  it("adds a brand-new item, such as a mistake the reviewer added", () => {
    const added = make(7, { status: "added", source: "manual" });
    const next = mergeResult(ITEMS, { item: added, created: [] });
    expect(next.find((i) => i.id === 7)).toEqual(added);
    expect(mergeResult(next, { item: added, created: [] }).filter((i) => i.id === 7).length).toBe(1);
  });
  it("removes an item the server deleted", () => {
    expect(mergeResult(ITEMS, { item: null, removedId: 2 }).some((i) => i.id === 2)).toBe(false);
  });
  it("shows a dash for a side with nothing", () => {
    expect(pairText(make(0, { a_text: "", b_text: "हैं" }))).toBe("-  →  हैं");
  });
});

describe("keys", () => {
  const ctx = { typing: false, hasSelection: false, hasItem: true, itemStatus: "pending" };
  const press = (key, extra = {}, over = {}) =>
    keyAction({ key, ctrlKey: false, metaKey: false, altKey: false, ...extra }, { ...ctx, ...over });
  it("moves with j and k and the arrow keys", () => {
    expect(press("j")).toEqual({ type: "move", delta: 1 });
    expect(press("K")).toEqual({ type: "move", delta: -1 });
    expect(press("ArrowDown")).toEqual({ type: "move", delta: 1 });
  });
  it("decides with Enter, x, u and notes with n", () => {
    expect(press("Enter")).toEqual({ type: "confirm" });
    expect(press("x")).toEqual({ type: "reject" });
    expect(press("u")).toEqual({ type: "reset" });
    expect(press("n")).toEqual({ type: "note" });
  });
  it("picks the category with the keys 1 to 6 in the agreed order", () => {
    expect(CATEGORIES.map((_, i) => press(String(i + 1)).category)).toEqual(CATEGORIES);
    expect(press("7")).toBeNull();
    expect(press("0")).toBeNull();
  });
  it("adds a mistake instead when text is selected", () => {
    expect(press("2", {}, { hasSelection: true })).toEqual({ type: "add", category: "Language" });
  });
  it("counts an ignored difference with Enter or p", () => {
    expect(press("Enter", {}, { itemStatus: "ignored" })).toEqual({ type: "promote" });
    expect(press("p")).toEqual({ type: "promote" });
  });
  it("does nothing while typing, except Escape", () => {
    expect(press("j", {}, { typing: true })).toBeNull();
    expect(press("Enter", {}, { typing: true })).toBeNull();
    expect(press("Escape", {}, { typing: true })).toEqual({ type: "escape" });
  });
  it("does nothing to an item when none is selected", () => {
    expect(press("Enter", {}, { hasItem: false })).toBeNull();
    expect(press("3", {}, { hasItem: false })).toBeNull();
    expect(press("j", {}, { hasItem: false })).toEqual({ type: "move", delta: 1 });
  });
  it("leaves browser shortcuts alone, but Ctrl+S saves", () => {
    expect(press("r", { metaKey: true })).toBeNull();
    expect(press("s", { ctrlKey: true })).toEqual({ type: "save" });
  });
  it("opens help with ?, and then ignores other keys", () => {
    expect(press("?")).toEqual({ type: "help" });
    expect(press("j", {}, { helpOpen: true })).toBeNull();
  });
});
