import { useEffect, useState, type FormEvent } from "react";
import { CUSTOMER_ID_PATTERN, shortId, when } from "../session/session";

type Props = {
  customerId: string;
  sessionId: string | null;
  startedAt: string | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  onCustomerChange: (id: string) => void;
  onEnd: () => void;
  onRetry: () => void;
};

export function SessionBar({ customerId, sessionId, startedAt, loading, error, busy, onCustomerChange, onEnd, onRetry }: Props) {
  const [draft, setDraft] = useState(customerId);
  const valid = CUSTOMER_ID_PATTERN.test(draft.trim());

  useEffect(() => setDraft(customerId), [customerId]);

  function apply(e?: FormEvent) {
    e?.preventDefault();
    const id = draft.trim();
    if (valid && id !== customerId) onCustomerChange(id);
  }

  return (
    <section className="session-bar" aria-label="Session">
      <form className="customer-field" onSubmit={apply}>
        <label htmlFor="customer-id">Customer ID</label>
        <input
          id="customer-id"
          value={draft}
          maxLength={64}
          autoComplete="off"
          aria-invalid={!valid}
          aria-describedby={valid ? undefined : "customer-id-error"}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => apply()}
        />
      </form>

      <div className="session-info" role="status">
        {loading ? (
          "Loading session…"
        ) : error ? (
          <span className="inline-error">
            {error}{" "}
            <button type="button" className="link-btn" onClick={onRetry}>
              Retry
            </button>
          </span>
        ) : sessionId ? (
          <>
            Session <code title={sessionId}>{shortId(sessionId)}</code>
            {startedAt && <span className="session-sub"> · started {when(startedAt)}</span>}
          </>
        ) : (
          "No session"
        )}
      </div>

      <button type="button" className="secondary end-btn" disabled={busy || loading || !sessionId} onClick={onEnd}>
        End session
      </button>

      {!valid && (
        <p id="customer-id-error" className="inline-error field-error">
          Use 1–64 letters, numbers, - or _ (no names or emails).
        </p>
      )}
    </section>
  );
}
