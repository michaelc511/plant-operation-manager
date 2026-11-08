# Run the React app (desktop and phone)

The React app (`frontend/`) is the supervisor-facing UI. It calls the FastAPI backend, which runs
the LangGraph agents over the vector store. The browser only talks to the Vite server: requests
to `/api/*` are forwarded to FastAPI, so a phone needs to reach just one address.

```
Phone / browser  →  Vite :5173  →(/api proxy)→  FastAPI :8000  →  LangGraph agents  →  Chroma + OpenAI
```

## 1. One-time setup
```bash
cd ~/projects/plant-operation-manager
echo 'DATABASE_URL=sqlite:///data/app.db' >> .env   # once; OPENAI_API_KEY must already be in .env
cd frontend && npm install && cd ..
```
The vector store must be built (`python tools/scripts/ingest_docs.py`); see `cli.md`.

## 2. Start the backend (terminal 1)
```bash
cd ~/projects/plant-operation-manager
source venv/bin/activate
uvicorn main:app --reload --app-dir src
```

## 3. Start the app (terminal 2)
On this computer only:
```bash
cd ~/projects/plant-operation-manager/frontend
npm run dev                 # open http://localhost:5173
```
For phones on the same Wi-Fi:
```bash
npm run dev:phone           # prints a "Network" URL such as http://192.168.1.98:5173
```

## 4. Open it on a phone
1. Connect the phone to the **same Wi-Fi** as the computer.
2. Open the **Network** URL printed by `npm run dev:phone` in Safari or Chrome.
3. If macOS asks whether `node` may accept incoming connections, click **Allow**.
4. Optional: Share → **Add to Home Screen** to open it like an app.

The green dot in the header means the app reached the backend and the agents are ready. A red
dot shows a banner explaining what's wrong.

## Using the app
- **Ask** tab: the top bar shows the signed-in customer (demo: Carl Wayne, customer ID 1,
  read-only) and the open ticket (e.g. **Ticket #1001 · Open**). **Close ticket** closes it (no
  ticket is open until you ask a question or tap **New ticket**). **New ticket** opens a fresh one
  and puts the current one on hold. Coming back later reopens your last active ticket. Type a
  question or tap a sample. Each answer shows its status, the documents
  searched, confidence, numbered citations (tap a number to jump to its source), a
  **Check before acting** box for flags, 👍/👎 feedback, and **How this was answered** (agent steps).
- **History** tab: **Ticket history** lists every other ticket with its state (On hold,
  Escalated, Resolved, Closed) and a **Reopen** button that makes it the open ticket again; then
  the last 30 questions from the query log; tap one to see the full answer.
- **First run:** an empty database starts with five demo tickets for Carl Wayne, #1001 (Open)
  to #1005 (Closed). Set `DEMO_TICKETS=0` in `.env` to start empty.

## Production-style build
```bash
cd frontend
npm run build               # type-checks, then writes dist/
npm run preview             # serves dist/ on http://<computer-ip>:4173 with the same /api proxy
```

## Configuration
| Variable | Where | Default | Purpose |
|---|---|---|---|
| `API_PROXY_TARGET` | `frontend/.env` or shell | `http://localhost:8000` | Where Vite forwards `/api` |
| `VITE_API_BASE` | `frontend/.env` | `/api` | API base the browser calls, if served without the proxy |

## Troubleshooting
| Symptom | Fix |
|---|---|
| Red dot, "Can't reach the server" | Start the backend (step 2) and check `curl localhost:8000/health` |
| Phone can't open the Network URL | Same Wi-Fi? Allow `node` in macOS firewall; some guest networks block device-to-device traffic |
| "The document index isn't built yet" | Run `python tools/scripts/ingest_docs.py` |
| `OPENAI_API_KEY is not set` in an answer | Add the key to the project's `.env` and restart the backend |

## Guardrails and AI governance
- The app declines out-of-scope questions, says "not found" instead of guessing, and always
  includes safety procedures for risky tasks.
- Answers are advisory: read the **Check before acting** box and the cited sources before acting.
- Every answer and 👍/👎 is saved to the audit log (`queries`); keys, emails and phone numbers
  are redacted before session history is stored.

## Security note
`npm run dev:phone` exposes the app to everyone on the local network, with no login. Use it on
a trusted network only; add authentication before any wider rollout.
