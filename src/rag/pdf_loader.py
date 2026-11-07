"""Turn a source PDF into section-aware chunks with page metadata for citations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pypdf import PdfReader

from .config import CHUNK_CHARS, CHUNK_OVERLAP, Source

# Running header/footer lines repeated on every page.
_BOILERPLATE = [
    re.compile(r"^Northfield Components Inc\."),
    re.compile(r"^FICTIONAL SAMPLE DOCUMENT"),
    re.compile(r"^Note: FICTIONAL SAMPLE DOCUMENT"),
    re.compile(r"^part numbers and values are invented\.$"),
    re.compile(r"Page \d+ of \d+$"),
    re.compile(r"^[A-Z]{2,}-[A-Z0-9-]+ Rev \w+ \| Effective"),
]
_HEADING = re.compile(r"^(\d{1,2})(?:\.(\d{1,2}))?\.?\s+([A-Z][^\n]{2,70})$")


@dataclass
class Chunk:
    text: str
    source: str
    doc_no: str
    title: str
    section: str  # e.g. "5.2"
    section_title: str  # e.g. "The Six-Step Lockout Procedure"
    page_start: int
    page_end: int
    chunk_index: int = 0

    def to_metadata(self) -> dict:
        return {
            "source": self.source,
            "doc_no": self.doc_no,
            "title": self.title,
            "section": self.section,
            "section_title": self.section_title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_index": self.chunk_index,
        }


def _is_boilerplate(line: str) -> bool:
    return any(p.search(line) for p in _BOILERPLATE)


def _read_lines(path) -> list[tuple[int, str]]:
    """Return (page_number, line) pairs with headers and footers removed."""
    out = []
    for page_no, page in enumerate(PdfReader(str(path)).pages, start=1):
        for line in (page.extract_text() or "").splitlines():
            line = line.strip()
            if line and not _is_boilerplate(line):
                out.append((page_no, line))
    return out


def _sections(lines: list[tuple[int, str]]) -> list[tuple[str, str, list[tuple[int, str]]]]:
    """Group lines under numbered headings.

    A line counts as a heading only if it is the next number in sequence (N+1 or N.(M+1)),
    which keeps numbered list items such as "1. Prepare and notify." from being mistaken
    for headings.
    """
    sections = [("0", "Document information", [])]
    major, minor = 0, 0
    for page, line in lines:
        m = _HEADING.match(line)
        if m and not line.endswith(".") and ". " not in m.group(3):
            a, b = int(m.group(1)), m.group(2)
            if b is None and a == major + 1:
                major, minor = a, 0
                sections.append((str(a), m.group(3).strip(), []))
                continue
            if b is not None and a == major and int(b) == minor + 1:
                minor = int(b)
                sections.append((f"{a}.{b}", m.group(3).strip(), []))
                continue
        sections[-1][2].append((page, line))
    return [s for s in sections if s[2]]


def _windows(lines: list[tuple[int, str]]):
    """Split a section's lines into overlapping windows of about CHUNK_CHARS characters."""
    start = 0
    while start < len(lines):
        size, end = 0, start
        while end < len(lines) and (size == 0 or size + len(lines[end][1]) <= CHUNK_CHARS):
            size += len(lines[end][1]) + 1
            end += 1
        yield lines[start:end]
        if end >= len(lines):
            break
        # Step back far enough to repeat about CHUNK_OVERLAP characters.
        back, overlap = end, 0
        while back - 1 > start and overlap < CHUNK_OVERLAP:
            back -= 1
            overlap += len(lines[back][1]) + 1
        start = max(back, start + 1)


def load_chunks(source: Source) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sec, sec_title, sec_lines in _sections(_read_lines(source.path)):
        for window in _windows(sec_lines):
            body = "\n".join(line for _, line in window)
            header = f"[{source.doc_no} {source.title} - Section {sec} {sec_title}]"
            chunks.append(
                Chunk(
                    text=f"{header}\n{body}",
                    source=source.key,
                    doc_no=source.doc_no,
                    title=source.title,
                    section=sec,
                    section_title=sec_title,
                    page_start=window[0][0],
                    page_end=window[-1][0],
                    chunk_index=len(chunks),
                )
            )
    return chunks
