-- Query log (FR8) and supervisor feedback (FR9). Applied by persistence.db.init_db; safe to re-run.
-- New columns must also be listed in persistence.db.MIGRATIONS so existing databases are upgraded.
CREATE TABLE IF NOT EXISTS queries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    question      TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    routes        TEXT    NOT NULL,              -- JSON array
    answer        TEXT    NOT NULL,
    citations     TEXT    NOT NULL,              -- JSON array
    flags         TEXT    NOT NULL DEFAULT '[]', -- JSON array of uncertainty notes
    confidence    TEXT,                          -- high / medium / low
    trace         TEXT    NOT NULL DEFAULT '[]', -- JSON array of agent steps
    tokens        INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL    NOT NULL DEFAULT 0,
    latency_ms    INTEGER NOT NULL DEFAULT 0,
    helpful       INTEGER,                       -- NULL = no feedback, 1 = helpful, 0 = not helpful
    feedback_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_queries_created_at ON queries (created_at);

-- Customer session storage: one row per turn (a 'user' row with the question, then an
-- 'assistant' row with the answer). Written only after an answer completes successfully.
-- Text is redacted by services.redact before it reaches this table; no keys, headers, trace or cost.
CREATE TABLE IF NOT EXISTS session_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL,
    customer_id   TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    message       TEXT,                          -- the question (user rows)
    answer        TEXT,                          -- the answer (assistant rows)
    citations     TEXT    NOT NULL DEFAULT '[]', -- JSON array (assistant rows)
    confidence    TEXT,                          -- high / medium / low (assistant rows)
    status        TEXT    NOT NULL,              -- answered / not_found / clarify / out_of_scope
    query_id      INTEGER REFERENCES queries (id),
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_session_messages_session ON session_messages (session_id, id);

-- One row per conversation. SessionAgent reuses a customer's 'active' session while it has been
-- used within the idle window, otherwise closes it and creates a new one.
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    customer_id    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    -- Ticket state shown to users. The active session is 'open'; switching away puts it 'on_hold';
    -- Close ticket makes it 'closed'; 'escalated' and 'resolved' are set by staff (demo seed only).
    state          TEXT NOT NULL DEFAULT 'open'
                   CHECK (state IN ('open', 'on_hold', 'escalated', 'resolved', 'closed')),
    created_at     TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_customer_active ON sessions (customer_id, status, last_active_at);

-- Backfill: sessions that only exist as messages (stored before this table existed).
INSERT OR IGNORE INTO sessions (session_id, customer_id, status, created_at, last_active_at)
SELECT session_id, MIN(customer_id), 'active', MIN(created_at), MAX(created_at)
FROM session_messages GROUP BY session_id;

-- Visitor counts (privacy-friendly): one row per visitor per UTC day. `visitor` is a one-way hash
-- of the IP with a secret salt and the day, so no raw IP is stored and visitors can't be followed
-- across days. Written by services.visits on the UI's page-load ping (POST /visit).
CREATE TABLE IF NOT EXISTS visits (
    day     TEXT    NOT NULL,              -- YYYY-MM-DD (UTC)
    visitor TEXT    NOT NULL,              -- sha256(salt|day|ip), first 16 hex chars
    views   INTEGER NOT NULL DEFAULT 1,    -- page loads by this visitor that day
    PRIMARY KEY (day, visitor)
);

-- Small key/value settings (e.g. the visitor-hash salt, created once per database).
CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
