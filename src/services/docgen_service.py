"""
ServerGen AI — Enterprise PDF & PowerPoint (PPTX) Generation Service.

Provides automated, local-LLM powered synthesis of publication-ready executive PDF
reports and modern 16:9 widescreen PowerPoint presentations. Uses on-premise
local models (Ollama llama3.2:3b) to draft structured content, and renders durable
binary files without any external cloud egress.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import pptx
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
from src.ai.providers.base import LLMRequest
from src.ai.providers.ollama_provider import OllamaProvider
from src.core.config import get_settings

logger = logging.getLogger("servergen.docgen")


# ── Data Models ─────────────────────────────────────────────────────────────


class SlideContent(BaseModel):
    title: str = Field(..., description="Slide headline")
    category: str = Field(default="OVERVIEW", description="Category or topic tag")
    bullets: list[str] = Field(default_factory=list, description="Core bullet points")
    key_takeaway: str = Field(default="", description="Key takeaway or stat")
    notes: str = Field(default="", description="Presenter speaker notes")


class PresentationDeck(BaseModel):
    title: str = Field(..., description="Presentation title")
    subtitle: str = Field(default="", description="Subtitle or purpose")
    author: str = Field(default="ServerGen AI", description="Author or generating system")
    classification: str = Field(default="INTERNAL", description="Security classification")
    slides: list[SlideContent] = Field(default_factory=list, description="Slide list")


class ReportSection(BaseModel):
    heading: str = Field(..., description="Section title")
    content: str = Field(default="", description="Section narrative explanation")
    bullet_points: list[str] = Field(default_factory=list, description="Key points")
    key_metric: str = Field(default="", description="Key metric or observation")


class ReportDocument(BaseModel):
    title: str = Field(..., description="Document title")
    subtitle: str = Field(default="", description="Document subtitle")
    classification: str = Field(default="INTERNAL", description="Classification level")
    author: str = Field(default="ServerGen AI Local Engine", description="Author")
    executive_summary: str = Field(default="", description="High level summary")
    sections: list[ReportSection] = Field(default_factory=list, description="Document sections")
    recommendations: list[str] = Field(default_factory=list, description="Actionable recommendations")


class GeneratedFileMeta(BaseModel):
    file_id: str
    filename: str
    format: str
    file_size: int
    title: str
    summary: str
    download_url: str
    created_at: str
    slide_or_page_count: int = 0


# ── ReportLab Numbered Canvas for Dynamic Page Count ────────────────────────


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically inject 'Page X of Y' in the PDF footer."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:  # noqa: N802
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Top border line for footer
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(40, 36, letter[0] - 40, 36)

        # Left label and right page number
        self.drawString(40, 24, "ServerGen AI — Enterprise Document Automation (On-Premise)")
        self.drawRightString(
            letter[0] - 40,
            24,
            f"Page {self._pageNumber} of {page_count}",
        )
        self.restoreState()


# ── Main Generator Service ──────────────────────────────────────────────────


class DocumentGeneratorService:
    """
    Comprehensive document generation engine.
    Orchestrates local LLM structuring, ReportLab PDF rendering, and PPTX generation.
    """

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        settings = get_settings()
        self.storage_dir = Path(
            storage_dir or getattr(settings, "GENERATED_STORAGE_DIR", "storage/generated")
        ).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.storage_dir / "index_meta.json"
        self._ensure_meta_index()

    def _ensure_meta_index(self) -> None:
        if not self.metadata_file.exists():
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _save_meta(self, meta: GeneratedFileMeta) -> None:
        try:
            records = self.list_generated_files()
            # Prepend new item
            records = [r for r in records if r.file_id != meta.file_id]
            records.insert(0, meta)
            # Retain last 100 items
            records = records[:100]
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in records], f, indent=2)
        except Exception as e:
            logger.warning("Failed to update generated index_meta.json: %s", e)

    def list_generated_files(self) -> list[GeneratedFileMeta]:
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, encoding="utf-8") as f:
                    data = json.load(f)
                    return [GeneratedFileMeta(**item) for item in data]
        except Exception as e:
            logger.warning("Error reading index_meta.json: %s", e)
        return []

    def get_file_path(self, file_id_or_name: str) -> Path | None:
        """Resolve a generated file securely preventing path traversal."""
        clean = os.path.basename(file_id_or_name.strip())
        # Try direct match
        target = (self.storage_dir / clean).resolve()
        if target.is_file() and target.is_relative_to(self.storage_dir):
            return target

        # Try prefix match by file_id
        for candidate in self.storage_dir.iterdir():
            if candidate.is_file() and candidate.name.startswith(clean):
                if candidate.is_relative_to(self.storage_dir):
                    return candidate
        return None

    # ── Presentation (PPTX) Generation ──────────────────────────────────────

    async def generate_presentation_from_prompt(
        self,
        prompt: str,
        num_slides: int = 5,
        context: str = "",
        classification: str = "INTERNAL",
        model: str | None = None,
    ) -> tuple[PresentationDeck, Path, GeneratedFileMeta]:
        """
        Drafts a structured presentation using local Ollama model, then compiles to PPTX.
        """
        num_slides = max(3, min(num_slides, 12))
        settings = get_settings()
        provider = OllamaProvider()
        active_model = model or settings.DEFAULT_MODEL

        system_instruction = (
            "You are an expert executive presentation strategist and visual communications director. "
            "Your goal is to transform user prompts into high-impact, professional PowerPoint slide decks. "
            "You MUST output strictly valid JSON matching the requested structure, with zero commentary or markdown code blocks."
        )

        user_content = f"""USER TOPIC / REQUEST:
{prompt}

OPTIONAL REFERENCE CONTEXT:
{context[:2500] if context else 'None provided.'}

INSTRUCTIONS:
Create a compelling, professional {num_slides}-slide presentation deck.
The JSON must follow this exact schema:
{{
  "title": "Clear, High-Impact Deck Title",
  "subtitle": "Informative Deck Subtitle or Purpose",
  "author": "ServerGen AI Local Engine",
  "classification": "{classification.upper()}",
  "slides": [
    {{
      "title": "Slide Headline",
      "category": "CATEGORY TAG (e.g., ARCHITECTURE, STRATEGY, RISK)",
      "bullets": [
        "Concise, high-density point 1 with actionable insight",
        "Point 2 explaining technical or operational mechanism",
        "Point 3 covering governance, performance, or next step"
      ],
      "key_takeaway": "One-line bold takeaway or crucial metric",
      "notes": "Speaker talking points for this slide"
    }}
  ]
}}
Provide exactly {num_slides} slides in the slides array.
First slide after title should serve as Executive Overview/Agenda.
Last slide should serve as Summary & Strategic Next Steps.
Return ONLY valid JSON.
"""

        deck_data: PresentationDeck | None = None
        try:
            req = LLMRequest(
                model=active_model,
                prompt=user_content,
                system_prompt=system_instruction,
                max_tokens=900,
                temperature=0.3,
            )
            response = await asyncio.wait_for(provider.generate(req), timeout=30.0)
            deck_data = self._parse_deck_json(response.content)
        except Exception as exc:
            logger.warning("Local LLM presentation generation warning: %s. Using heuristic synthesizer.", exc)

        if not deck_data or not deck_data.slides:
            deck_data = self._heuristic_deck_fallback(prompt, num_slides, classification)

        file_id = str(uuid.uuid4())[:12]
        path, meta = self.render_presentation(deck_data, file_id=file_id)
        return deck_data, path, meta

    def _parse_deck_json(self, raw_output: str) -> PresentationDeck | None:
        """Extract and parse PresentationDeck JSON with robust markdown stripping."""
        cleaned = raw_output.strip()
        # Remove markdown code fences if present
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
            else:
                cleaned = re.sub(r"^```[a-z]*\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)

        cleaned = cleaned.strip()
        # Find first '{' and last '}'
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            json_str = cleaned[start : end + 1]
            try:
                parsed = json.loads(json_str)
                return PresentationDeck(**parsed)
            except Exception:
                pass
        return None

    def _heuristic_deck_fallback(
        self, prompt: str, num_slides: int, classification: str
    ) -> PresentationDeck:
        """Constructs a clean, logically sound slide deck when LLM returns unstructured text."""
        clean_title = prompt.split("\n")[0][:60].strip() or "Executive Project Brief"
        slides = [
            SlideContent(
                title="Executive Overview & Objectives",
                category="STRATEGY",
                bullets=[
                    f"Core Objective: Address '{clean_title}' with structured operational precision.",
                    "Establish zero-trust boundaries and verified security postures across all workflows.",
                    "Maximize efficiency while maintaining rigorous governance and auditability.",
                ],
                key_takeaway="Align technical capabilities directly with verified enterprise compliance.",
                notes="Introduce primary stakeholder objectives and scope.",
            ),
            SlideContent(
                title="Current Architecture & Technical Analysis",
                category="ARCHITECTURE",
                bullets=[
                    "On-premise execution isolated from external public cloud egress.",
                    "Role-Based Access Control enforcing granular user clearances.",
                    "Vector retrieval combined with deterministic policy checks.",
                ],
                key_takeaway="Zero data leakage guaranteed through verified localized boundaries.",
                notes="Review architectural components and operational safety mechanisms.",
            ),
            SlideContent(
                title="Implementation Roadmap & Best Practices",
                category="OPERATIONS",
                bullets=[
                    "Phase 1: Baseline deployment and automated role entitlement checks.",
                    "Phase 2: Full document ingestion, indexing, and vector synchronization.",
                    "Phase 3: Continuous audit verification with SHA-256 tamper-evident ledgers.",
                ],
                key_takeaway="Predictable rollout supported by continuous automated verification.",
                notes="Emphasize governance controls and incremental deployment milestones.",
            ),
        ]

        if num_slides >= 4:
            slides.append(
                SlideContent(
                    title="Risk Management & Dual-Custody Controls",
                    category="GOVERNANCE",
                    bullets=[
                        "High-risk operational tasks require dual-custody managerial sign-off.",
                        "All queries and model responses logged to cryptographic audit ledger.",
                        "Clear separation between Viewer, Analyst, Operator, and Administrator roles.",
                    ],
                    key_takeaway="No critical mutation can occur without verified authorization.",
                    notes="Highlight regulatory adherence and managerial control.",
                )
            )

        if num_slides >= 5:
            slides.append(
                SlideContent(
                    title="Summary & Next Steps",
                    category="SUMMARY",
                    bullets=[
                        "Validate local model performance and document indexing status.",
                        "Train departmental users on role-specific query interfaces.",
                        "Review daily audit trail logs to maintain zero compliance drift.",
                    ],
                    key_takeaway="Enterprise readiness achieved through automation, security, and verification.",
                    notes="Conclude and open floor for questions or approvals.",
                )
            )

        return PresentationDeck(
            title=clean_title,
            subtitle="Automated Presentation Deck — ServerGen AI",
            classification=classification,
            author="ServerGen AI Local Engine",
            slides=slides[:num_slides],
        )

    def render_presentation(
        self, deck: PresentationDeck, file_id: str | None = None
    ) -> tuple[Path, GeneratedFileMeta]:
        """
        Compiles a PresentationDeck Pydantic model into a modern 16:9 widescreen PPTX.
        """
        fid = file_id or str(uuid.uuid4())[:12]
        sanitized_title = re.sub(r"[^\w\-]", "_", deck.title)[:40].strip("_") or "presentation"
        filename = f"{fid}_{sanitized_title}.pptx"
        output_path = self.storage_dir / filename

        prs = pptx.Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank_layout = prs.slide_layouts[6]  # Blank layout

        # Corporate color palette
        c_navy = RGBColor(15, 23, 42)  # #0F172A
        c_blue = RGBColor(37, 99, 235)  # #2563EB
        c_slate = RGBColor(71, 85, 105)  # #475569
        c_light_bg = RGBColor(248, 250, 252)  # #F8FAFC
        c_card_bg = RGBColor(255, 255, 255)
        c_border = RGBColor(226, 232, 240)  # #E2E8F0
        c_white = RGBColor(255, 255, 255)
        c_accent = RGBColor(56, 189, 248)  # #38BDF8

        # ── 1. Title Slide ──────────────────────────────────────────────────
        title_slide = prs.slides.add_slide(blank_layout)

        # Background card
        bg_shape = title_slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5)
        )
        bg_shape.fill.solid()
        bg_shape.fill.fore_color.rgb = c_navy
        bg_shape.line.fill.background()

        # Accent top stripe
        top_bar = title_slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.2)
        )
        top_bar.fill.solid()
        top_bar.fill.fore_color.rgb = c_blue
        top_bar.line.fill.background()

        # Classification pill
        pill = title_slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.2), Inches(2.2), Inches(0.4)
        )
        pill.fill.solid()
        pill.fill.fore_color.rgb = c_blue
        pill.line.fill.background()
        pill_tf = pill.text_frame
        pill_tf.text = deck.classification.upper()
        p_p = pill_tf.paragraphs[0]
        p_p.font.size = Pt(11)
        p_p.font.bold = True
        p_p.font.color.rgb = c_white
        p_p.alignment = PP_ALIGN.CENTER

        # Deck Title
        title_box = title_slide.shapes.add_textbox(
            Inches(1.0), Inches(2.2), Inches(11.333), Inches(2.0)
        )
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = deck.title
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = c_white

        # Subtitle
        if deck.subtitle:
            p2 = tf.add_paragraph()
            p2.text = deck.subtitle
            p2.font.size = Pt(18)
            p2.font.color.rgb = c_accent
            p2.space_before = Pt(14)

        # Footer author & system info
        footer_box = title_slide.shapes.add_textbox(
            Inches(1.0), Inches(5.8), Inches(11.333), Inches(0.8)
        )
        f_tf = footer_box.text_frame
        f_p = f_tf.paragraphs[0]
        f_p.text = (
            f"Generated: {datetime.date.today().strftime('%B %d, %Y')}  |  "
            f"Author: {deck.author}  |  Platform: ServerGen AI Enterprise Suite"
        )
        f_p.font.size = Pt(11)
        f_p.font.color.rgb = c_slate

        # ── 2. Content Slides ───────────────────────────────────────────────
        for idx, slide_model in enumerate(deck.slides, start=1):
            slide = prs.slides.add_slide(blank_layout)

            # Slide background
            s_bg = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5)
            )
            s_bg.fill.solid()
            s_bg.fill.fore_color.rgb = c_light_bg
            s_bg.line.fill.background()

            # Top banner
            header_bar = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.2)
            )
            header_bar.fill.solid()
            header_bar.fill.fore_color.rgb = c_navy
            header_bar.line.fill.background()

            # Slide category tag
            cat_box = slide.shapes.add_textbox(
                Inches(0.8), Inches(0.15), Inches(8.0), Inches(0.3)
            )
            cat_tf = cat_box.text_frame
            cat_p = cat_tf.paragraphs[0]
            cat_p.text = f"{slide_model.category.upper()}  •  SLIDE {idx:02d}"
            cat_p.font.size = Pt(10)
            cat_p.font.bold = True
            cat_p.font.color.rgb = c_accent

            # Slide Title
            st_box = slide.shapes.add_textbox(
                Inches(0.8), Inches(0.45), Inches(10.0), Inches(0.6)
            )
            st_tf = st_box.text_frame
            st_p = st_tf.paragraphs[0]
            st_p.text = slide_model.title
            st_p.font.size = Pt(22)
            st_p.font.bold = True
            st_p.font.color.rgb = c_white

            # Classification top right badge
            badge = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, Inches(11.2), Inches(0.4), Inches(1.5), Inches(0.35)
            )
            badge.fill.solid()
            badge.fill.fore_color.rgb = c_blue
            badge.line.fill.background()
            badge_tf = badge.text_frame
            badge_p = badge_tf.paragraphs[0]
            badge_p.text = deck.classification
            badge_p.font.size = Pt(9)
            badge_p.font.bold = True
            badge_p.font.color.rgb = c_white
            badge_p.alignment = PP_ALIGN.CENTER

            # Main content card
            main_card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(0.8),
                Inches(1.6),
                Inches(11.733),
                Inches(4.5),
            )
            main_card.fill.solid()
            main_card.fill.fore_color.rgb = c_card_bg
            main_card.line.color.rgb = c_border
            main_card.line.width = Pt(1)

            # Bullet points box inside card
            content_box = slide.shapes.add_textbox(
                Inches(1.2), Inches(1.9), Inches(10.9), Inches(3.2)
            )
            c_tf = content_box.text_frame
            c_tf.word_wrap = True

            for b_idx, bullet in enumerate(slide_model.bullets):
                p_bullet = c_tf.paragraphs[0] if b_idx == 0 else c_tf.add_paragraph()
                p_bullet.text = f"•   {bullet}"
                p_bullet.font.size = Pt(16)
                p_bullet.font.color.rgb = c_navy
                p_bullet.space_after = Pt(14)
                p_bullet.line_spacing = 1.2

            # Key Takeaway footer box inside card
            if slide_model.key_takeaway:
                takeaway_card = slide.shapes.add_shape(
                    MSO_SHAPE.ROUNDED_RECTANGLE,
                    Inches(1.2),
                    Inches(5.1),
                    Inches(10.9),
                    Inches(0.8),
                )
                takeaway_card.fill.solid()
                takeaway_card.fill.fore_color.rgb = RGBColor(238, 242, 255)  # Light indigo
                takeaway_card.line.color.rgb = c_blue
                takeaway_card.line.width = Pt(1)

                t_tf = takeaway_card.text_frame
                t_tf.word_wrap = True
                t_p = t_tf.paragraphs[0]
                t_p.text = f"KEY TAKEAWAY: {slide_model.key_takeaway}"
                t_p.font.size = Pt(12)
                t_p.font.bold = True
                t_p.font.color.rgb = c_blue
                t_p.alignment = PP_ALIGN.LEFT

            # Slide Footer
            footer_txt = slide.shapes.add_textbox(
                Inches(0.8), Inches(6.8), Inches(11.733), Inches(0.4)
            )
            ft_p = footer_txt.text_frame.paragraphs[0]
            ft_p.text = f"ServerGen AI Enterprise Knowledge Deck  |  Slide {idx} of {len(deck.slides)}"
            ft_p.font.size = Pt(9)
            ft_p.font.color.rgb = c_slate

            # Speaker Notes
            if slide_model.notes:
                with contextlib.suppress(Exception):
                    slide.notes_slide.notes_text_frame.text = slide_model.notes

        prs.save(str(output_path))
        file_size = output_path.stat().st_size

        meta = GeneratedFileMeta(
            file_id=fid,
            filename=filename,
            format="pptx",
            file_size=file_size,
            title=deck.title,
            summary=f"Widescreen 16:9 Presentation with {len(deck.slides)} slides.",
            download_url=f"/api/v1/generate/download/{filename}",
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            slide_or_page_count=len(deck.slides),
        )
        self._save_meta(meta)
        return output_path, meta

    # ── Executive PDF Report Generation ──────────────────────────────────────

    async def generate_pdf_from_prompt(
        self,
        prompt: str,
        classification: str = "INTERNAL",
        context: str = "",
        model: str | None = None,
    ) -> tuple[ReportDocument, Path, GeneratedFileMeta]:
        """
        Drafts a structured executive document using local Ollama, then compiles to a PDF.
        """
        settings = get_settings()
        provider = OllamaProvider()
        active_model = model or settings.DEFAULT_MODEL

        system_instruction = (
            "You are an executive enterprise technical writer and senior systems architect. "
            "Your objective is to produce high-density, authoritative, well-structured technical "
            "and business reports. You MUST return strictly valid JSON matching the requested schema."
        )

        user_content = f"""USER TOPIC / REQUEST:
{prompt}

OPTIONAL REFERENCE KNOWLEDGE:
{context[:3000] if context else 'None provided.'}

INSTRUCTIONS:
Create a comprehensive, professional executive report.
The JSON must follow this exact schema:
{{
  "title": "Comprehensive Document Title",
  "subtitle": "Detailed Subtitle Explaining Context and Purpose",
  "classification": "{classification.upper()}",
  "author": "ServerGen AI Local Knowledge Engine",
  "executive_summary": "High-density 3-5 sentence synthesis covering core problem, mechanisms, and key conclusions.",
  "sections": [
    {{
      "heading": "Section 1: Architectural Foundation & Scope",
      "content": "In-depth explanatory paragraph detailing core principles, systems, and background.",
      "bullet_points": [
        "Granular detail or operational finding 1",
        "Granular detail or operational finding 2",
        "Granular detail or operational finding 3"
      ],
      "key_metric": "Key operational metric or critical finding"
    }},
    {{
      "heading": "Section 2: Security & Operational Governance",
      "content": "Paragraph explaining controls, safeguards, RBAC, and risk mitigation.",
      "bullet_points": [
        "Control specification 1",
        "Control specification 2"
      ],
      "key_metric": "Security compliance benchmark"
    }},
    {{
      "heading": "Section 3: Practical Implementation & Best Practices",
      "content": "Detailed step-by-step guidance for enterprise operators.",
      "bullet_points": [
        "Actionable implementation phase 1",
        "Actionable implementation phase 2",
        "Actionable implementation phase 3"
      ],
      "key_metric": "Performance SLA"
    }}
  ],
  "recommendations": [
    "Immediate operational action item 1",
    "Governance or compliance step 2",
    "Continuous auditing and optimization step 3"
  ]
}}
Ensure the response is strictly valid JSON with no extraneous characters.
"""

        doc_data: ReportDocument | None = None
        try:
            req = LLMRequest(
                model=active_model,
                prompt=user_content,
                system_prompt=system_instruction,
                max_tokens=1100,
                temperature=0.3,
            )
            response = await asyncio.wait_for(provider.generate(req), timeout=30.0)
            doc_data = self._parse_report_json(response.content)
        except Exception as exc:
            logger.warning("Local LLM report generation warning: %s. Using heuristic synthesizer.", exc)

        if not doc_data or not doc_data.sections:
            doc_data = self._heuristic_report_fallback(prompt, classification)

        file_id = str(uuid.uuid4())[:12]
        path, meta = self.render_pdf(doc_data, file_id=file_id)
        return doc_data, path, meta

    def _parse_report_json(self, raw_output: str) -> ReportDocument | None:
        """Parse ReportDocument JSON with regex markdown cleaning."""
        cleaned = raw_output.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
            else:
                cleaned = re.sub(r"^```[a-z]*\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                return ReportDocument(**parsed)
            except Exception:
                pass
        return None

    def _heuristic_report_fallback(self, prompt: str, classification: str) -> ReportDocument:
        """Constructs a rich executive report fallback when LLM output is non-JSON."""
        clean_title = prompt.split("\n")[0][:70].strip() or "Enterprise System Assessment"
        return ReportDocument(
            title=clean_title,
            subtitle="Executive Technical Report & Operational Analysis",
            classification=classification,
            author="ServerGen AI Local Knowledge Engine",
            executive_summary=(
                f"This document provides an authoritative evaluation of '{clean_title}'. "
                "The analysis synthesizes zero-trust architectural principles, localized on-premise execution, "
                "and automated governance policies to ensure verified, compliance-ready enterprise performance."
            ),
            sections=[
                ReportSection(
                    heading="1. Operational Scope & Architecture Overview",
                    content=(
                        "Modern enterprise automation demands strict isolation between untrusted input and "
                        "execution runtimes. All operations must adhere to verified access boundaries without "
                        "relying on external public cloud APIs."
                    ),
                    bullet_points=[
                        "Zero external telemetry or data egress during query and generation processing.",
                        "Strict Role-Based Access Control enforcing clearance from Public to Restricted.",
                        "Deterministic policy checks preceding all model and tool executions.",
                    ],
                    key_metric="100% On-Premise Air-Gapped Operation",
                ),
                ReportSection(
                    heading="2. Security Controls & Dual-Custody Approval",
                    content=(
                        "System modifications and sensitive data access require multi-layered policy evaluations. "
                        "When tasks exceed acceptable autonomous thresholds, dual-custody approval workflows "
                        "halt execution pending authorized review."
                    ),
                    bullet_points=[
                        "Automated risk scoring based on keyword detection and declared data sensitivity.",
                        "Cryptographic SHA-256 audit ledger recording actor, action, and decision.",
                        "Immutable document versioning preventing unauthorized modification.",
                    ],
                    key_metric="Cryptographic Tamper-Evidence Ledger",
                ),
                ReportSection(
                    heading="3. Strategic Recommendations & Verification",
                    content=(
                        "To maximize organizational value, operations must be continuously measured against "
                        "established safety criteria. Regular regression checks and verification suites provide "
                        "objective confidence in operational stability."
                    ),
                    bullet_points=[
                        "Execute automated integration verification across all 5 core security subsystems.",
                        "Regularly reindex departmental document repositories to maintain semantic accuracy.",
                        "Review pending approvals and ledger event sequences on a weekly cadence.",
                    ],
                    key_metric="Zero Compliance Drift",
                ),
            ],
            recommendations=[
                "Deploy local LLM runtime (Ollama) with verified hardware resource allocations.",
                "Enforce dual-custody approvals for any infrastructure modification or sensitive export.",
                "Perform scheduled audit ledger verification to validate cryptographic chain integrity.",
            ],
        )

    def render_pdf(
        self, doc_data: ReportDocument, file_id: str | None = None
    ) -> tuple[Path, GeneratedFileMeta]:
        """
        Compiles a ReportDocument Pydantic model into a publication-quality PDF using ReportLab.
        """
        fid = file_id or str(uuid.uuid4())[:12]
        sanitized_title = re.sub(r"[^\w\-]", "_", doc_data.title)[:40].strip("_") or "report"
        filename = f"{fid}_{sanitized_title}.pdf"
        output_path = self.storage_dir / filename

        # 40pt margins = ~0.55 in
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=40,
            rightMargin=40,
            topMargin=45,
            bottomMargin=45,
        )

        styles = getSampleStyleSheet()

        # Custom typography palette
        c_primary = colors.HexColor("#1E293B")  # Slate 800
        c_blue = colors.HexColor("#2563EB")  # Blue 600
        c_muted = colors.HexColor("#64748B")  # Slate 500
        c_border = colors.HexColor("#E2E8F0")  # Slate 200
        c_callout_bg = colors.HexColor("#F8FAFC")  # Slate 50

        # Classification color
        c_map = {
            "PUBLIC": colors.HexColor("#16A34A"),  # Green
            "INTERNAL": colors.HexColor("#2563EB"),  # Blue
            "CONFIDENTIAL": colors.HexColor("#D97706"),  # Amber
            "RESTRICTED": colors.HexColor("#DC2626"),  # Red
        }
        cls_color = c_map.get(doc_data.classification.upper(), c_blue)

        # Style definitions
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=c_primary,
            spaceAfter=6,
        )

        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=c_muted,
            spaceAfter=14,
        )

        h1_style = ParagraphStyle(
            "SectionH1",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=c_blue,
            spaceBefore=14,
            spaceAfter=6,
        )

        body_style = ParagraphStyle(
            "BodyDark",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=c_primary,
            spaceAfter=8,
        )

        bullet_style = ParagraphStyle(
            "BulletDark",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=c_primary,
            leftIndent=14,
            spaceAfter=4,
        )

        callout_style = ParagraphStyle(
            "CalloutText",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#334155"),
        )

        story: list[Any] = []

        # ── 1. Header Banner & Security Badge ───────────────────────────────
        badge_p = Paragraph(
            f"<b>CLASSIFICATION: {doc_data.classification.upper()}</b>",
            ParagraphStyle(
                "Badge",
                fontName="Helvetica-Bold",
                fontSize=8.5,
                textColor=colors.white,
                alignment=1,
            ),
        )
        badge_table = Table([[badge_p]], colWidths=[140], rowHeights=[20])
        badge_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), cls_color),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )

        story.append(badge_table)
        story.append(Spacer(1, 8))

        # Title & Subtitle
        story.append(Paragraph(doc_data.title, title_style))
        if doc_data.subtitle:
            story.append(Paragraph(doc_data.subtitle, subtitle_style))

        # Metadata table (Author, Date, System)
        meta_data = [
            [
                Paragraph(f"<b>Author:</b> {doc_data.author}", body_style),
                Paragraph(
                    f"<b>Date:</b> {datetime.date.today().strftime('%B %d, %Y')}", body_style
                ),
                Paragraph("<b>Platform:</b> ServerGen AI", body_style),
            ]
        ]
        meta_table = Table(meta_data, colWidths=[200, 160, 172])
        meta_table.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 1, c_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(meta_table)
        story.append(Spacer(1, 12))

        # ── 2. Executive Summary Box ────────────────────────────────────────
        if doc_data.executive_summary:
            summary_title = Paragraph("<b>EXECUTIVE SUMMARY</b>", h1_style)
            summary_body = Paragraph(doc_data.executive_summary, callout_style)
            sum_cell = [summary_title, Spacer(1, 4), summary_body]
            sum_table = Table([[sum_cell]], colWidths=[532])
            sum_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), c_callout_bg),
                        ("BOX", (0, 0), (-1, -1), 1, c_border),
                        ("LINEBEFORE", (0, 0), (0, -1), 3.5, c_blue),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                        ("LEFTPADDING", (0, 0), (-1, -1), 12),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ]
                )
            )
            story.append(sum_table)
            story.append(Spacer(1, 14))

        # ── 3. Content Sections ─────────────────────────────────────────────
        for sec in doc_data.sections:
            sec_elements: list[Any] = [Paragraph(sec.heading, h1_style)]

            if sec.content:
                sec_elements.append(Paragraph(sec.content, body_style))

            for bp in sec.bullet_points:
                sec_elements.append(Paragraph(f"•  {bp}", bullet_style))

            if sec.key_metric:
                metric_p = Paragraph(
                    f"<b>KEY FINDING / BENCHMARK:</b> {sec.key_metric}",
                    ParagraphStyle(
                        "Metric",
                        parent=styles["Normal"],
                        fontName="Helvetica-Bold",
                        fontSize=8.5,
                        textColor=c_blue,
                    ),
                )
                m_table = Table([[metric_p]], colWidths=[532])
                m_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2FF")),
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C7D2FE")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ]
                    )
                )
                sec_elements.append(Spacer(1, 4))
                sec_elements.append(m_table)

            sec_elements.append(Spacer(1, 10))
            story.append(KeepTogether(sec_elements))

        # ── 4. Strategic Recommendations ────────────────────────────────────
        if doc_data.recommendations:
            rec_elements: list[Any] = [
                Paragraph("Strategic Action Items & Recommendations", h1_style)
            ]
            for idx, rec in enumerate(doc_data.recommendations, start=1):
                rec_elements.append(
                    Paragraph(f"<b>[{idx}]</b>  {rec}", bullet_style)
                )
            rec_elements.append(Spacer(1, 10))
            story.append(KeepTogether(rec_elements))

        # Build PDF using NumberedCanvas for dynamic page counts
        doc.build(story, canvasmaker=NumberedCanvas)
        file_size = output_path.stat().st_size

        meta = GeneratedFileMeta(
            file_id=fid,
            filename=filename,
            format="pdf",
            file_size=file_size,
            title=doc_data.title,
            summary=doc_data.executive_summary[:200]
            if doc_data.executive_summary
            else "Executive PDF Report",
            download_url=f"/api/v1/generate/download/{filename}",
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            slide_or_page_count=1,
        )
        self._save_meta(meta)
        return output_path, meta
