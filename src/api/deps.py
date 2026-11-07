"""Shared dependencies. Tests replace these with app.dependency_overrides."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from agents.base import AnswerAgent
from agents.orchestrator import PlantQAAgent
from persistence.db import connect
from rag.llm import LLMClient
from rag.vector_store import VectorStore


@lru_cache
def get_store() -> VectorStore:
    return VectorStore()


@lru_cache
def get_llm() -> LLMClient:
    return LLMClient()


@lru_cache
def get_agent() -> AnswerAgent:
    return PlantQAAgent(get_llm(), get_store())


def get_db() -> Iterator:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
