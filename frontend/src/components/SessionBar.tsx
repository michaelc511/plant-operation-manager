import type { TicketState } from "../api/types";
import { customerProfile, initials } from "../session/customers";
import { when } from "../session/session";
import { TICKET_STATE_LABEL } from "./labels";

type Props = {
  customerId: string;
  sessionId: string | null;
  ticketNo: number | null;
  ticketState: TicketState | null;
  startedAt: string | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  onEnd: () => void;
  onNew: () => void;
  onRetry: () => void;
};

export function SessionBar({ customerId, sessionId, ticketNo, ticketState, startedAt, loading, error, busy, onEnd, onNew, onRetry }: Props) {
  const profile = customerProfile(customerId);

  return (
    <section className="session-bar" aria-label="Session">
      <div className="customer-card" aria-label="Customer">
        <span className="avatar" aria-hidden="true">
          {profile ? initials(profile.name) : "?"}
        </span>
        <div className="customer-text">
          <span className="customer-name">{profile ? profile.name : "Guest customer"}</span>
          <span className="customer-meta">
            {profile ? profile.role : "No profile on file"}
          </span>
        </div>
      </div>

      <div className="customer-field">
        <label htmlFor="customer-id">Customer ID</label>
        <input id="customer-id" value={customerId} readOnly aria-readonly="true" title="Signed-in customer (read-only)" />
      </div>

      <div className="session-info" role="status">
        {loading ? (
          "Loading ticket…"
        ) : error ? (
          <span className="inline-error">
            {error}{" "}
            <button type="button" className="link-btn" onClick={onRetry}>
              Retry
            </button>
          </span>
        ) : sessionId && ticketNo ? (
          <>
            <span className="ticket">Ticket #{ticketNo}</span>{" "}
            <span className={`badge ticket-${ticketState ?? "open"}`}>{TICKET_STATE_LABEL[ticketState ?? "open"]}</span>
            {startedAt && <span className="session-sub"> · opened {when(startedAt)}</span>}
          </>
        ) : (
          <span className="session-sub">No open ticket. Ask a question or start a new one.</span>
        )}
      </div>

      <div className="ticket-actions">
        {sessionId && (
          <button type="button" className="secondary end-btn" disabled={busy || loading} onClick={onEnd}>
            Close ticket
          </button>
        )}
        <button type="button" className="secondary end-btn" disabled={busy || loading} onClick={onNew}>
          New ticket
        </button>
      </div>

    </section>
  );
}
