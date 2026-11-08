// Session helpers: the demo customer ID and turning stored session messages back into exchanges.
import type { AnswerData, Route, Session, SessionMessage, SourceKey } from "../api/types";

// The demo signs in one fixed customer (Carl Wayne, see customers.ts); the ID is shown read-only.
export const DEMO_CUSTOMER_ID = "1";

export type Exchange = {
  key: number;
  question: string;
  answer?: AnswerData;
  error?: string;
};

// The session store keeps the answer, citations, confidence and status only (no trace, flags or cost),
// so restored answers show those and skip the rest.
function toAnswer(m: SessionMessage, question: string): AnswerData {
  const sources = [...new Set(m.citations.map((c) => c.source))] as SourceKey[];
  const routes: Route[] = m.status === "out_of_scope" ? ["out_of_scope"] : sources;
  return {
    query_id: m.query_id ?? 0,
    question,
    status: m.status,
    routes,
    answer: m.answer ?? "",
    citations: m.citations,
    flags: [],
    confidence: m.confidence,
    trace: [],
    usage: { tokens: 0, cost_usd: 0 },
    latency_ms: 0,
  };
}

export function exchangesFromSession(s: Session, nextKey: () => number): Exchange[] {
  const out: Exchange[] = [];
  for (const m of s.messages) {
    if (m.role === "user") out.push({ key: nextKey(), question: m.message ?? "" });
    else if (out.length && !out[out.length - 1].answer) {
      const last = out[out.length - 1];
      last.answer = toAnswer(m, last.question);
    }
  }
  return out;
}

export function when(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}
