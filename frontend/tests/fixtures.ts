import type { AskResponse, QueryRecord, Session, SessionSummary } from "../src/api/types";

export const ANSWER: AskResponse = {
  query_id: 7,
  question: "How often do we grease the conveyor bearings on Line 3?",
  status: "answered",
  routes: ["maintenance", "safety"],
  answer: "Grease every 250 operating hours [1]. Lock out CV-3 at DS-3C first [2].",
  citations: [
    { source: "maintenance", doc_no: "MM-100", title: "Equipment Maintenance Manual", section: "4.1",
      section_title: "Bearing Lubrication", page_start: 3, page_end: 4 },
    { source: "safety", doc_no: "EHS-SOP-001", title: "Plant Safety Procedures", section: "5.3",
      section_title: "Energy Sources by Equipment", page_start: 4, page_end: 4 },
  ],
  flags: ["Check EHS-SOP-001 before starting."],
  confidence: "high",
  trace: ["orchestrator: -> router", "router: in_scope"],
  usage: { tokens: 3200, cost_usd: 0.0017 },
  latency_ms: 4100,
  session_id: "sess1111aaaa",
  customer_id: "1",
  ticket_no: 1002,
};

export const RECORD: QueryRecord = {
  ...ANSWER,
  id: 7,
  created_at: "2026-11-06T18:00:00Z",
  helpful: null,
  feedback_note: null,
};

export const SESSION: Session = {
  session_id: "sess1111aaaa",
  customer_id: "1",
  ticket_no: 1002,
  status: "active",
  state: "open",
  created_at: "2026-11-06T18:00:00Z",
  last_active_at: "2026-11-06T18:00:00Z",
  created: false,
  messages: [],
};

export const OLD_SESSION: Session = {
  ...SESSION,
  session_id: "sess0000old0",
  ticket_no: 1001,
  created_at: "2026-11-05T09:00:00Z",
  messages: [
    { id: 1, session_id: "sess0000old0", customer_id: "1", role: "user", message: "What PPE for the solvent tank?",
      answer: null, citations: [], confidence: null, status: "answered", query_id: 3, created_at: "2026-11-05T09:00:00Z" },
    { id: 2, session_id: "sess0000old0", customer_id: "1", role: "assistant", message: null,
      answer: "Wear a respirator and nitrile gloves [1].", citations: [ANSWER.citations[1]], confidence: "high",
      status: "answered", query_id: 3, created_at: "2026-11-05T09:00:05Z" },
  ],
};

export const SUMMARIES: SessionSummary[] = [
  { session_id: SESSION.session_id, customer_id: "1", ticket_no: 1002, status: "active", state: "open", created_at: SESSION.created_at,
    last_active_at: SESSION.last_active_at, question_count: 0, first_question: null },
  { session_id: OLD_SESSION.session_id, customer_id: "1", ticket_no: 1001, status: "closed", state: "on_hold", created_at: OLD_SESSION.created_at,
    last_active_at: OLD_SESSION.created_at, question_count: 1, first_question: "What PPE for the solvent tank?" },
];

export const HEALTH = { status: "ok", vector_store_ready: true, agent_ready: true };

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
