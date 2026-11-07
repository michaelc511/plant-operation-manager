// Mirrors the FastAPI schemas in src/api/schemas.py.

export type SourceKey = "safety" | "maintenance" | "quality";
export type Route = SourceKey | "out_of_scope";
export type AnswerStatus = "answered" | "not_found" | "clarify" | "out_of_scope";
export type Confidence = "high" | "medium" | "low";

export interface Citation {
  source: SourceKey;
  doc_no: string;
  title: string;
  section: string;
  section_title: string;
  page_start: number;
  page_end: number;
}

export interface Usage {
  tokens: number;
  cost_usd: number;
}

export interface AskResponse {
  query_id: number;
  question: string;
  status: AnswerStatus;
  routes: Route[];
  answer: string;
  citations: Citation[];
  flags: string[];
  confidence: Confidence | null;
  trace: string[];
  usage: Usage;
  latency_ms: number;
  session_id: string;
  customer_id: string;
}

// What an answer card needs: an /ask reply, a query-log record or a restored session turn.
export type AnswerData = Omit<AskResponse, "session_id" | "customer_id">;

export interface QueryRecord extends Omit<AskResponse, "query_id" | "session_id" | "customer_id"> {
  id: number;
  created_at: string;
  helpful: boolean | null;
  feedback_note: string | null;
}

export interface Health {
  status: "ok";
  vector_store_ready: boolean;
  agent_ready: boolean;
}

export type SessionStatus = "active" | "closed";

export interface SessionMessage {
  id: number;
  session_id: string;
  customer_id: string;
  role: "user" | "assistant";
  message: string | null;
  answer: string | null;
  citations: Citation[];
  confidence: Confidence | null;
  status: AnswerStatus;
  query_id: number | null;
  created_at: string;
}

export interface Session {
  session_id: string;
  customer_id: string;
  status: SessionStatus;
  created_at: string;
  last_active_at: string;
  created: boolean;
  messages: SessionMessage[];
}

export interface SessionSummary {
  session_id: string;
  customer_id: string;
  status: SessionStatus;
  created_at: string;
  last_active_at: string;
  question_count: number;
  first_question: string | null;
}
