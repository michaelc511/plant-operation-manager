# 0001: Stack

- UI: React (Vite + TS), Streamlit, Gradio
- Backend: FastAPI (Python)
- Database: SQLite
- LLM: OpenAI
- Tests: pytest (Python), vitest (TypeScript)

## Why
TBD

## Guardrails and AI governance
- LangGraph keeps routing, retrieval and verification as separate, testable steps, so
  guardrails (scope, grounding, safety, prompt injection) are enforced in code, not only in
  prompts.
- SQLite holds the audit log (`queries`) for AI governance: every answer is traceable to its
  sources, flags, cost and feedback.
- OpenAI keys stay server-side in FastAPI; the React app never sees them.
