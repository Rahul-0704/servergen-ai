"""
ServerGen AI — Role-Filtered Knowledge Retriever.

Implements access-controlled information retrieval:
1. Filters candidate chunks by the caller's active role and clearance level.
2. Performs lexical and keyword relevance ranking.
3. Formats verified organizational context for grounding the local LLM.
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from src.ai.schemas import DataSensitivity
from src.auth.rbac import AuthContext
from src.rag.schemas import KnowledgeChunk, RAGRetrievalResult
from src.rag.store import KnowledgeStore

logger = logging.getLogger("servergen.rag.retriever")


class RoleFilteredRetriever:
    """Retrieves organizational knowledge with strict RBAC boundary checks."""

    # Maximum classification level accessible by role without extra approval
    _ROLE_MAX_CLEARANCE: ClassVar[dict[str, DataSensitivity]] = {
        "administrator": DataSensitivity.RESTRICTED,
        "it_operator": DataSensitivity.CONFIDENTIAL,
        "security_analyst": DataSensitivity.CONFIDENTIAL,
        "manager": DataSensitivity.RESTRICTED,
        "general_employee": DataSensitivity.INTERNAL,
    }

    _SENSITIVITY_ORDER: ClassVar[dict[DataSensitivity, int]] = {
        DataSensitivity.PUBLIC: 0,
        DataSensitivity.INTERNAL: 1,
        DataSensitivity.CONFIDENTIAL: 2,
        DataSensitivity.RESTRICTED: 3,
    }

    _STOPWORDS: ClassVar[set[str]] = {
        "the", "and", "this", "that", "with", "from", "for", "are", "was", "were", "been",
        "have", "has", "had", "what", "which", "who", "whom", "will", "would", "can", "could",
        "should", "does", "did", "doing", "you", "your", "our", "all", "any", "both", "each",
        "few", "more", "most", "other", "some", "such", "than", "too", "very", "about", "tell",
        "give", "please", "help", "know", "how", "why", "when", "where",
    }

    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self.store = store or KnowledgeStore.get_instance()

    def retrieve(
        self,
        query: str,
        auth: AuthContext,
        top_k: int = 3,
        min_relevance: float = 0.3,
    ) -> RAGRetrievalResult:
        """
        Retrieve relevant knowledge chunks permissible for the caller's role.

        Chunks with classifications higher than the user's clearance or without
        the user's role in `allowed_roles` are strictly excluded from the result.
        """
        all_chunks = self.store.list_chunks()
        user_role = auth.role.lower()
        max_clearance = self._ROLE_MAX_CLEARANCE.get(user_role, DataSensitivity.INTERNAL)
        max_clearance_rank = self._SENSITIVITY_ORDER[max_clearance]

        raw_terms = re.findall(r"\w{3,}", query.lower())
        query_terms = {t for t in raw_terms if t not in self._STOPWORDS}
        if not query_terms:
            query_terms = set(raw_terms)

        scored_chunks: list[tuple[float, KnowledgeChunk]] = []
        denied_count = 0
        total_searched = len(all_chunks)

        for chunk in all_chunks:
            # Check role clearance
            chunk_rank = self._SENSITIVITY_ORDER[chunk.classification]
            has_role_permission = not chunk.allowed_roles or user_role in [r.lower() for r in chunk.allowed_roles]

            # Compute term relevance score
            chunk_words = set(re.findall(r"\w{3,}", chunk.content.lower() + " " + chunk.doc_title.lower()))
            overlap = sum(1 for term in query_terms if term in chunk_words)
            if not overlap or not query_terms:
                score = 0.0
            else:
                score = overlap / len(query_terms)

            # Require at least 2 matching significant keywords if multiple query terms exist
            min_overlap = 2 if len(query_terms) >= 3 else 1
            if score >= min_relevance and overlap >= min_overlap:
                if chunk_rank > max_clearance_rank or not has_role_permission:
                    denied_count += 1
                    logger.warning(
                        "RAG Access Denied: User '%s' (%s) denied access to chunk '%s' [%s]",
                        auth.username or auth.user_id,
                        auth.role,
                        chunk.chunk_id,
                        chunk.classification.value,
                    )
                    continue

                chunk_copy = chunk.model_copy()
                chunk_copy.relevance_score = round(score, 3)
                scored_chunks.append((score, chunk_copy))

        # Sort by relevance descending
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        selected_chunks = [c for _, c in scored_chunks[:top_k]]

        # Determine highest sensitivity among retrieved chunks
        highest_sens = DataSensitivity.PUBLIC
        for c in selected_chunks:
            if self._SENSITIVITY_ORDER[c.classification] > self._SENSITIVITY_ORDER[highest_sens]:
                highest_sens = c.classification

        # Format context string
        context_blocks = []
        for idx, c in enumerate(selected_chunks, 1):
            context_blocks.append(
                f"[Source {idx}: {c.doc_title} | Classification: {c.classification.value.upper()}]\n{c.content}"
            )
        context_text = "\n\n".join(context_blocks)

        return RAGRetrievalResult(
            chunks=selected_chunks,
            total_searched=total_searched,
            denied_chunks_count=denied_count,
            highest_sensitivity=highest_sens,
            context_text=context_text,
        )
