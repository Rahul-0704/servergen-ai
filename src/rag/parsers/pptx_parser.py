"""
ServerGen AI — Microsoft PowerPoint PPTX Parser.

Extracts slides, slide titles, notes, and shape text using python-pptx,
preserving presentation slide boundaries.
"""

from __future__ import annotations

import io

from pptx import Presentation

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument


class PPTXParser(BaseParser):
    @property
    def name(self) -> str:
        return "pptx_presentation_parser"

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            prs = Presentation(io.BytesIO(content))
        except Exception as exc:
            raise ValidationError(f"Invalid or corrupt PPTX presentation: {exc}") from exc

        blocks: list[ExtractedBlock] = []
        total_chars = 0
        doc_title = ""

        for slide_idx, slide in enumerate(prs.slides, start=1):
            slide_title = ""
            slide_texts: list[str] = []

            # Check if slide has a title shape
            if slide.shapes.title and slide.shapes.title.text:
                slide_title = slide.shapes.title.text.strip()
                if not doc_title and slide_idx == 1:
                    doc_title = slide_title

            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        txt = para.text.strip()
                        if txt and txt != slide_title:
                            slide_texts.append(txt)

            if slide_title or slide_texts:
                content_lines = []
                if slide_title:
                    content_lines.append(f"## {slide_title}")
                content_lines.extend(slide_texts)
                slide_body = "\n".join(content_lines)
                total_chars += len(slide_body)

                heading = f"Slide {slide_idx}"
                if slide_title:
                    heading += f": {slide_title}"

                blocks.append(
                    ExtractedBlock(
                        content=slide_body,
                        page_number=slide_idx,
                        section_heading=heading,
                        metadata={"slide": slide_idx, "title": slide_title},
                    )
                )

        if not blocks or total_chars == 0:
            raise ValidationError("PPTX presentation contains no readable slide content")

        return ParsedDocument(
            blocks=blocks,
            title=doc_title or filename.rsplit(".", 1)[0],
            total_characters=total_chars,
            parser_name=self.name,
        )
