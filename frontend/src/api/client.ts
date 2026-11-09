// The only place the UI talks to the backend. All business logic stays in FastAPI.
import type { AskResponse, Health, QueryRecord, Session, SessionSummary } from "./types";

// "/api" goes through the Vite proxy (see vite.config.ts). Override with VITE_API_BASE if the
// app is served from somewhere else.
const BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const FRIENDLY: Record<number, string> = {
  0: "Can't reach the server. Check your Wi-Fi and that the plant assistant is running.",
  429: "Too many questions right now. Please try again shortly.",
  500: "The server hit an error. Please try again.",
  502: "The assistant's server isn't responding. Ask IT to check that the API is running.",
  504: "The assistant took too long to answer. Please try again.",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, FRIENDLY[0]);
  }
  if (!res.ok) {
    let message = FRIENDLY[res.status] ?? `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // keep the friendly message
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  // Source PDF opened at a page (most browsers honor #page=N).
  pdfUrl: (source: string, page?: number) =>
    `${BASE}/sources/${encodeURIComponent(source)}/pdf${page ? `#page=${page}` : ""}`,
  // One page-load ping for visitor counts (no body; the server stores a daily hash, never the IP).
  visit: () => fetch(`${BASE}/visit`, { method: "POST" }).then(() => undefined),
  ask: (question: string, session?: { sessionId?: string | null; customerId?: string }) =>
    request<AskResponse>("/ask", {
      method: "POST",
      body: JSON.stringify(
        session
          ? { question, session_id: session.sessionId ?? null, customer_id: session.customerId ?? "1" }
          : { question },
      ),
    }),
  queries: (limit = 30) => request<QueryRecord[]>(`/queries?limit=${limit}`),
  feedback: (queryId: number, helpful: boolean, note?: string) =>
    request<QueryRecord>(`/queries/${queryId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ helpful, note: note ?? null }),
    }),
  // Sessions (tickets): one active ticket per customer, stored by the backend.
  // create=false returns the last active ticket, or null if the customer closed it.
  activeSession: (customerId: string, create = true) =>
    request<Session | null>("/sessions/active", {
      method: "POST",
      body: JSON.stringify({ customer_id: customerId, create }),
    }),
  newSession: (customerId: string) =>
    request<Session>("/sessions/new", { method: "POST", body: JSON.stringify({ customer_id: customerId }) }),
  sessions: (customerId: string, limit = 20) =>
    request<SessionSummary[]>(`/sessions?customer_id=${encodeURIComponent(customerId)}&limit=${limit}`),
  closeSession: (sessionId: string, customerId: string) =>
    request<Session>(`/sessions/${encodeURIComponent(sessionId)}/close`, {
      method: "POST",
      body: JSON.stringify({ customer_id: customerId }),
    }),
  resumeSession: (sessionId: string, customerId: string) =>
    request<Session>(`/sessions/${encodeURIComponent(sessionId)}/resume`, {
      method: "POST",
      body: JSON.stringify({ customer_id: customerId }),
    }),
};
