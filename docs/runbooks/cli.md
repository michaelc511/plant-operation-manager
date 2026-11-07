# Run the agents from the command line

Ask questions in the terminal. The LangGraph agents (router → retrieval → verifier) answer from
the three plant PDFs stored in the local Chroma vector store. No server is needed.

## 1. One-time setup
```bash
cd ~/projects/plant-operation-manager
python3.11 -m venv venv              # skip if venv/ already exists
source venv/bin/activate
pip install -r requirements.txt      # skip if already installed
```
Make sure `.env` has your OpenAI key (never commit `.env`):
```
OPENAI_API_KEY=sk-...
```

## 2. Build the vector store (once, and again after the PDFs change)
```bash
python tools/scripts/ingest_docs.py
```
Expected output: about 27 safety, 33 maintenance and 23 quality chunks, total cost well under $0.01.
Check retrieval without the agents:
```bash
python tools/scripts/ingest_docs.py --search "How often do we grease the CV-3 bearings?"
```

## 3. Ask a question
Every new terminal: `cd ~/projects/plant-operation-manager && source venv/bin/activate`

One question:
```bash
python tools/scripts/ask.py "How often do we grease the conveyor bearings on Line 3?"
```
Interactive mode (keep asking; `:trace` toggles agent steps, `:quit` exits):
```bash
python tools/scripts/ask.py
```
See what each agent did (routing decision, sources searched, passages kept, verification):
```bash
python tools/scripts/ask.py --trace "What torque do the HP-400 die clamp bolts need?"
```
Raw JSON (for scripts):
```bash
python tools/scripts/ask.py --json "Where is the evacuation assembly point?"
```

## Reading the output
| Part | Meaning |
|---|---|
| `ANSWERED` / `NOT_FOUND` / `CLARIFY` / `OUT_OF_SCOPE` | Outcome. Not found and out of scope mean the agent declined rather than guess |
| `routes` | Document sources the router picked (safety is added for any risky task) |
| `confidence` | Verifier's rating: high, medium or low |
| `[1]`, `[2]` and **Sources** | Each citation: document, section and page |
| **Check before acting** | Flags: unsupported claims, missing safety citation, widened search |
| Last line | Tokens, cost, time and model |

## Sample questions
- `What PPE do I need to clean the solvent tank?` (safety)
- `What's the acceptable diameter tolerance for part A-102?` (quality)
- `Can I replace a machine guard while the line is running?` (safety + maintenance)
- `After a die change on the HP-400, what inspection is required?` (all three)
- `How do I request vacation days?` (should be declined as out of scope)

## Troubleshooting
| Message | Fix |
|---|---|
| `OPENAI_API_KEY is not set` | Add the key to `.env` in the project root |
| `vector store has no chunks for ...` | Run `python tools/scripts/ingest_docs.py` |
| `ModuleNotFoundError` | Activate the venv: `source venv/bin/activate` |
| `reportlab requires 3.10+` or similar | Recreate the venv with `python3.11` (step 1) |

## Same agents over HTTP
To serve the agents to a UI, start the API instead (needs `DATABASE_URL=sqlite:///data/app.db` in
`.env`; questions are then logged to SQLite):
```bash
uvicorn main:app --reload --app-dir src
curl -s -X POST localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "How often do we grease CV-3?"}' | python3 -m json.tool
```
