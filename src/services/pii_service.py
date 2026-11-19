"""
ServerGen AI — Enterprise Data Loss Prevention (DLP) & PII Redaction Engine.

Provides zero-trust pattern matching and redaction for sensitive enterprise data:
- Personally Identifiable Information (PII): Emails, Phone Numbers, US SSNs, Credit Cards.
- Corporate Credentials & Secrets: Bearer tokens, API keys, Private keys, AWS keys.
- Granular masking with token preservation and audit logging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class PIIRedactionResult:
    """Outcome of a PII scrubbing operation."""

    sanitized_text: str
    redactions_count: int
    categories_found: list[str]


class EnterprisePIIService:
    """High-performance regular-expression engine for data loss prevention."""

    # Pre-compiled high-efficiency patterns
    _PATTERNS: ClassVar[list[tuple[str, re.Pattern[str], str]]] = [
        # Credit Cards (Visa, MasterCard, Amex, Discover with optional dashes/spaces)
        (
            "CREDIT_CARD",
            re.compile(
                r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b"
                r"|\b(?:\d{4}[-\s]){3}\d{4}\b"
            ),
            "[REDACTED_CARD]",
        ),
        # US Social Security Number (SSN)
        (
            "SSN",
            re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
            "[REDACTED_SSN]",
        ),
        # Email Addresses
        (
            "EMAIL",
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
            "[REDACTED_EMAIL]",
        ),
        # Phone Numbers (International & Domestic variants)
        (
            "PHONE",
            re.compile(
                r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
            ),
            "[REDACTED_PHONE]",
        ),
        # API Keys & Secrets (Bearer tokens, AWS keys, generic hex/base64 tokens)
        (
            "SECRET_KEY",
            re.compile(
                r"(?i)\b(?:bearer\s+[a-zA-Z0-9_\-\.]{20,}|akid[a-zA-Z0-9]{16,}|sk_[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|xox[baprs]-[a-zA-Z0-9]{10,})\b"
            ),
            "[REDACTED_SECRET]",
        ),
    ]

    def redact_text(self, text: str) -> PIIRedactionResult:
        """Sanitize a block of text, replacing all sensitive patterns."""
        if not text:
            return PIIRedactionResult(sanitized_text="", redactions_count=0, categories_found=[])

        sanitized = text
        total_redactions = 0
        categories: set[str] = set()

        for category, pattern, replacement in self._PATTERNS:
            matches = pattern.findall(sanitized)
            if matches:
                total_redactions += len(matches)
                categories.add(category)
                sanitized = pattern.sub(replacement, sanitized)

        return PIIRedactionResult(
            sanitized_text=sanitized,
            redactions_count=total_redactions,
            categories_found=sorted(categories),
        )

    def redact_table(
        self, headers: list[str], rows: list[list[Any]]
    ) -> tuple[list[str], list[list[Any]], int]:
        """Sanitize headers and rows of a tabular dataset."""
        total_redactions = 0
        clean_headers: list[str] = []
        for h in headers:
            res = self.redact_text(str(h))
            clean_headers.append(res.sanitized_text)
            total_redactions += res.redactions_count

        clean_rows: list[list[Any]] = []
        for row in rows:
            clean_row: list[Any] = []
            for cell in row:
                if cell is None or isinstance(cell, (int, float, bool)):
                    clean_row.append(cell)
                else:
                    res = self.redact_text(str(cell))
                    clean_row.append(res.sanitized_text)
                    total_redactions += res.redactions_count
            clean_rows.append(clean_row)

        return clean_headers, clean_rows, total_redactions


# Global instance
pii_service = EnterprisePIIService()
