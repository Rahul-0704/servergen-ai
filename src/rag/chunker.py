"""
ServerGen AI — Structure-Aware Document Chunker.

Splits parsed extracted blocks into configurable, structure-aware retrieval chunks
while preserving section headings, page numbers, and tabular boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.config import get_settings
from src.rag.parsers.base import ExtractedBlock


@dataclass
class ChunkItem:
    """A generated document chunk ready for embedding and storage."""

    chunk_index: int
    content: str
    token_count: int
    page_number: int | None = None
    section_heading: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentChunker:
    """
    Structure-aware chunker adhering to enterprise token budgets and boundaries.
    """

    def __init__(
        self,
        chunk_size_tokens: int | None = None,
        overlap_tokens: int | None = None,
    ) -> None:
        settings = get_settings()
        self.chunk_size = chunk_size_tokens or settings.RAG_CHUNK_SIZE_TOKENS
        self.overlap = overlap_tokens or settings.RAG_CHUNK_OVERLAP_TOKENS

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Heuristic token estimation (~4 characters per token or word count * 1.3)."""
        if not text:
            return 0
        words = len(text.split())
        return max(1, int(words * 1.3))

    def chunk_blocks(self, blocks: list[ExtractedBlock]) -> list[ChunkItem]:
        """
        Produce a sequential list of chunks from parsed blocks.
        Respects section titles, page numbers, and overlap requirements.
        """
        chunks: list[ChunkItem] = []
        chunk_index = 0

        for block in blocks:
            raw_text = block.content.strip()
            if not raw_text:
                continue

            block_tokens = self.estimate_tokens(raw_text)

            # If the block fits comfortably in one chunk
            if block_tokens <= self.chunk_size:
                chunks.append(
                    ChunkItem(
                        chunk_index=chunk_index,
                        content=raw_text,
                        token_count=block_tokens,
                        page_number=block.page_number,
                        section_heading=block.section_heading,
                        metadata=dict(block.metadata),
                    )
                )
                chunk_index += 1
            else:
                # Split large block by paragraphs or sentences with sliding window overlap
                sub_chunks = self._split_text_with_overlap(
                    text=raw_text,
                    target_tokens=self.chunk_size,
                    overlap_tokens=self.overlap,
                )
                for sub in sub_chunks:
                    if sub.strip():
                        chunks.append(
                            ChunkItem(
                                chunk_index=chunk_index,
                                content=sub.strip(),
                                token_count=self.estimate_tokens(sub),
                                page_number=block.page_number,
                                section_heading=block.section_heading,
                                metadata=dict(block.metadata),
                            )
                        )
                        chunk_index += 1

        return chunks

    def _split_text_with_overlap(
        self, text: str, target_tokens: int, overlap_tokens: int
    ) -> list[str]:
        """Split text by paragraphs or sentences with token overlap."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

        result: list[str] = []
        current_paras: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.estimate_tokens(para)
            if current_tokens + para_tokens > target_tokens and current_paras:
                # Emit chunk
                result.append("\n\n".join(current_paras))

                # Keep overlap paragraphs from end of current_paras
                overlap_buffer: list[str] = []
                overlap_count = 0
                for prev in reversed(current_paras):
                    prev_tokens = self.estimate_tokens(prev)
                    if overlap_count + prev_tokens <= overlap_tokens:
                        overlap_buffer.insert(0, prev)
                        overlap_count += prev_tokens
                    else:
                        break

                current_paras = overlap_buffer
                current_tokens = overlap_count

            current_paras.append(para)
            current_tokens += para_tokens

        if current_paras:
            result.append("\n\n".join(current_paras))

        return result
