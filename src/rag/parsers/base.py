"""
ServerGen AI — Base Document Parser Interfaces.

Defines the contract for multi-format text extraction, structural section
discovery, page number tracking, and tabular context preservation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedBlock:
    """A structurally bounded extracted block of text."""

    content: str
    page_number: int | None = None
    section_heading: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Output of a document parser run."""

    blocks: list[ExtractedBlock]
    title: str = ""
    total_characters: int = 0
    parser_name: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(b.content for b in self.blocks if b.content.strip())


class BaseParser(ABC):
    """Abstract base class for all file format extractors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the parser implementation."""

    @abstractmethod
    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        """Extract structured blocks from raw file bytes."""
