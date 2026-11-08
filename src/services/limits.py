"""Usage limits for a public demo without login. Plain code, no LLM call.

    check_rate(client_ip)   -> per-visitor limit on paid calls (/ask, /search):
                               RATE_LIMIT_PER_MINUTE (default 5) and RATE_LIMIT_PER_DAY (default 50)
    check_budget(conn)      -> refuses paid calls once today's logged OpenAI cost (UTC day, from the
                               queries table) reaches DAILY_BUDGET_USD (default 1.00)
    ingest_allowed()        -> ALLOW_INGEST (default on; the Docker image sets it to 0)

Set a limit to 0 to switch it off. Counters are in memory, which is correct for the single Fly
machine this app runs on; they reset when the machine restarts.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

DEFAULT_PER_MINUTE = 5
DEFAULT_PER_DAY = 50
DEFAULT_DAILY_BUDGET_USD = 1.00


class RateLimitedError(Exception):
    """A visitor made too many paid calls (HTTP 429)."""


class BudgetExceededError(Exception):
    """Today's OpenAI spend reached the daily budget (HTTP 429)."""


class IngestDisabledError(Exception):
    """Re-indexing is switched off on this server (HTTP 403)."""


def _number(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, default)))
    except ValueError:
        return default


def _utcnow() -> datetime:  # patched in tests
    return datetime.now(timezone.utc)


# ---- per-visitor rate limit
_lock = threading.Lock()
_calls: dict[str, deque[float]] = defaultdict(deque)


def reset() -> None:
    """Clear all counters (tests)."""
    with _lock:
        _calls.clear()


def check_rate(client_ip: str, now: float | None = None) -> None:
    per_minute = int(_number("RATE_LIMIT_PER_MINUTE", DEFAULT_PER_MINUTE))
    per_day = int(_number("RATE_LIMIT_PER_DAY", DEFAULT_PER_DAY))
    if not per_minute and not per_day:
        return
    now = time.time() if now is None else now
    with _lock:
        calls = _calls[client_ip]
        while calls and calls[0] <= now - 86400:  # keep one day of history
            calls.popleft()
        if per_day and len(calls) >= per_day:
            raise RateLimitedError(f"Daily limit of {per_day} questions reached for this device. Try again tomorrow.")
        if per_minute and sum(1 for t in calls if t > now - 60) >= per_minute:
            raise RateLimitedError(f"Too many questions: the limit is {per_minute} a minute. Try again shortly.")
        calls.append(now)


# ---- daily OpenAI budget
def spent_today(conn: sqlite3.Connection) -> float:
    start = _utcnow().strftime("%Y-%m-%dT00:00:00Z")
    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM queries WHERE created_at >= ?", (start,)).fetchone()
    return float(row[0])


def check_budget(conn: sqlite3.Connection) -> None:
    budget = _number("DAILY_BUDGET_USD", DEFAULT_DAILY_BUDGET_USD)
    if budget and spent_today(conn) >= budget:
        raise BudgetExceededError("The demo's daily question limit has been reached. Please try again tomorrow.")


# ---- re-indexing switch
def ingest_allowed() -> bool:
    return os.getenv("ALLOW_INGEST", "1") != "0"


def check_ingest() -> None:
    if not ingest_allowed():
        raise IngestDisabledError("Re-indexing is switched off on this server.")
