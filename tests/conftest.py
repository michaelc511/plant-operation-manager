"""Shared fixtures. Nothing here calls OpenAI."""

import hashlib
from types import SimpleNamespace

import chromadb
import pytest

from rag.llm import LLMClient
from rag.vector_store import VectorStore


class FakeEmbeddings:
    """Stands in for client.embeddings: deterministic bag-of-words vectors."""

    def create(self, model, input):
        data = [SimpleNamespace(index=i, embedding=_vec(t)) for i, t in enumerate(input)]
        return SimpleNamespace(data=data, usage=SimpleNamespace(total_tokens=sum(len(t) // 4 for t in input)))


def _vec(text, dim=64):
    v = [0.0] * dim
    for word in text.lower().split():
        v[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
    return v


@pytest.fixture(autouse=True)
def _no_demo_tickets(monkeypatch):
    """Tests start from an empty sessions table; test_sessions.py covers the demo seed itself."""
    monkeypatch.setenv("DEMO_TICKETS", "0")
    monkeypatch.delenv("SESSION_IDLE_MINUTES", raising=False)
    # usage limits off unless a test turns them on (tests/test_limits.py)
    for name in ("RATE_LIMIT_PER_MINUTE", "RATE_LIMIT_PER_DAY", "DAILY_BUDGET_USD"):
        monkeypatch.setenv(name, "0")
    monkeypatch.delenv("ALLOW_INGEST", raising=False)
    from services import limits

    limits.reset()


@pytest.fixture
def llm():
    return LLMClient(client=SimpleNamespace(embeddings=FakeEmbeddings()))


@pytest.fixture
def store():
    client = chromadb.EphemeralClient()
    for c in client.list_collections():  # EphemeralClient is shared within a process
        client.delete_collection(c.name if hasattr(c, "name") else c)
    return VectorStore(client=client)
