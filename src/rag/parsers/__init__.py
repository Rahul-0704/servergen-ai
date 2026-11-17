"""
ServerGen AI — Multi-Format Document Parser Registry.
"""

from __future__ import annotations

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument
from src.rag.parsers.csv_parser import CSVParser
from src.rag.parsers.docx_parser import DocxParser
from src.rag.parsers.html_parser import SafeHTMLParser
from src.rag.parsers.image_parser import ImageParser
from src.rag.parsers.pdf_parser import PDFParser
from src.rag.parsers.pptx_parser import PPTXParser
from src.rag.parsers.text_parser import TextParser
from src.rag.parsers.xlsx_parser import XLSXParser

_IMAGE_PARSER = ImageParser()

_PARSERS: dict[str, BaseParser] = {
    "txt": TextParser(),
    "md": TextParser(),
    "markdown": TextParser(),
    "csv": CSVParser(),
    "pdf": PDFParser(),
    "docx": DocxParser(),
    "xlsx": XLSXParser(),
    "pptx": PPTXParser(),
    "html": SafeHTMLParser(),
    "htm": SafeHTMLParser(),
    "png": _IMAGE_PARSER,
    "jpg": _IMAGE_PARSER,
    "jpeg": _IMAGE_PARSER,
    "bmp": _IMAGE_PARSER,
    "webp": _IMAGE_PARSER,
    "tiff": _IMAGE_PARSER,
    "tif": _IMAGE_PARSER,
}


def get_parser(filename: str, mime_type: str | None = None) -> BaseParser:
    """Return the designated parser for a given filename or MIME type."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _PARSERS:
        return _PARSERS[ext]

    if mime_type:
        mime_lower = mime_type.lower()
        if "pdf" in mime_lower:
            return _PARSERS["pdf"]
        if "wordprocessingml" in mime_lower or "msword" in mime_lower:
            return _PARSERS["docx"]
        if "spreadsheetml" in mime_lower or "excel" in mime_lower:
            return _PARSERS["xlsx"]
        if "presentationml" in mime_lower or "powerpoint" in mime_lower:
            return _PARSERS["pptx"]
        if "csv" in mime_lower:
            return _PARSERS["csv"]
        if "html" in mime_lower:
            return _PARSERS["html"]
        if "text" in mime_lower:
            return _PARSERS["txt"]
        if "image/" in mime_lower:
            return _IMAGE_PARSER

    supported = ", ".join(sorted(_PARSERS.keys()))
    raise ValidationError(f"No parser available for '{filename}'. Supported formats: {supported}")


__all__ = [
    "BaseParser",
    "CSVParser",
    "DocxParser",
    "ExtractedBlock",
    "ImageParser",
    "PDFParser",
    "PPTXParser",
    "ParsedDocument",
    "SafeHTMLParser",
    "TextParser",
    "get_parser",
]
