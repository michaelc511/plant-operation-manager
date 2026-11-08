import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { Health, Session, TicketState } from "./api/types";
import { AnswerCard } from "./components/AnswerCard";
import { AskBar } from "./components/AskBar";
import { History } from "./components/History";
import { SessionBar } from "./components/SessionBar";
import { Sessions } from "./components/Sessions";
import { Thinking } from "./components/Thinking";
import { SAMPLE_QUESTIONS } from "./components/labels";
import { DEMO_CUSTOMER_ID, type Exchange, exchangesFromSession } from "./session/session";

type SessionInfo = { session_id: string; ticket_no: number; state: TicketState; created_at: string | null };

type Tab = "ask" | "history";

export function App() {
  const [tab, setTab] = useState<Tab>("ask");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const nextKey = useRef(1);

  // ---- session: one active conversation per customer, restored from the backend
  const customerId = DEMO_CUSTOMER_ID; // read-only in the demo: the signed-in customer is fixed
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const loadSeq = useRef(0);

  const applySession = useCallback((s: Session | null) => {
    setSession(s && { session_id: s.session_id, ticket_no: s.ticket_no, state: s.state, created_at: s.created_at });
    setExchanges(s ? exchangesFromSession(s, () => nextKey.current++) : []);
  }, []);

  const runSessionCall = useCallback(
    async (call: () => Promise<Session | null>) => {
      const seq = ++loadSeq.current; // ignore replies to calls that were superseded
      setSessionLoading(true);
      setSessionError(null);
      try {
        const s = await call();
        if (seq === loadSeq.current) applySession(s);
      } catch (e) {
        if (seq === loadSeq.current) setSessionError((e as Error).message);
        throw e;
      } finally {
        if (seq === loadSeq.current) setSessionLoading(false);
      }
    },
    [applySession],
  );

  const loadActive = useCallback(
    // Returning users get their last active ticket back; null if they closed it.
    () => runSessionCall(() => api.activeSession(customerId, false)).catch(() => undefined),
    [runSessionCall, customerId],
  );

  useEffect(() => {
    setSession(null);
    setExchanges([]);
    loadActive();
  }, [customerId, loadActive]);

  async function endSession() {
    if (!session) return;
    const id = session.session_id;
    await runSessionCall(async () => {
      await api.closeSession(id, customerId);
      return null; // nothing is active until a new ticket, a question or a reopen
    }).catch(() => undefined);
  }

  async function newTicket() {
    await runSessionCall(() => api.newSession(customerId)).catch(() => undefined);
  }

  async function resumeSession(id: string) {
    await runSessionCall(() => api.resumeSession(id, customerId));
    setTab("ask");
  }

  useEffect(() => {
    api.visit().catch(() => undefined); // visitor count only; never blocks the app
  }, []);

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((e: Error) => setHealthError(e.message));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [exchanges, busy]);

  async function ask(question: string) {
    const key = nextKey.current++;
    setExchanges((xs) => [...xs, { key, question }]);
    setBusy(true);
    try {
      const answer = await api.ask(question, { sessionId: session?.session_id, customerId });
      if (answer.session_id !== session?.session_id)
        setSession({
          session_id: answer.session_id,
          ticket_no: answer.ticket_no,
          state: "open",
          created_at: new Date().toISOString(),
        });
      setExchanges((xs) => xs.map((x) => (x.key === key ? { ...x, answer } : x)));
    } catch (e) {
      setExchanges((xs) => xs.map((x) => (x.key === key ? { ...x, error: (e as Error).message } : x)));
    } finally {
      setBusy(false);
    }
  }

  // Don't ask while the session is (re)loading: the loaded conversation would replace the new question.
  const askLocked = busy || sessionLoading;

  const notReady =
    healthError ??
    (health && !health.vector_store_ready
      ? "The document index isn't built yet. Ask IT to run the ingest step."
      : health && !health.agent_ready
        ? "The answer agent isn't configured on the server."
        : null);

  return (
    <div className="app">
      <header className="top-bar">
        <div className="brand">
          <span className="logo" aria-hidden="true" />
          <div>
            <h1>Plant Docs Assistant</h1>
            <p>Safety · Maintenance · Quality</p>
          </div>
        </div>
        <span
          className={`health-dot ${health && !notReady ? "ok" : notReady ? "bad" : ""}`}
          role="img"
          aria-label={health && !notReady ? "Connected" : notReady ? "Not connected" : "Checking connection"}
          title={notReady ?? (health ? "Connected" : "Checking…")}
        />
      </header>

      <nav className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "ask"} onClick={() => setTab("ask")}>
          Ask
        </button>
        <button role="tab" aria-selected={tab === "history"} onClick={() => setTab("history")}>
          History
        </button>
      </nav>

      {notReady && (
        <div className="banner" role="alert">
          {notReady}
        </div>
      )}

      {tab === "ask" ? (
        <>
          <SessionBar
            customerId={customerId}
            sessionId={session?.session_id ?? null}
            ticketNo={session?.ticket_no ?? null}
            ticketState={session?.state ?? null}
            startedAt={session?.created_at ?? null}
            loading={sessionLoading}
            error={sessionError}
            busy={busy}
            onEnd={endSession}
            onNew={newTicket}
            onRetry={loadActive}
          />
          <main className="conversation">
            {exchanges.length === 0 && (
              <section className="welcome">
                <h2>Ask the plant documentation</h2>
                <p>
                  Answers come only from the controlled safety procedures, maintenance manual and quality
                  standards, with the section and page for each fact.
                </p>
                <div className="samples">
                  {SAMPLE_QUESTIONS.map((q) => (
                    <button key={q} type="button" className="sample" disabled={askLocked} onClick={() => ask(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              </section>
            )}
            {exchanges.map((x) => (
              <div key={x.key} className="exchange">
                <p className="question-bubble">{x.question}</p>
                {x.answer && <AnswerCard data={x.answer} />}
                {x.error && (
                  <div className="error-card" role="alert">
                    <strong>Couldn't get an answer.</strong> {x.error}
                  </div>
                )}
                {!x.answer && !x.error && <Thinking />}
              </div>
            ))}
            <div ref={endRef} />
          </main>
          <AskBar disabled={askLocked} onAsk={ask} />
        </>
      ) : (
        <main className="conversation">
          <Sessions customerId={customerId} currentSessionId={session?.session_id ?? null} onResume={resumeSession} />
          <h2 className="history-title">All recent questions</h2>
          <History />
        </main>
      )}
    </div>
  );
}
