"""
ServerGen AI — Image Document Parser (Native OCR).

Extracts text from image documents (.png, .jpg, .jpeg, .bmp, .webp, .tiff)
using native Windows OCR, generating structured blocks for RAG ingestion.
"""

from __future__ import annotations

import io
import logging

from PIL import Image

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument
from src.rag.parsers.pdf_parser import _run_ocr_on_image

logger = logging.getLogger("servergen.rag.parsers.image")


class ImageParser(BaseParser):
    @property
    def name(self) -> str:
        return "native_image_ocr_parser"

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            img = Image.open(io.BytesIO(content))
            width, height = img.size
        except Exception as exc:
            raise ValidationError(f"Invalid or unsupported image file: {exc}") from exc

        text = _run_ocr_on_image(content)
        title = filename.rsplit(".", 1)[0]
        warnings: list[str] = []

        if not text:
            text = (
                f"[Image Document: {filename} ({width}x{height} px) contains graphical "
                "content with no machine-readable text detected.]"
            )
            warnings.append("image_ocr_empty: No text detected in image.")
        else:
            warnings.append(f"image_ocr_applied: Extracted {len(text)} characters via native OCR.")

        block = ExtractedBlock(
            content=text,
            page_number=1,
            section_heading=f"Image: {title}",
            metadata={"width": width, "height": height, "format": img.format or "unknown"},
        )

        return ParsedDocument(
            blocks=[block],
            title=title,
            total_characters=len(text),
            parser_name=self.name,
            warnings=warnings,
        )
