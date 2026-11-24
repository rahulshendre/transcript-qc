import React from "react";

const KEYS = [
  ["J / K, arrows", "next / previous mistake"],
  ["Enter", "confirm: the engine was right"],
  ["1 to 6", "change category: Major, Language, Punctuation, CC, Repeated, Minor"],
  ["X", "not a mistake (stays under Rejected)"],
  ["N", "add a note (Ctrl+Enter to finish)"],
  ["U", "undo the decision, back to pending"],
  ["P", "count an ignored difference"],
  ["Select text, then 1 to 6", "add a mistake the engine missed"],
  ["Ctrl+S", "save now (it also saves after every decision)"],
  ["?", "this help"],
];

export default function Help({ onClose }) {
  return (
    <div className="overlay" onClick={onClose} role="dialog" aria-label="Keyboard help" data-testid="help">
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Keyboard</h2>
        <table>
          <tbody>
            {KEYS.map(([key, what]) => (
              <tr key={key}>
                <th><kbd>{key}</kbd></th>
                <td>{what}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="primary" onClick={onClose}>Close <kbd>Esc</kbd></button>
      </div>
    </div>
  );
}
