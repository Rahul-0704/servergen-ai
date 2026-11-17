"""
ServerGen AI — Enterprise Permission-Aware Hybrid Retriever.

Implements access-controlled information retrieval:
1. Strict server-side RBAC & clearance filtering before candidate retrieval.
2. Semantic vector search using cosine similarity.
3. Keyword search for technical identifiers, error codes, and exact terms.
4. Reciprocal Rank Fusion (RRF) to merge semantic and keyword results.
5. Source citation assembly and insufficient-evidence detection.
"""

from __future__ import annotations

import logging
import re
import time
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.schemas import DataSensitivity
from src.auth.rbac import AuthContext
from src.models.document import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentStatus,
)
from src.rag.embeddings import (
    BaseEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from src.rag.schemas import (
    CitationItem,
    DocumentCategory,
    KnowledgeChunk,
    RAGRetrievalResult,
)
from src.rag.store import KnowledgeStore

logger = logging.getLogger("servergen.rag.retriever")


class RoleFilteredRetriever:
    """
    Retrieves organizational knowledge with strict RBAC boundary checks
    and hybrid semantic + keyword result fusion.
    """

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
        "give", "please", "help", "know", "how", "why", "when", "where", "is", "in", "at", "of",
    }

    def __init__(
        self,
        embedding_provider: BaseEmbeddingProvider | None = None,
        store: KnowledgeStore | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.store = store or KnowledgeStore.get_instance()

    async def retrieve(
        self,
        query: str,
        auth: AuthContext,
        top_k: int = 4,
        min_relevance: float = 0.25,
        db: AsyncSession | None = None,
        max_sensitivity: DataSensitivity | None = None,
    ) -> RAGRetrievalResult:
        """
        Execute permission-aware hybrid retrieval against authorized documents.
        Never retrieves or exposes chunks with classifications higher than user's clearance
        or outside user's allowed roles.
        """
        start_time = time.monotonic()
        user_role = auth.role.lower()
        max_clearance = self._ROLE_MAX_CLEARANCE.get(user_role, DataSensitivity.INTERNAL)
        max_clearance_rank = self._SENSITIVITY_ORDER[max_clearance]
        if max_sensitivity is not None:
            max_allowed_rank = min(max_clearance_rank, self._SENSITIVITY_ORDER[max_sensitivity])
        else:
            max_allowed_rank = max_clearance_rank

        candidate_chunks: list[dict] = []
        denied_count = 0
        total_searched = 0

        # ── 1. Query Database Chunks if DB session provided ──────────────────
        if db is not None:
            # Fetch all active, non-deleted documents
            stmt_docs = select(Document).where(
                Document.is_deleted.is_(False),
                Document.status == DocumentStatus.INDEXED,
            )
            res_docs = await db.execute(stmt_docs)
            all_db_docs = res_docs.scalars().all()

            for doc in all_db_docs:
                doc_sens = DataSensitivity(doc.classification.lower())
                doc_rank = self._SENSITIVITY_ORDER[doc_sens]
                doc_roles = [r.lower() for r in (doc.allowed_roles or [])]
                is_permitted = (
                    doc_rank <= max_allowed_rank
                    and (
                        user_role == "administrator"
                        or (
                            doc_rank <= max_clearance_rank
                            and (not doc_roles or user_role in doc_roles)
                        )
                        or (doc.owner_id is not None and str(doc.owner_id) == auth.user_id)
                    )
                )

                if not doc.active_version_id:
                    continue

                # Query chunks for active version
                stmt_chunks = (
                    select(DocumentChunk, ChunkEmbedding)
                    .outerjoin(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
                    .where(
                        DocumentChunk.document_id == doc.id,
                        DocumentChunk.version_id == doc.active_version_id,
                    )
                )
                res_chunks = await db.execute(stmt_chunks)
                chunk_rows = res_chunks.all()

                total_searched += len(chunk_rows)

                for chunk, embedding in chunk_rows:
                    if not is_permitted:
                        denied_count += 1
                        continue

                    cat = (
                        DocumentCategory(doc.category)
                        if doc.category in DocumentCategory
                        else DocumentCategory.GENERAL
                    )
                    candidate_chunks.append({
                        "chunk_id": str(chunk.id),
                        "doc_id": doc.id,
                        "doc_title": doc.title,
                        "content": chunk.content,
                        "category": cat,
                        "classification": doc_sens,
                        "allowed_roles": doc.allowed_roles or [],
                        "page_number": chunk.page_number,
                        "section_heading": chunk.section_heading,
                        "version_number": 1,
                        "vector": embedding.embedding_vector if embedding else None,
                    })

        # ── 2. Include in-memory seeded store chunks (fallback/baseline) ─────
        seeded_chunks = self.store.list_chunks()
        total_searched += len(seeded_chunks)

        for sc in seeded_chunks:
            sc_rank = self._SENSITIVITY_ORDER[sc.classification]
            has_role_permission = (
                not sc.allowed_roles or user_role in [r.lower() for r in sc.allowed_roles]
            )
            if sc_rank > max_allowed_rank or (
                not has_role_permission and user_role != "administrator"
            ):
                denied_count += 1
                continue

            candidate_chunks.append({
                "chunk_id": sc.chunk_id,
                "doc_id": sc.doc_id,
                "doc_title": sc.doc_title,
                "content": sc.content,
                "category": sc.category,
                "classification": sc.classification,
                "allowed_roles": sc.allowed_roles,
                "page_number": None,
                "section_heading": None,
                "version_number": 1,
                "vector": None,
            })

        if not candidate_chunks:
            return RAGRetrievalResult(
                chunks=[],
                total_searched=total_searched,
                denied_chunks_count=denied_count,
                highest_sensitivity=DataSensitivity.PUBLIC,
                context_text="",
                insufficient_evidence=True,
                execution_time_ms=round((time.monotonic() - start_time) * 1000, 1),
            )

        # ── 3. Hybrid Semantic & Keyword Scoring ─────────────────────────────
        raw_terms = re.findall(r"\w{3,}", query.lower())
        query_terms = {t for t in raw_terms if t not in self._STOPWORDS}
        if not query_terms:
            query_terms = set(raw_terms)

        # Generate query vector for semantic matching
        query_vector = await self.embedding_provider.embed_text(query)

        # Semantic candidates
        semantic_ranked: list[tuple[float, dict]] = []
        for cand in candidate_chunks:
            cand_vec = cand["vector"]
            if not cand_vec:
                # Generate embedding on the fly if chunk didn't have one cached
                cand_vec = await self.embedding_provider.embed_text(cand["content"])
                cand["vector"] = cand_vec

            sim = cosine_similarity(query_vector, cand_vec)
            semantic_ranked.append((sim, cand))

        semantic_ranked.sort(key=lambda x: x[0], reverse=True)

        # Keyword candidates
        keyword_ranked: list[tuple[float, dict]] = []
        for cand in candidate_chunks:
            sec_heading = cand["section_heading"] or ""
            searchable = f"{cand['content']} {cand['doc_title']} {sec_heading}".lower()
            cand_words = set(re.findall(r"\w{3,}", searchable))
            overlap = sum(1 for term in query_terms if term in cand_words)
            kw_score = (overlap / len(query_terms)) if query_terms else 0.0

            # Exact phrase match boost
            if query.lower() in searchable:
                kw_score += 0.35

            keyword_ranked.append((kw_score, cand))

        keyword_ranked.sort(key=lambda x: x[0], reverse=True)

        # ── 4. Reciprocal Rank Fusion (RRF) ──────────────────────────────────
        rrf_scores: dict[str, float] = {}
        sem_scores: dict[str, float] = {}
        kw_scores: dict[str, float] = {}
        chunk_map: dict[str, dict] = {}

        k_rrf = 60
        for rank_idx, (sim, cand) in enumerate(semantic_ranked):
            cid = cand["chunk_id"]
            chunk_map[cid] = cand
            sem_scores[cid] = round(sim, 3)
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k_rrf + rank_idx + 1))

        for rank_idx, (kw, cand) in enumerate(keyword_ranked):
            cid = cand["chunk_id"]
            kw_scores[cid] = round(kw, 3)
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k_rrf + rank_idx + 1))

        # Combined normalized score
        fused_results: list[tuple[float, KnowledgeChunk]] = []
        for cid, _rrf_val in rrf_scores.items():
            cand = chunk_map[cid]
            s_score = sem_scores.get(cid, 0.0)
            k_score = kw_scores.get(cid, 0.0)

            # Blended relevance score
            blended = round((0.60 * s_score) + (0.40 * min(1.0, k_score)), 3)

            # Strict relevance filter: candidate must meet min_relevance
            if blended < min_relevance:
                continue

            kc = KnowledgeChunk(
                chunk_id=cid,
                doc_id=cand["doc_id"],
                doc_title=cand["doc_title"],
                content=cand["content"],
                category=cand["category"],
                classification=cand["classification"],
                allowed_roles=cand["allowed_roles"],
                relevance_score=blended,
                semantic_score=s_score,
                keyword_score=k_score,
                page_number=cand.get("page_number"),
                section_heading=cand.get("section_heading"),
                version_number=cand.get("version_number", 1),
                retrieval_method="hybrid_rrf",
            )
            fused_results.append((blended, kc))

        fused_results.sort(key=lambda x: x[0], reverse=True)
        selected_chunks = [kc for _, kc in fused_results[:top_k]]

        insufficient_evidence = len(selected_chunks) == 0

        # Determine highest sensitivity among retrieved chunks
        highest_sens = DataSensitivity.PUBLIC
        for c in selected_chunks:
            if self._SENSITIVITY_ORDER[c.classification] > self._SENSITIVITY_ORDER[highest_sens]:
                highest_sens = c.classification

        # Assemble citations and structured context text
        citations: list[CitationItem] = []
        context_blocks: list[str] = []

        for idx, c in enumerate(selected_chunks, start=1):
            source_ref = f"Source {idx}: {c.doc_title}"
            loc_parts = []
            if c.page_number is not None:
                loc_parts.append(f"Page {c.page_number}")
            if c.section_heading:
                loc_parts.append(f"Section: {c.section_heading}")
            loc_str = f" ({', '.join(loc_parts)})" if loc_parts else ""

            cls_str = c.classification.value.upper()
            context_blocks.append(
                f"[{source_ref}{loc_str} | Classification: {cls_str}]\n{c.content}"
            )

            citations.append(
                CitationItem(
                    citation_index=idx,
                    document_id=str(c.doc_id),
                    document_title=c.doc_title,
                    version_number=c.version_number,
                    page_number=c.page_number,
                    section_heading=c.section_heading,
                    classification=c.classification.value,
                    relevance_score=c.relevance_score,
                    excerpt=c.content[:200] + ("..." if len(c.content) > 200 else ""),
                    is_verified=True,
                )
            )

        context_text = "\n\n".join(context_blocks)
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 1)

        return RAGRetrievalResult(
            chunks=selected_chunks,
            total_searched=total_searched,
            denied_chunks_count=denied_count,
            highest_sensitivity=highest_sens,
            context_text=context_text,
            insufficient_evidence=insufficient_evidence,
            retrieval_strategy="hybrid_rrf",
            execution_time_ms=elapsed_ms,
            citations=citations,
        )
