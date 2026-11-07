"""Load system prompts from tools/prompts/."""

from functools import lru_cache

from rag.config import ROOT

PROMPTS_DIR = ROOT / "tools" / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()
