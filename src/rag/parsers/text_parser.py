"""
ServerGen AI — Plaintext & Markdown Parser.

Extracts text while detecting Markdown headers to establish section contexts.
"""

from __future__ import annotations

import re

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument


class TextParser(BaseParser):
    @property
    def name(self) -> str:
        return "text_markdown_parser"

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        # Attempt UTF-8 with fallback to latin-1
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as exc:
                raise ValidationError(f"Unable to decode text file: {exc}") from exc

        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            raise ValidationError("File contains no readable text")

        lines = text.split("\n")
        blocks: list[ExtractedBlock] = []
        current_heading: str | None = None
        current_lines: list[str] = []

        header_re = re.compile(r"^(#{1,6})\s+(.+)$")

        for line in lines:
            h_match = header_re.match(line.strip())
            if h_match:
                # Flush existing buffer
                if current_lines:
                    chunk_text = "\n".join(current_lines).strip()
                    if chunk_text:
                        blocks.append(
                            ExtractedBlock(
                                content=chunk_text,
                                section_heading=current_heading,
                            )
                        )
                    current_lines = []
                current_heading = h_match.group(2).strip()
                current_lines.append(line)
            else:
                current_lines.append(line)

        if current_lines:
            chunk_text = "\n".join(current_lines).strip()
            if chunk_text:
                blocks.append(
                    ExtractedBlock(
                        content=chunk_text,
                        section_heading=current_heading,
                    )
                )

        if not blocks:
            blocks.append(ExtractedBlock(content=text))

        doc_title = current_heading or filename.rsplit(".", 1)[0]
        return ParsedDocument(
            blocks=blocks,
            title=doc_title,
            total_characters=len(text),
            parser_name=self.name,
        )
