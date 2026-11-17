"""
ServerGen AI — PDF and Presentation Generation Controlled Tools.

Exposes controlled, sandboxed tools for generating executive PDF reports and
widescreen 16:9 PowerPoint (PPTX) presentations using local on-premise AI models.
"""

from __future__ import annotations

import logging
from typing import Any

from src.services.docgen_service import DocumentGeneratorService
from src.tools.base import Tool, ToolMetadata, ToolResult

logger = logging.getLogger("servergen.tools.docgen")


class PDFGeneratorTool(Tool):
    """Generates an executive corporate PDF report on-premise without cloud egress."""

    def __init__(self, service: DocumentGeneratorService | None = None) -> None:
        self.service = service or DocumentGeneratorService()

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="pdf_generator",
            description="Generate a publication-ready corporate PDF report from topic or prompt",
            required_permission="ai.execute",
            potential_impact="low",
            allows_shell=False,
            allows_sql=False,
            allows_filesystem=False,
        )

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        prompt = str(parameters.get("prompt") or parameters.get("topic") or "").strip()
        if not prompt:
            return ToolResult(
                tool=self.metadata.name,
                success=False,
                error="Parameter 'prompt' or 'topic' is required.",
            )

        classification = str(parameters.get("classification", "INTERNAL")).upper()
        context = str(parameters.get("context", "")).strip()

        try:
            _, _, meta = await self.service.generate_pdf_from_prompt(
                prompt=prompt,
                classification=classification,
                context=context,
            )
            return ToolResult(
                tool=self.metadata.name,
                success=True,
                output=(
                    f"Successfully generated executive PDF report '{meta.title}' ({meta.file_size} bytes).\n"
                    f"File ID: {meta.file_id}\n"
                    f"Download Link: {meta.download_url}\n"
                    f"Summary: {meta.summary}"
                ),
            )
        except Exception as exc:
            logger.error("PDF generation failed: %s", exc)
            return ToolResult(
                tool=self.metadata.name,
                success=False,
                error=f"PDF generation failed: {exc}",
            )


class PresentationGeneratorTool(Tool):
    """Generates a professional 16:9 PowerPoint presentation deck on-premise."""

    def __init__(self, service: DocumentGeneratorService | None = None) -> None:
        self.service = service or DocumentGeneratorService()

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="presentation_generator",
            description="Generate a widescreen 16:9 PowerPoint presentation deck (PPTX) from topic",
            required_permission="ai.execute",
            potential_impact="low",
            allows_shell=False,
            allows_sql=False,
            allows_filesystem=False,
        )

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        prompt = str(parameters.get("prompt") or parameters.get("topic") or "").strip()
        if not prompt:
            return ToolResult(
                tool=self.metadata.name,
                success=False,
                error="Parameter 'prompt' or 'topic' is required.",
            )

        num_slides = int(parameters.get("num_slides", 5))
        classification = str(parameters.get("classification", "INTERNAL")).upper()
        context = str(parameters.get("context", "")).strip()

        try:
            _, _, meta = await self.service.generate_presentation_from_prompt(
                prompt=prompt,
                num_slides=num_slides,
                classification=classification,
                context=context,
            )
            return ToolResult(
                tool=self.metadata.name,
                success=True,
                output=(
                    f"Successfully generated {meta.slide_or_page_count}-slide PowerPoint presentation '{meta.title}' "
                    f"({meta.file_size} bytes).\n"
                    f"File ID: {meta.file_id}\n"
                    f"Download Link: {meta.download_url}\n"
                    f"Summary: {meta.summary}"
                ),
            )
        except Exception as exc:
            logger.error("Presentation generation failed: %s", exc)
            return ToolResult(
                tool=self.metadata.name,
                success=False,
                error=f"Presentation generation failed: {exc}",
            )
