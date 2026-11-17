"""
Tests for PDF and PowerPoint (PPTX) Generation Subsystem and Tools.
"""

from __future__ import annotations

import pytest

from src.services.docgen_service import DocumentGeneratorService
from src.tools.docgen import PDFGeneratorTool, PresentationGeneratorTool


def test_heuristic_deck_generation(tmp_path):
    svc = DocumentGeneratorService(storage_dir=tmp_path)
    deck = svc._heuristic_deck_fallback("Enterprise Cloud Security", num_slides=4, classification="CONFIDENTIAL")
    assert deck.title == "Enterprise Cloud Security"
    assert deck.classification == "CONFIDENTIAL"
    assert len(deck.slides) == 4
    assert deck.slides[0].category == "STRATEGY"


def test_pptx_rendering(tmp_path):
    svc = DocumentGeneratorService(storage_dir=tmp_path)
    deck = svc._heuristic_deck_fallback("DevOps Runbook", num_slides=3, classification="INTERNAL")
    output_path, meta = svc.render_presentation(deck)

    assert output_path.exists()
    assert output_path.suffix == ".pptx"
    assert meta.format == "pptx"
    assert meta.file_size > 0
    assert meta.slide_or_page_count == 3
    assert "/api/v1/generate/download/" in meta.download_url


def test_pdf_rendering(tmp_path):
    svc = DocumentGeneratorService(storage_dir=tmp_path)
    doc_data = svc._heuristic_report_fallback("Audit Compliance Assessment", classification="RESTRICTED")
    output_path, meta = svc.render_pdf(doc_data)

    assert output_path.exists()
    assert output_path.suffix == ".pdf"
    assert meta.format == "pdf"
    assert meta.file_size > 0
    assert "/api/v1/generate/download/" in meta.download_url


def test_file_lookup_and_traversal_protection(tmp_path):
    svc = DocumentGeneratorService(storage_dir=tmp_path)
    deck = svc._heuristic_deck_fallback("Test Deck", num_slides=3, classification="PUBLIC")
    output_path, meta = svc.render_presentation(deck)

    # Valid lookup
    found = svc.get_file_path(meta.filename)
    assert found is not None
    assert found == output_path

    # Prefix lookup
    found_prefix = svc.get_file_path(meta.file_id)
    assert found_prefix is not None

    # Traversal attempt should be safely blocked / return None
    traversal = svc.get_file_path("../../Windows/System32/calc.exe")
    assert traversal is None


@pytest.mark.asyncio
async def test_tools_execution(tmp_path):
    svc = DocumentGeneratorService(storage_dir=tmp_path)
    pdf_tool = PDFGeneratorTool(service=svc)
    assert pdf_tool.metadata.name == "pdf_generator"
    assert pdf_tool.metadata.allows_filesystem is False

    pdf_res = await pdf_tool.execute({"prompt": "Quarterly Security Review", "classification": "INTERNAL"})
    assert pdf_res.success is True
    assert "Download Link:" in pdf_res.output

    ppt_tool = PresentationGeneratorTool(service=svc)
    assert ppt_tool.metadata.name == "presentation_generator"
    assert ppt_tool.metadata.allows_filesystem is False

    ppt_res = await ppt_tool.execute({"prompt": "Zero Trust Migration", "num_slides": 4})
    assert ppt_res.success is True
    assert "Download Link:" in ppt_res.output
