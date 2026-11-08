import { useEffect, useState } from "react";
import { api } from "../api/client";
import { customerProfile } from "../session/customers";
import type { SessionSummary } from "../api/types";
import { when } from "../session/session";
import { TICKET_STATE_LABEL } from "./labels";

type Props = {
  customerId: string;
  currentSessionId: string | null;
  onResume: (sessionId: string) => Promise<void>;
};

export function Sessions({ customerId, currentSessionId, onResume }: Props) {
  const [items, setItems] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resuming, setResuming] = useState<string | null>(null);

  function load() {
    setError(null);
    setItems(null);
    api.sessions(customerId).then(setItems).catch((e: Error) => setError(e.message));
  }

  useEffect(load, [customerId]);

  // The active ticket lives on the Ask tab; History lists every other one (on hold, escalated,
  // resolved or closed), each of which can be reopened.
  const past = items?.filter((s) => s.session_id !== currentSessionId) ?? null;

  async function resume(id: string) {
    setResuming(id);
    setError(null);
    try {
      await onResume(id);
    } catch (e) {
      setError((e as Error).message);
      setResuming(null);
    }
  }

  return (
    <section className="sessions" aria-labelledby="sessions-title">
      <h2 id="sessions-title">
        Ticket history <span className="session-sub">· {customerProfile(customerId)?.name ?? "customer"} (ID {customerId})</span>
      </h2>
      {error && (
        <div className="empty" role="alert">
          <p>Couldn't load past tickets: {error}</p>
          <button type="button" className="secondary" onClick={load}>
            Try again
          </button>
        </div>
      )}
      {!error && items === null && (
        <p className="empty" role="status">
          Loading past tickets…
        </p>
      )}
      {past && past.length === 0 && (
        <p className="empty">No other tickets yet. Closing the open ticket or starting a new one moves it here.</p>
      )}
      {past && past.length > 0 && (
        <ul className="history">
          {past.map((s) => {
            const titleId = `session-${s.session_id}`;
            return (
              <li key={s.session_id} className="session-row">
                <div>
                  <span id={titleId} className="history-q">
                    {s.first_question ?? "No questions asked"}
                  </span>
                  <span className="history-sub">
                    <span className="ticket">#{s.ticket_no}</span>
                    <span className={`badge ticket-${s.state}`}>{TICKET_STATE_LABEL[s.state]}</span>
                    {s.question_count} {s.question_count === 1 ? "question" : "questions"} · {when(s.last_active_at)}
                  </span>
                </div>
                <button
                  type="button"
                  className="secondary"
                  aria-describedby={titleId}
                  disabled={resuming !== null}
                  onClick={() => resume(s.session_id)}
                >
                  {resuming === s.session_id ? "Reopening…" : "Reopen"}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
