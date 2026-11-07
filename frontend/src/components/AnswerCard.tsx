import { useState } from "react";
import { api } from "../api/client";
import type { AnswerData } from "../api/types";
import { AnswerText } from "./AnswerText";
import { ROUTE_LABEL, STATUS_LABEL, pages } from "./labels";

type Props = {
  data: AnswerData;
  initialHelpful?: boolean | null;
};

export function AnswerCard({ data, initialHelpful = null }: Props) {
  const prefix = `q${data.query_id}-cite`;
  return (
    <article className={`answer-card status-${data.status}`} aria-label="Answer">
      <header className="answer-meta">
        <span className={`badge badge-${data.status}`}>{STATUS_LABEL[data.status]}</span>
        {data.routes
          .filter((r) => r !== "out_of_scope")
          .map((r) => (
            <span key={r} className={`chip chip-${r}`}>
              {ROUTE_LABEL[r]}
            </span>
          ))}
        {data.confidence && (
          <span className={`confidence confidence-${data.confidence}`}>{data.confidence[0].toUpperCase() + data.confidence.slice(1)} confidence</span>
        )}
      </header>

      <AnswerText text={data.answer} citeIdPrefix={prefix} citationCount={data.citations.length} />

      {data.flags.length > 0 && (
        <section className="flags" aria-label="Check before acting">
          <h3>Check before acting</h3>
          <ul>
            {data.flags.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </section>
      )}

      {data.citations.length > 0 && (
        <section className="sources" aria-label="Sources">
          <h3>Sources</h3>
          <ol>
            {data.citations.map((c, i) => (
              <li key={i} id={`${prefix}-${i + 1}`}>
                <span className={`source-dot dot-${c.source}`} aria-hidden="true" />
                <span>
                  <strong>
                    {c.doc_no} §{c.section}
                  </strong>{" "}
                  {c.section_title}
                  <span className="source-sub">
                    {c.title} · {pages(c.page_start, c.page_end)}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {data.query_id > 0 && <Feedback queryId={data.query_id} initial={initialHelpful} />}

      {data.trace.length > 0 && (
      <details className="trace">
        <summary>How this was answered</summary>
        <ol>
          {data.trace.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ol>
        <p className="usage">
          {(data.latency_ms / 1000).toFixed(1)} s · {data.usage.tokens.toLocaleString()} tokens · $
          {data.usage.cost_usd.toFixed(4)}
        </p>
      </details>
      )}
    </article>
  );
}

function Feedback({ queryId, initial }: { queryId: number; initial: boolean | null }) {
  const [helpful, setHelpful] = useState<boolean | null>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(value: boolean) {
    setSaving(true);
    setError(null);
    try {
      await api.feedback(queryId, value);
      setHelpful(value);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="feedback">
      <span>{helpful === null ? "Was this helpful?" : "Thanks for the feedback"}</span>
      <button
        type="button"
        className={helpful === true ? "fb-btn selected" : "fb-btn"}
        aria-pressed={helpful === true}
        aria-label="Helpful"
        disabled={saving}
        onClick={() => send(true)}
      >
        👍
      </button>
      <button
        type="button"
        className={helpful === false ? "fb-btn selected" : "fb-btn"}
        aria-pressed={helpful === false}
        aria-label="Not helpful"
        disabled={saving}
        onClick={() => send(false)}
      >
        👎
      </button>
      {error && (
        <span role="alert" className="inline-error">
          {error}
        </span>
      )}
    </div>
  );
}
