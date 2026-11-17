"""
ServerGen AI — Structured CSV Parser.

Preserves column headers and tabular context for each row so that numeric
and enterprise values retain their semantics during retrieval.
"""

from __future__ import annotations

import csv
import io

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument


class CSVParser(BaseParser):
    @property
    def name(self) -> str:
        return "csv_tabular_parser"

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as exc:
                raise ValidationError(f"Unable to decode CSV file: {exc}") from exc

        if not text.strip():
            raise ValidationError("CSV document is empty")

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise ValidationError("CSV document contains no tabular rows")

        headers = [h.strip() for h in rows[0]]
        if not any(headers):
            headers = [f"Col_{i+1}" for i in range(len(rows[0]))]

        blocks: list[ExtractedBlock] = []
        batch_rows: list[str] = []
        batch_size = 15
        total_chars = 0

        for row_idx, row in enumerate(rows[1:], start=1):
            if not any(c.strip() for c in row):
                continue
            cells = []
            for col_idx, cell_val in enumerate(row):
                header = headers[col_idx] if col_idx < len(headers) else f"Col_{col_idx+1}"
                val = cell_val.strip()
                if val:
                    cells.append(f"{header}: {val}")
            if cells:
                line = f"[Row {row_idx}] " + " | ".join(cells)
                batch_rows.append(line)
                total_chars += len(line)

            if len(batch_rows) >= batch_size:
                block_content = "\n".join(batch_rows)
                start_r = row_idx - len(batch_rows) + 1
                heading = f"Tabular Data: {filename} (Rows {start_r}-{row_idx})"
                blocks.append(
                    ExtractedBlock(
                        content=block_content,
                        section_heading=heading,
                        metadata={"row_count": len(batch_rows)},
                    )
                )
                batch_rows = []

        if batch_rows:
            block_content = "\n".join(batch_rows)
            blocks.append(
                ExtractedBlock(
                    content=block_content,
                    section_heading=f"Tabular Data: {filename} (Final Rows)",
                    metadata={"row_count": len(batch_rows)},
                )
            )

        if not blocks:
            raise ValidationError("CSV document contains only empty rows")

        return ParsedDocument(
            blocks=blocks,
            title=f"Dataset: {filename}",
            total_characters=total_chars,
            parser_name=self.name,
        )
