// Pure logic for the review screen: no React, no network. Everything here is unit tested.

export const CATEGORIES = ["Major", "Language", "Punctuation", "CC", "Repeated", "Minor"];

// Keys 1 to 6 pick the category in this order.
export const CATEGORY_KEYS = Object.fromEntries(CATEGORIES.map((c, i) => [String(i + 1), c]));

export const STATUS_FILTERS = [
  { id: "counted", label: "Counted" },
  { id: "pending", label: "Pending" },
  { id: "done", label: "Done" },
  { id: "rejected", label: "Rejected" },
  { id: "ignored", label: "Ignored" },
];

export const SORTS = [
  { id: "line", label: "Line number" },
  { id: "category", label: "Category" },
  { id: "uncertain", label: "Uncertain first" },
];

export const lineOf = (item) => item.line_no || item.b_line || 0;

/** Does an item belong in the list for this status filter? */
export function matchesStatus(item, status) {
  switch (status) {
    case "counted":
      return item.counts;
    case "pending":
      return item.status === "pending";
    case "done":
      return item.counts && item.status !== "pending";
    case "rejected":
      return item.status === "rejected";
    case "ignored":
      return item.status === "ignored";
    default:
      return true;
  }
}

export function sortItems(items, sort) {
  const byLine = (a, b) => lineOf(a) - lineOf(b) || a.id - b.id;
  const copy = [...items];
  if (sort === "category") {
    return copy.sort(
      (a, b) => CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category) || byLine(a, b),
    );
  }
  if (sort === "uncertain") {
    return copy.sort((a, b) => a.confidence - b.confidence || byLine(a, b));
  }
  return copy.sort(byLine);
}

/** The list the reviewer sees: status filter, optional category filter, then the sort. */
export function visibleItems(items, { status = "counted", category = null, sort = "line" } = {}) {
  const shown = items.filter(
    (item) => matchesStatus(item, status) && (!category || item.category === category),
  );
  return sortItems(shown, sort);
}

/** Reviewed counts straight from the items: the same rule the server uses. */
export function countsFromItems(items) {
  const counts = Object.fromEntries(CATEGORIES.map((c) => [c, 0]));
  for (const item of items) if (item.counts) counts[item.category] += 1;
  return counts;
}

/** The id one step from the current one in the list, or the current one at the ends. */
export function moveSelection(list, currentId, delta) {
  if (!list.length) return null;
  const at = list.findIndex((item) => item.id === currentId);
  if (at < 0) return list[delta > 0 ? 0 : list.length - 1].id;
  return list[Math.min(list.length - 1, Math.max(0, at + delta))].id;
}

/** After a decision: the next pending item in the list, else the next item, else stay. */
export function advanceAfter(list, currentId) {
  const at = list.findIndex((item) => item.id === currentId);
  if (at < 0) return currentId;
  for (let i = at + 1; i < list.length; i += 1) {
    if (list[i].status === "pending") return list[i].id;
  }
  for (let i = 0; i < at; i += 1) {
    if (list[i].status === "pending") return list[i].id;
  }
  return list[Math.min(at + 1, list.length - 1)].id;
}

/** Put a server answer into the list: replace the item, add any items it created. */
export function mergeResult(items, result) {
  let next = items;
  if (result.item) {
    const exists = next.some((item) => item.id === result.item.id);
    next = exists
      ? next.map((item) => (item.id === result.item.id ? result.item : item))
      : [...next, result.item];
  } else if (result.removedId !== undefined) {
    next = next.filter((item) => item.id !== result.removedId);
  }
  const known = new Set(next.map((item) => item.id));
  const created = (result.created || []).filter((item) => !known.has(item.id));
  return created.length ? [...next, ...created] : next;
}

/** "कहां -> कहाँ", with a dash where one side has nothing. */
export function pairText(item) {
  return `${item.a_text || "-"}  →  ${item.b_text || "-"}`;
}

export function statusLabel(status) {
  return (
    {
      pending: "pending",
      confirmed: "confirmed",
      changed: "changed",
      rejected: "not a mistake",
      ignored: "ignored",
      promoted: "counted by you",
      added: "added by you",
    }[status] || status
  );
}

/**
 * What a key press means. Returns an action object or null.
 * context: { typing, hasSelection, hasItem, itemStatus, itemSource, helpOpen }
 */
export function keyAction(event, context) {
  if (event.ctrlKey || event.metaKey || event.altKey) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") return { type: "save" };
    return null;
  }
  if (event.key === "Escape") return { type: "escape" };
  if (context.typing) return null;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  if (key === "?") return { type: "help" };
  if (context.helpOpen) return null;
  if (key === "j" || key === "ArrowDown") return { type: "move", delta: 1 };
  if (key === "k" || key === "ArrowUp") return { type: "move", delta: -1 };
  if (CATEGORY_KEYS[key]) {
    return context.hasSelection
      ? { type: "add", category: CATEGORY_KEYS[key] }
      : context.hasItem
        ? { type: "category", category: CATEGORY_KEYS[key] }
        : null;
  }
  if (!context.hasItem) return null;
  if (key === "Enter") return context.itemStatus === "ignored" ? { type: "promote" } : { type: "confirm" };
  if (key === "x") return { type: "reject" };
  if (key === "n") return { type: "note" };
  if (key === "u") return { type: "reset" };
  if (key === "p") return { type: "promote" };
  if (key === "Delete" || key === "Backspace") return { type: "delete" };
  return null;
}
