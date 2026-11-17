"""
ServerGen AI — Microsoft Word DOCX Document Parser.

Extracts text paragraphs, section headings, and tabular records using python-docx.
"""

from __future__ import annotations

import io

from docx import Document as DocxDocument

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument


class DocxParser(BaseParser):
    @property
    def name(self) -> str:
        return "docx_document_parser"

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            doc = DocxDocument(io.BytesIO(content))
        except Exception as exc:
            raise ValidationError(f"Invalid or corrupt DOCX document: {exc}") from exc

        blocks: list[ExtractedBlock] = []
        current_heading: str | None = None
        current_paras: list[str] = []
        total_chars = 0
        doc_title = ""

        # Extract paragraphs with heading detection
        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            total_chars += len(text)
            style_name = p.style.name.lower() if p.style else ""

            if "heading 1" in style_name:
                if not doc_title:
                    doc_title = text
                if current_paras:
                    blocks.append(
                        ExtractedBlock(
                            content="\n\n".join(current_paras),
                            section_heading=current_heading,
                        )
                    )
                    current_paras = []
                current_heading = text
                current_paras.append(f"# {text}")
            elif "heading" in style_name:
                if current_paras:
                    blocks.append(
                        ExtractedBlock(
                            content="\n\n".join(current_paras),
                            section_heading=current_heading,
                        )
                    )
                    current_paras = []
                current_heading = text
                current_paras.append(f"## {text}")
            else:
                current_paras.append(text)

        if current_paras:
            blocks.append(
                ExtractedBlock(
                    content="\n\n".join(current_paras),
                    section_heading=current_heading,
                )
            )

        # Extract tables preserving tabular context
        for tbl_idx, table in enumerate(doc.tables, start=1):
            rows = table.rows
            if not rows:
                continue
            headers = [c.text.strip() for c in rows[0].cells]
            table_lines: list[str] = []
            for r_idx, row in enumerate(rows[1:], start=1):
                cells = []
                for c_idx, cell in enumerate(row.cells):
                    header = headers[c_idx] if c_idx < len(headers) else f"Col_{c_idx+1}"
                    c_text = cell.text.strip()
                    if c_text:
                        cells.append(f"{header}: {c_text}")
                if cells:
                    line = f"[Row {r_idx}] " + " | ".join(cells)
                    table_lines.append(line)
                    total_chars += len(line)

            if table_lines:
                blocks.append(
                    ExtractedBlock(
                        content="\n".join(table_lines),
                        section_heading=f"Table {tbl_idx} ({current_heading or 'Document Body'})",
                        metadata={"table_index": tbl_idx, "rows": len(table_lines)},
                    )
                )

        if not blocks or total_chars == 0:
            raise ValidationError("DOCX document contains no readable text or tables")

        return ParsedDocument(
            blocks=blocks,
            title=doc_title or filename.rsplit(".", 1)[0],
            total_characters=total_chars,
            parser_name=self.name,
        )
