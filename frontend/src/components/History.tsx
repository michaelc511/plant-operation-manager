import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { QueryRecord } from "../api/types";
import { AnswerCard } from "./AnswerCard";
import { STATUS_LABEL } from "./labels";

function when(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export function History() {
  const [items, setItems] = useState<QueryRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  function load() {
    setError(null);
    setItems(null);
    api.queries(30).then(setItems).catch((e: Error) => setError(e.message));
  }

  useEffect(load, []);

  if (error)
    return (
      <div className="empty" role="alert">
        <p>Couldn't load history: {error}</p>
        <button type="button" className="secondary" onClick={load}>
          Try again
        </button>
      </div>
    );
  if (items === null)
    return (
      <p className="empty" role="status">
        Loading history…
      </p>
    );
  if (items.length === 0) return <p className="empty">No questions yet. Ask one on the Ask tab.</p>;

  return (
    <ul className="history">
      {items.map((q) => (
        <li key={q.id}>
          <button
            type="button"
            className="history-row"
            aria-expanded={open === q.id}
            onClick={() => setOpen(open === q.id ? null : q.id)}
          >
            <span className="history-q">{q.question}</span>
            <span className="history-sub">
              <span className={`badge badge-${q.status}`}>{STATUS_LABEL[q.status]}</span>
              {when(q.created_at)}
              {q.helpful !== null && <span aria-label={q.helpful ? "Marked helpful" : "Marked not helpful"}>{q.helpful ? " 👍" : " 👎"}</span>}
            </span>
          </button>
          {open === q.id && <AnswerCard data={{ ...q, query_id: q.id }} initialHelpful={q.helpful} />}
        </li>
      ))}
    </ul>
  );
}
