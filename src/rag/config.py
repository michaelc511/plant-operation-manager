"""Paths and the registry of knowledge sources. Secrets come only from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DOCS_DIR = ROOT / "docs"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", ROOT / "data" / "chroma"))

# Chunking: target size and overlap in characters (about 4 characters per token).
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200


@dataclass(frozen=True)
class Source:
    key: str  # routing label and vector-store collection name
    doc_no: str
    title: str
    filename: str

    @property
    def path(self) -> Path:
        return DOCS_DIR / self.filename


SOURCES: dict[str, Source] = {
    "safety": Source("safety", "EHS-SOP-001", "Plant Safety Procedures", "safety_procedures.pdf"),
    "maintenance": Source("maintenance", "MM-100", "Equipment Maintenance Manual", "maintenance_manual.pdf"),
    "quality": Source("quality", "QC-STD-200", "Quality Control Standards", "quality_control_standards.pdf"),
}
