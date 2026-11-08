# Architecture

## Overview
A FastAPI backend answers floor supervisors' questions from three controlled plant documents.
A LangGraph orchestrator runs three subagents: a router picks the document source(s), retrieval
searches only those sources in a local Chroma vector store, and a verifier writes a cited answer
and flags anything uncertain. Every question and answer is logged to SQLite.

## Components
| Layer | Path | Role |
|---|---|---|
| API | `src/main.py`, `src/api/` | Routes, Pydantic schemas, dependencies |
| Services | `src/services/` | Business logic between routes and data |
| Agents | `src/agents/` | LangGraph orchestrator and subagents; `base.py` is the API contract |
| Retrieval | `src/rag/` | PDF chunking, OpenAI wrapper (`llm.py`), Chroma store |
| Persistence | `src/persistence/` | SQLite query log and feedback |
| Prompts | `tools/prompts/` | `router.md`, `verifier.md` |
| Evals | `evaluation/` | Real-API cases and scorer |

## Agent graph
```
START -> orchestrator --> router    --> orchestrator
                      --> retrieval --> orchestrator
                      --> verifier  --> orchestrator
                      --> END
```
- **Orchestrator** (plain code, no LLM): decides the next step. Out of scope or too vague →
  finish. No evidence, or verifier finds no answer → widen the search to all sources once.
- **Router** (LLM, strict JSON): `in_scope` / `out_of_scope` / `clarify`, source list, and
  `safety_relevant`. If safety-relevant, the safety source is always added (FR5).
- **Retrieval** (hybrid): per routed source, vector search (Chroma, cosine >= 0.30) and BM25
  keyword search (`src/rag/keyword_index.py`, IDs like `HP-400` kept whole) each return 10
  candidates; Reciprocal Rank Fusion (`src/rag/hybrid.py`, k=60) merges them and keeps the top 4.
  Across sources the best 8 passages become evidence E1..En, each tagged `matched_by`
  vector / keyword / both. `RETRIEVAL_MODE=vector` switches back to vector-only.
- **Verifier** (LLM, strict JSON + code checks): answers only from evidence and lists claims.
  Code then drops citations to passages that weren't retrieved, flags unsupported claims,
  withholds answers with no valid citation (FR3), flags safety-relevant answers that cite no
  safety procedure, merges duplicate citations and renumbers markers to `[1]`, `[2]`.

## Guardrails
- **Scope:** the router declines out-of-scope questions and asks for clarification when a
  question is too vague.
- **Grounding:** the verifier answers only from evidence; code removes citations to passages
  that weren't retrieved, flags unsupported claims and withholds answers with no valid citation.
- **Safety:** safety-relevant questions always search the safety source, and answers that cite
  no safety procedure are flagged.
- **Prompt injection:** `tools/prompts/router.md` and `verifier.md` treat the question and
  evidence as data and ignore instructions inside them (eval case `oos-injection`).
- **Privacy:** `src/services/redact.py` strips keys, tokens, emails and phone numbers before
  session text is stored.

## AI governance
- **Audit trail:** `queries` records routes, citations, flags, confidence, cost, trace and
  feedback for every answer.
- **Human in the loop:** answers are advisory with flags shown as "Check before acting"; the
  app takes no actions.
- **Change control:** prompts (`tools/prompts/`) and model settings (`CHAT_MODEL`,
  `EMBEDDING_MODEL`) are versioned; CI runs the mocked test suite on every push; `evaluation/`
  measures answer and retrieval quality with the real API.
- **Not built yet:** auth and roles, per-user audit, rate limiting, input moderation, an
  AI-use policy and model card, and an eval gate in CI.

## Data flow
1. `POST /ask` → `services/ask.py` → `PlantQAAgent.run(question)`.
2. The graph returns status, routes, answer, citations, flags, confidence, trace and usage.
3. The service logs the result to the `queries` table and returns it.
4. `POST /queries/{id}/feedback` records whether the supervisor found it helpful.

## External services
- OpenAI: `text-embedding-3-small` for embeddings, `gpt-4.1-mini` for router and verifier
  (override with `EMBEDDING_MODEL` / `CHAT_MODEL`). Key from `OPENAI_API_KEY`.
- Local only: Chroma at `data/chroma/`, SQLite at `DATABASE_URL`.
