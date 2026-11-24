// Calls to the local server. Every failure becomes an Error with a message fit to show.

async function read(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `Something went wrong (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return data;
}

const send = (url, method, body) =>
  fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(read);

export const api = {
  details: (fileName) => fetch(`api/details?file_name=${encodeURIComponent(fileName)}`).then(read),
  sessions: () => fetch("api/sessions").then(read),
  open(fileA, fileB, details) {
    const form = new FormData();
    form.append("file_a", fileA);
    form.append("file_b", fileB);
    for (const key of ["movie", "writer", "episode"]) form.append(key, details[key] || "");
    return fetch("api/sessions", { method: "POST", body: form }).then(read);
  },
  state: (id) => fetch(`api/sessions/${id}`).then(read),
  rows: (id) => fetch(`api/sessions/${id}/rows`).then(read),
  act: (id, itemId, body) => send(`api/sessions/${id}/items/${itemId}`, "POST", body),
  add: (id, body) => send(`api/sessions/${id}/items`, "POST", body),
  setDetails: (id, body) => send(`api/sessions/${id}/details`, "PATCH", body),
  save: (id) => send(`api/sessions/${id}/save`, "POST", {}),
};

/** Download an export. Returns { pending } when the server wants a go-ahead first. */
export async function download(id, kind, force) {
  const response = await fetch(`api/sessions/${id}/export/${kind}?force=${force ? "true" : "false"}`);
  if (response.status === 409) {
    const data = await response.json();
    const found = /(\d+) mistakes/.exec(data.detail || "");
    return { pending: found ? Number(found[1]) : 1, message: data.detail };
  }
  if (!response.ok) await read(response);
  const blob = await response.blob();
  const header = response.headers.get("content-disposition") || "";
  const star = /filename\*=utf-8''([^;]+)/i.exec(header);
  const plain = /filename="?([^";]+)"?/i.exec(header);
  const name = star ? decodeURIComponent(star[1]) : plain ? plain[1] : `export.${kind}`;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return { name };
}
