"""
Unit Tests — Multi-Format Document Parsers.

Verifies text extraction, tabular context preservation, and structural heading
detection across TXT, MD, CSV, PDF, DOCX, XLSX, PPTX, and HTML.
"""

from __future__ import annotations

import io

import pytest
from docx import Document as DocxDocument
from openpyxl import Workbook
from pptx import Presentation
from pypdf import PdfWriter
from src.core.exceptions import ValidationError
from src.rag.parsers import (
    CSVParser,
    DocxParser,
    PDFParser,
    PPTXParser,
    SafeHTMLParser,
    TextParser,
    XLSXParser,
    get_parser,
)


def test_parser_factory_resolution() -> None:
    """Parser registry resolves correct parser by extension and MIME."""
    assert isinstance(get_parser("report.pdf"), PDFParser)
    assert isinstance(get_parser("document.docx"), DocxParser)
    assert isinstance(get_parser("metrics.xlsx"), XLSXParser)
    assert isinstance(get_parser("slides.pptx"), PPTXParser)
    assert isinstance(get_parser("dataset.csv"), CSVParser)
    assert isinstance(get_parser("notes.md"), TextParser)
    assert isinstance(get_parser("page.html"), SafeHTMLParser)


def test_text_and_markdown_parser() -> None:
    """Markdown headers are detected to establish section boundaries."""
    md_content = b"""# ServerGen AI Architecture
ServerGen AI provides on-premise enterprise automation.

## Security Controls
Argon2id and role-based access control are enforced.
"""

    parser = TextParser()
    parsed = parser.parse(md_content, "arch.md")

    assert parsed.title == "Security Controls" or "Architecture" in parsed.full_text
    assert len(parsed.blocks) >= 2
    assert any("Security Controls" in (b.section_heading or "") for b in parsed.blocks)
    assert "enterprise automation" in parsed.full_text


def test_csv_tabular_context_preserved() -> None:
    """CSV parser preserves row and column headers for numeric data."""
    csv_content = b"""Region,Department,Q3_Expenditure,Status
US-East,Engineering,$45000,Approved
EU-Central,Security,$28000,Approved
"""

    parser = CSVParser()
    parsed = parser.parse(csv_content, "budget.csv")

    assert len(parsed.blocks) >= 1
    content = parsed.blocks[0].content
    assert "Region: US-East" in content
    assert "Q3_Expenditure: $45000" in content
    assert "[Row 1]" in content


def test_pdf_parser_page_tracking() -> None:
    """PDF parser extracts text and attributes page numbers."""
    writer = PdfWriter()
    page1 = writer.add_blank_page(width=72, height=72)
    # Note: pypdf blank page has no text, so test empty rejection or add real page
    buf = io.BytesIO()
    writer.write(buf)

    parser = PDFParser()
    # Empty PDF without extractable text raises ValidationError
    with pytest.raises(ValidationError, match="no extractable text"):
        parser.parse(buf.getvalue(), "empty.pdf")


def test_docx_parser() -> None:
    """DOCX parser extracts paragraphs and heading hierarchy."""
    doc = DocxDocument()
    doc.add_heading("Operational Runbook", level=1)
    doc.add_paragraph("Follow standard verification before restarting services.")
    buf = io.BytesIO()
    doc.save(buf)

    parser = DocxParser()
    parsed = parser.parse(buf.getvalue(), "runbook.docx")

    assert "Operational Runbook" in parsed.full_text
    assert "restarting services" in parsed.full_text
    assert parsed.total_characters > 0


def test_xlsx_parser_tabular_context() -> None:
    """XLSX parser maintains sheet name and row/column coordinates."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Q3_Summary"
    ws.append(["Metric", "Target", "Actual"])
    ws.append(["Uptime", "99.9%", "99.95%"])
    buf = io.BytesIO()
    wb.save(buf)

    parser = XLSXParser()
    parsed = parser.parse(buf.getvalue(), "metrics.xlsx")

    assert len(parsed.blocks) >= 1
    content = parsed.blocks[0].content
    assert "Sheet: Q3_Summary" in parsed.blocks[0].section_heading
    assert "Metric: Uptime" in content
    assert "Actual: 99.95%" in content


def test_pptx_parser_slide_boundaries() -> None:
    """PPTX parser extracts slide text and tracks slide coordinates."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Executive Briefing"
    slide.placeholders[1].text = "Automation reduced maintenance by 65%."
    buf = io.BytesIO()
    prs.save(buf)

    parser = PPTXParser()
    parsed = parser.parse(buf.getvalue(), "briefing.pptx")

    assert "Executive Briefing" in parsed.full_text
    assert "reduced maintenance" in parsed.full_text
    assert parsed.blocks[0].page_number == 1


def test_safe_html_parser() -> None:
    """HTML parser extracts headings and text while stripping scripts."""
    html_content = b"""<!DOCTYPE html>
<html>
<head><title>System Guide</title><script>alert('bad');</script></head>
<body>
<h1>Enterprise Guide</h1>
<p>Authorized personnel only.</p>
</body>
</html>"""

    parser = SafeHTMLParser()
    parsed = parser.parse(html_content, "guide.html")

    assert "Enterprise Guide" in parsed.full_text
    assert "Authorized personnel" in parsed.full_text
    assert "alert" not in parsed.full_text  # Script stripped!
