"""Strip secrets and personal contact data from text before it is stored in session history.

Covers API keys and tokens, credential assignments, emails and phone numbers. Plant data such as
part numbers, drawing revisions and torque specs is left alone: it is the answer content.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),                          # OpenAI-style keys
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),                     # AWS access key IDs
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),                    # GitHub tokens
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),                    # Slack tokens
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWTs
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),            # Authorization: Bearer ...
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # emails
    re.compile(r"(?<![\w-])(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?![\w-])"),  # phone numbers
]


def redact(text: str | None) -> str | None:
    if not text:
        return text
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text
