import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SessionSummary } from "../api/types";
import { shortId, when } from "../session/session";

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
        Sessions <span className="session-sub">· customer {customerId}</span>
      </h2>
      {error && (
        <div className="empty" role="alert">
          <p>Couldn't load sessions: {error}</p>
          <button type="button" className="secondary" onClick={load}>
            Try again
          </button>
        </div>
      )}
      {!error && items === null && (
        <p className="empty" role="status">
          Loading sessions…
        </p>
      )}
      {items && items.length === 0 && <p className="empty">No sessions yet.</p>}
      {items && items.length > 0 && (
        <ul className="history">
          {items.map((s) => {
            const current = s.session_id === currentSessionId;
            const titleId = `session-${s.session_id}`;
            return (
              <li key={s.session_id} className={`session-row${current ? " current" : ""}`}>
                <div>
                  <span id={titleId} className="history-q">
                    {s.first_question ?? "New session (no questions yet)"}
                  </span>
                  <span className="history-sub">
                    <span className={`badge ${s.status === "active" ? "badge-answered" : "badge-closed"}`}>
                      {s.status === "active" ? "Active" : "Ended"}
                    </span>
                    {s.question_count} {s.question_count === 1 ? "question" : "questions"} · {when(s.last_active_at)} ·{" "}
                    <code title={s.session_id}>{shortId(s.session_id)}</code>
                  </span>
                </div>
                {current ? (
                  <span className="current-label">Current</span>
                ) : (
                  <button
                    type="button"
                    className="secondary"
                    aria-describedby={titleId}
                    disabled={resuming !== null}
                    onClick={() => resume(s.session_id)}
                  >
                    {resuming === s.session_id ? "Resuming…" : "Resume"}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
