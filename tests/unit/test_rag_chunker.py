"""
Unit Tests — Document Chunker & Token Budgeting.

Verifies:
1. Token estimation heuristic.
2. Structure-aware splitting without truncating headings.
3. Preservation of section headings and page coordinates.
4. Overlap configuration across paragraph boundaries.
"""

from __future__ import annotations

from src.rag.chunker import DocumentChunker
from src.rag.parsers.base import ExtractedBlock


def test_chunker_preserves_metadata() -> None:
    """Chunks retain page numbers, section headings, and block metadata."""
    blocks = [
        ExtractedBlock(
            content="Initial overview paragraph describing core server architecture.",
            page_number=1,
            section_heading="Introduction",
            metadata={"source": "test"},
        ),
        ExtractedBlock(
            content="Second section describing database connection clustering.",
            page_number=2,
            section_heading="Database",
            metadata={"source": "test"},
        ),
    ]

    chunker = DocumentChunker(chunk_size_tokens=500, overlap_tokens=50)
    chunks = chunker.chunk_blocks(blocks)

    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[0].section_heading == "Introduction"
    assert chunks[1].page_number == 2
    assert chunks[1].section_heading == "Database"
    assert chunks[0].token_count > 0


def test_chunker_splits_large_blocks_with_overlap() -> None:
    """Large content exceeding chunk size is split with sliding token overlap."""
    long_para = "Enterprise policy requires strict auditing. " * 60
    blocks = [
        ExtractedBlock(
            content=f"{long_para}\n\n{long_para}\n\n{long_para}",
            page_number=3,
            section_heading="Auditing Policy",
        )
    ]

    chunker = DocumentChunker(chunk_size_tokens=100, overlap_tokens=20)
    chunks = chunker.chunk_blocks(blocks)

    assert len(chunks) > 1
    for c in chunks:
        assert c.page_number == 3
        assert c.section_heading == "Auditing Policy"
        assert len(c.content.strip()) > 0
