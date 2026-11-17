"""
ServerGen AI — Microsoft Excel XLSX Parser.

Extracts spreadsheet sheets, preserving sheet names, column headers, and
row coordinates to maintain business and numeric context.
"""

from __future__ import annotations

import io

from openpyxl import load_workbook

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument


class XLSXParser(BaseParser):
    @property
    def name(self) -> str:
        return "openpyxl_spreadsheet_parser"

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        except Exception as exc:
            raise ValidationError(f"Invalid or corrupt XLSX document: {exc}") from exc

        blocks: list[ExtractedBlock] = []
        total_chars = 0
        batch_size = 15

        try:
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                rows_iter = sheet.iter_rows(values_only=True)
                headers: list[str] = []
                batch_rows: list[str] = []

                # Find first non-empty row as header
                for row in rows_iter:
                    if row and any(v is not None and str(v).strip() for v in row):
                        headers = [
                            str(v).strip() if v is not None else f"Col_{i+1}"
                            for i, v in enumerate(row)
                        ]
                        break

                if not headers:
                    continue

                for row_idx, row in enumerate(rows_iter, start=2):
                    if not row or not any(v is not None and str(v).strip() for v in row):
                        continue
                    cells = []
                    for c_idx, val in enumerate(row):
                        if val is not None and str(val).strip():
                            header = headers[c_idx] if c_idx < len(headers) else f"Col_{c_idx+1}"
                            cells.append(f"{header}: {str(val).strip()}")
                    if cells:
                        line = f"[Sheet: {sheet_name}, Row {row_idx}] " + " | ".join(cells)
                        batch_rows.append(line)
                        total_chars += len(line)

                    if len(batch_rows) >= batch_size:
                        blocks.append(
                            ExtractedBlock(
                                content="\n".join(batch_rows),
                                section_heading=f"Sheet: {sheet_name}",
                                metadata={"sheet": sheet_name, "row_count": len(batch_rows)},
                            )
                        )
                        batch_rows = []

                if batch_rows:
                    blocks.append(
                        ExtractedBlock(
                            content="\n".join(batch_rows),
                            section_heading=f"Sheet: {sheet_name}",
                            metadata={"sheet": sheet_name, "row_count": len(batch_rows)},
                        )
                    )
        finally:
            wb.close()

        if not blocks or total_chars == 0:
            raise ValidationError("XLSX workbook contains no readable data rows")

        return ParsedDocument(
            blocks=blocks,
            title=f"Spreadsheet: {filename}",
            total_characters=total_chars,
            parser_name=self.name,
        )
