"""LangSmith tracing: run name/tags, client wrapping and retriever trace shape. No network, no API key."""
from rag.hybrid import Hit, _trace_inputs, _trace_outputs
from rag.llm import _traced
from agents.orchestrator import PROMPT_VERSION, RUN_NAME, trace_config
from rag.llm import CHAT_MODEL


def test_trace_config_local(monkeypatch):
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    cfg = trace_config()
    assert cfg["run_name"] == RUN_NAME == "plant-question"
    assert cfg["tags"] == [f"model:{CHAT_MODEL}", f"prompt:{PROMPT_VERSION}", "env:local"]


def test_trace_config_prod_on_fly(monkeypatch):
    monkeypatch.setenv("FLY_APP_NAME", "plant-operation-manager")
    assert "env:prod" in trace_config()["tags"]


def test_traced_never_breaks_the_client():
    class NotAnOpenAIClient:  # wrap_openai may reject it; the client must still come back usable
        pass

    client = NotAnOpenAIClient()
    assert _traced(client) is not None


def test_retriever_trace_drops_vector_and_shows_documents():
    inputs = _trace_inputs({"self": object(), "source": "safety", "question": "lockout?", "vector": [0.1] * 1536,
                            "k": 4, "min_vector_score": 0.3})
    assert "vector" not in inputs and "self" not in inputs and inputs["question"] == "lockout?"

    hit = Hit("c1", "Apply lockout tags.", {"page": 3}, 0.9, 0.8, 2.1)
    for raw in ([hit], {"output": [hit]}):
        doc = _trace_outputs(raw)["documents"][0]
        assert doc["page_content"] == "Apply lockout tags."
        assert doc["metadata"]["page"] == 3 and doc["metadata"]["chunk_id"] == "c1"
