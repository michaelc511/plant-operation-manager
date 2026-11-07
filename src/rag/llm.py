"""The project's single wrapper around the OpenAI SDK. Model names and prices live here only."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")

# USD per 1M tokens, for cost logging. Update if the model or price changes.
EMBEDDING_PRICE_PER_M = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}
CHAT_PRICE_PER_M = {  # (input, output)
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
}


class MissingAPIKeyError(RuntimeError):
    pass


class LLMUnavailableError(RuntimeError):
    """The provider call failed or returned something unusable."""


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    total_tokens: int
    latency_s: float

    @property
    def cost_usd(self) -> float:
        return self.total_tokens / 1_000_000 * EMBEDDING_PRICE_PER_M.get(EMBEDDING_MODEL, 0.0)


@dataclass
class ChatResult:
    data: dict
    prompt_tokens: int
    completion_tokens: int
    latency_s: float

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> float:
        p_in, p_out = CHAT_PRICE_PER_M.get(CHAT_MODEL, (0.0, 0.0))
        return (self.prompt_tokens * p_in + self.completion_tokens * p_out) / 1_000_000


class LLMClient:
    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            if not os.getenv("OPENAI_API_KEY"):
                raise MissingAPIKeyError(
                    "OPENAI_API_KEY is not set. Add it to the project's .env file (see .env.example)."
                )
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def embed(self, texts: list[str], batch_size: int = 100) -> EmbeddingResult:
        vectors: list[list[float]] = []
        tokens = 0
        start = time.perf_counter()
        for i in range(0, len(texts), batch_size):
            try:
                resp = self.client.embeddings.create(model=EMBEDDING_MODEL, input=texts[i : i + batch_size])
            except MissingAPIKeyError:
                raise
            except Exception as exc:  # network, auth, rate limit
                raise LLMUnavailableError(f"Embedding request failed: {exc}") from exc
            vectors += [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
            tokens += resp.usage.total_tokens
        return EmbeddingResult(vectors, tokens, time.perf_counter() - start)

    def chat_json(self, system: str, user: str, schema_name: str, schema: dict) -> ChatResult:
        """One chat completion constrained to a strict JSON schema. Temperature 0 for repeatability."""
        start = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(
                model=CHAT_MODEL,
                temperature=0,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
            )
        except MissingAPIKeyError:
            raise
        except Exception as exc:
            raise LLMUnavailableError(f"Chat request failed: {exc}") from exc
        msg = resp.choices[0].message
        if getattr(msg, "refusal", None):
            raise LLMUnavailableError(f"Model refused: {msg.refusal}")
        try:
            data = json.loads(msg.content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMUnavailableError("Model returned invalid JSON") from exc
        return ChatResult(data, resp.usage.prompt_tokens, resp.usage.completion_tokens, time.perf_counter() - start)
