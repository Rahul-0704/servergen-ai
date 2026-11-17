"""
ServerGen AI — Secure HTML Document Parser.

Extracts text content and headings while stripping scripts, styles, and unsafe
elements using Python's standard html.parser. Never executes client scripts.
"""

from __future__ import annotations

from html.parser import HTMLParser

from src.core.exceptions import ValidationError
from src.rag.parsers.base import BaseParser, ExtractedBlock, ParsedDocument


class _SafeHTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[ExtractedBlock] = []
        self._current_text: list[str] = []
        self._current_heading: str | None = None
        self._doc_title: str = ""
        self._in_ignored_tag = False
        self._in_title = False
        self._in_heading = False
        self._ignored_tags = {"script", "style", "noscript", "svg", "iframe", "object"}
        self._heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._ignored_tags:
            self._in_ignored_tag = True
        elif tag_lower == "title":
            self._in_title = True
        elif tag_lower in self._heading_tags:
            self._flush()
            self._in_heading = True

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._ignored_tags:
            self._in_ignored_tag = False
        elif tag_lower == "title":
            self._in_title = False
        elif tag_lower in self._heading_tags:
            self._in_heading = False
        elif tag_lower in {"p", "div", "section", "article", "tr", "li"}:
            self._current_text.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_ignored_tag:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        if self._in_title and not self._doc_title:
            self._doc_title = cleaned
        elif self._in_heading:
            self._current_heading = cleaned
            self._current_text.append(f"## {cleaned}\n")
        else:
            self._current_text.append(cleaned + " ")

    def _flush(self) -> None:
        content = "".join(self._current_text).strip()
        if content:
            self.blocks.append(
                ExtractedBlock(
                    content=content,
                    section_heading=self._current_heading,
                )
            )
            self._current_text = []

    def finalize(self) -> None:
        self._flush()


class SafeHTMLParser(BaseParser):
    @property
    def name(self) -> str:
        return "safe_html_parser"

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            html_text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                html_text = content.decode("latin-1")
            except Exception as exc:
                raise ValidationError(f"Unable to decode HTML: {exc}") from exc

        extractor = _SafeHTMLTextExtractor()
        try:
            extractor.feed(html_text)
            extractor.finalize()
        except Exception as exc:
            raise ValidationError(f"Invalid or malformed HTML: {exc}") from exc

        if not extractor.blocks:
            raise ValidationError("HTML document contains no extractable body text")

        total_chars = sum(len(b.content) for b in extractor.blocks)
        return ParsedDocument(
            blocks=extractor.blocks,
            title=extractor._doc_title or filename.rsplit(".", 1)[0],
            total_characters=total_chars,
            parser_name=self.name,
        )
