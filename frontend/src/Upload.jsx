import React, { useEffect, useState } from "react";
import { api } from "./api.js";

function Drop({ label, file, onFile, testId }) {
  const [over, setOver] = useState(false);
  return (
    <label
      className={`drop ${over ? "over" : ""} ${file ? "has" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
      }}
    >
      <span className="drop-label">{label}</span>
      <span className="drop-file">{file ? file.name : "Drop a .docx here, or click to choose"}</span>
      <input
        type="file"
        accept=".docx"
        data-testid={testId}
        onChange={(e) => e.target.files[0] && onFile(e.target.files[0])}
      />
    </label>
  );
}

export default function Upload({ onOpen }) {
  const [a, setA] = useState(null);
  const [b, setB] = useState(null);
  const [details, setDetails] = useState({ movie: "", writer: "", episode: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState([]);

  useEffect(() => {
    api.sessions().then(setSaved).catch(() => {});
  }, []);

  const chooseA = async (file) => {
    setA(file);
    setError("");
    try {
      setDetails(await api.details(file.name));
    } catch {
      /* the fields stay editable */
    }
  };

  const compare = async () => {
    setBusy(true);
    setError("");
    try {
      onOpen(await api.open(a, b, details));
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  const resume = async (id) => {
    setBusy(true);
    try {
      onOpen(await api.state(id));
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  const field = (key, label) => (
    <label className="field">
      <span>{label}</span>
      <input
        value={details[key]}
        data-testid={`detail-${key}`}
        onChange={(e) => setDetails({ ...details, [key]: e.target.value })}
      />
    </label>
  );

  return (
    <main className="upload">
      <h1>Transcript QC</h1>
      <p className="lead">
        Compare a transcript with its reference, check every counted mistake, then export the QC
        document. Everything stays on this computer.
      </p>
      <div className="drops">
        <Drop label="File A: the transcript being scored" file={a} onFile={chooseA} testId="file-a" />
        <Drop label="File B: the reference" file={b} onFile={setB} testId="file-b" />
      </div>
      <div className="fields">
        {field("movie", "Movie name")}
        {field("writer", "Written by")}
        {field("episode", "Episode")}
      </div>
      {error && <p className="error" role="alert" data-testid="upload-error">{error}</p>}
      <button className="primary" disabled={!a || !b || busy} onClick={compare} data-testid="compare">
        {busy ? "Comparing... this takes a few seconds" : "Compare"}
      </button>
      {saved.length > 0 && (
        <section className="saved">
          <h2>Pick up where you stopped</h2>
          <ul>
            {saved.map((s) => (
              <li key={s.id}>
                <button className="link" disabled={busy} onClick={() => resume(s.id)}>
                  {s.a_name} with {s.b_name}
                </button>
                <span>
                  {s.reviewed} of {s.total} reviewed
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
