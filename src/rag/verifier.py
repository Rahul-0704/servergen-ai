"""
ServerGen AI — Grounded Answer & Citation Verifier.

Validates that model-generated answers are grounded strictly in retrieved
and authorized evidence, flags hallucinated or un-retrieved citations,
and detects untrusted prompt injection patterns inside retrieved text.
"""

from __future__ import annotations

import logging
import re

from src.rag.schemas import CitationItem

logger = logging.getLogger("servergen.rag.verifier")

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+(override|prompt\s+leak)", re.IGNORECASE),
    re.compile(r"reveal\s+(all\s+)?(passwords|secrets|tokens|keys)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?safety\s+guidelines", re.IGNORECASE),
]


class CitationVerifier:
    """
    Deterministic citation and evidence grounding verification.
    """

    @staticmethod
    def detect_prompt_injection(text: str) -> list[str]:
        """Check for adversarial prompt injection attempts embedded in document content."""
        findings = []
        for pat in _PROMPT_INJECTION_PATTERNS:
            if pat.search(text):
                findings.append(f"suspected_adversarial_pattern_detected: {pat.pattern}")
        return findings

    @staticmethod
    def verify_citations(
        output_text: str,
        retrieved_citations: list[CitationItem],
    ) -> tuple[list[CitationItem], list[str]]:
        """
        Verify that all source citations in output match genuinely retrieved evidence.
        Flags warnings if the output references non-existent or fabricated sources.
        """
        warnings: list[str] = []
        verified_citations: list[CitationItem] = []

        retrieved_map: dict[int, CitationItem] = {
            c.citation_index: c for c in retrieved_citations
        }

        # Look for [Source X] references in text
        source_refs = re.findall(r"\[(?:Source\s*(\d+))[^\]]*\]", output_text, re.IGNORECASE)
        found_indices = {int(idx) for idx in source_refs if idx.isdigit()}

        for idx in found_indices:
            if idx in retrieved_map:
                verified_citations.append(retrieved_map[idx])
            else:
                warnings.append(
                    f"unverified_citation: cited [Source {idx}] not in retrieved context"
                )

        # If no explicit inline citation tags were found but chunks were provided,
        # associate the top retrieved citations that contributed to context
        if not verified_citations and retrieved_citations:
            verified_citations = list(retrieved_citations)

        return verified_citations, warnings
