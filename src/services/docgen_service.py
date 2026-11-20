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

import pptx
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
from pydantic import BaseModel, Field
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

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
            if candidate.is_file() and candidate.name.startswith(clean) and candidate.is_relative_to(self.storage_dir):
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
                max_tokens=2500,
                temperature=0.25,
            )
            response = await asyncio.wait_for(provider.generate(req), timeout=60.0)
            deck_data = self._parse_deck_json(response.content)
        except Exception as exc:
            logger.warning("Local LLM presentation generation warning: %s. Using heuristic synthesizer.", exc)

        if not deck_data or not deck_data.slides:
            deck_data = self._heuristic_deck_fallback(prompt, num_slides, classification, context=context)

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
        if start != -1 and end != -1 and end > start:
            json_str = cleaned[start : end + 1]
            try:
                parsed = json.loads(json_str)
                return PresentationDeck(**parsed)
            except Exception:
                try:
                    cleaned_commas = re.sub(r",\s*([}\]])", r"\1", json_str)
                    parsed = json.loads(cleaned_commas)
                    return PresentationDeck(**parsed)
                except Exception as exc:
                    logger.debug("JSON parse failed: %s", exc)
        return None

    def _extract_insights_from_context(self, context: str, min_items: int = 5) -> list[str]:
        """Extract substantive factual points from reference context or RAG retrieval."""
        if not context:
            return []
        lines = [line.strip() for line in context.splitlines() if line.strip()]
        insights = []
        for line in lines:
            clean = re.sub(r"^[\*\-•#\d+\.]+\s*", "", line).strip()
            clean = re.sub(r"[\*_`]", "", clean)
            if len(clean) > 20 and not clean.lower().startswith(
                ("here is", "sure,", "summary:", "overview:", "in summary", "to summarize")
            ):
                insights.append(clean)

        if len(insights) < min_items:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", context) if len(s.strip()) > 25]
            for s in sentences:
                clean_s = re.sub(r"^[\*\-•#\d+\.]+\s*", "", s).strip()
                clean_s = re.sub(r"[\*_`]", "", clean_s)
                if clean_s and clean_s not in insights:
                    insights.append(clean_s)
        return insights

    def _heuristic_deck_fallback(
        self, prompt: str, num_slides: int, classification: str, context: str = ""
    ) -> PresentationDeck:
        """Constructs a clean, logically sound slide deck when LLM returns unstructured text."""
        clean_title = prompt.split("\n")[0][:60].strip() or "Executive Project Brief"
        extracted = self._extract_insights_from_context(context)

        s1_bullets = extracted[:3] if len(extracted) >= 3 else [
            f"Core Objective: Address '{clean_title}' with structured operational precision.",
            "Establish zero-trust boundaries and verified security postures across all workflows.",
            "Maximize efficiency while maintaining rigorous governance and auditability.",
        ]

        s2_bullets = extracted[3:6] if len(extracted) >= 6 else [
            "On-premise execution isolated from external public cloud egress.",
            "Role-Based Access Control enforcing granular user clearances.",
            "Vector retrieval combined with deterministic policy checks.",
        ]

        s3_bullets = extracted[6:9] if len(extracted) >= 9 else [
            "Phase 1: Baseline deployment and automated role entitlement checks.",
            "Phase 2: Full document ingestion, indexing, and vector synchronization.",
            "Phase 3: Continuous audit verification with SHA-256 tamper-evident ledgers.",
        ]

        slides = [
            SlideContent(
                title="Executive Overview & Objectives",
                category="STRATEGY",
                bullets=s1_bullets,
                key_takeaway="Align technical capabilities directly with verified enterprise compliance.",
                notes="Introduce primary stakeholder objectives and scope.",
            ),
            SlideContent(
                title="Current Architecture & Technical Analysis",
                category="ARCHITECTURE",
                bullets=s2_bullets,
                key_takeaway="Zero data leakage guaranteed through verified localized boundaries.",
                notes="Review architectural components and operational safety mechanisms.",
            ),
            SlideContent(
                title="Implementation Roadmap & Best Practices",
                category="OPERATIONS",
                bullets=s3_bullets,
                key_takeaway="Predictable rollout supported by continuous automated verification.",
                notes="Emphasize governance controls and incremental deployment milestones.",
            ),
        ]

        if num_slides >= 4:
            s4_bullets = extracted[9:12] if len(extracted) >= 12 else [
                "High-risk operational tasks require dual-custody managerial sign-off.",
                "All queries and model responses logged to cryptographic audit ledger.",
                "Clear separation between Viewer, Analyst, Operator, and Administrator roles.",
            ]
            slides.append(
                SlideContent(
                    title="Risk Management & Dual-Custody Controls",
                    category="GOVERNANCE",
                    bullets=s4_bullets,
                    key_takeaway="No critical mutation can occur without verified authorization.",
                    notes="Highlight regulatory adherence and managerial control.",
                )
            )

        if num_slides >= 5:
            s5_bullets = extracted[12:15] if len(extracted) >= 15 else [
                "Validate local model performance and document indexing status.",
                "Train departmental users on role-specific query interfaces.",
                "Review daily audit trail logs to maintain zero compliance drift.",
            ]
            slides.append(
                SlideContent(
                    title="Summary & Next Steps",
                    category="SUMMARY",
                    bullets=s5_bullets,
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
        Compiles a PresentationDeck Pydantic model into a high-impact, modern 16:9 widescreen PPTX.
        Includes Executive KPI Cards, 2-Column Analytical Cards, Strategic Milestones, and bold typography.
        """
        fid = file_id or str(uuid.uuid4())[:12]
        sanitized_title = re.sub(r"[^\w\-]", "_", deck.title)[:40].strip("_") or "presentation"
        filename = f"{fid}_{sanitized_title}.pptx"
        output_path = self.storage_dir / filename

        prs = pptx.Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank_layout = prs.slide_layouts[6]

        # Corporate Color Palette
        c_navy = RGBColor(15, 23, 42)        # #0F172A
        c_blue = RGBColor(37, 99, 235)       # #2563EB
        c_slate = RGBColor(71, 85, 105)      # #475569
        c_light_bg = RGBColor(248, 250, 252) # #F8FAFC
        c_card_bg = RGBColor(255, 255, 255)
        c_border = RGBColor(226, 232, 240)   # #E2E8F0
        c_white = RGBColor(255, 255, 255)
        c_accent = RGBColor(56, 189, 248)    # #38BDF8
        c_emerald = RGBColor(16, 185, 129)   # #10B981
        c_purple = RGBColor(124, 58, 237)    # #7C3AED

        def _add_bullet(tf, text_val: str, is_first: bool = False, font_sz: Pt | None = None, space: Pt | None = None):
            f_sz = font_sz or Pt(13.5)
            s_after = space or Pt(8)
            p = tf.paragraphs[0] if is_first else tf.add_paragraph()
            p.space_after = s_after
            p.line_spacing = 1.15

            # Match **Heading**: or Heading:
            m = re.match(r"^(\*\*.*?\*\*|[A-Za-z0-9\s]{3,28}:)(.*)$", text_val.strip())
            if m:
                lead = m.group(1).replace("**", "").strip()
                body = m.group(2).strip()
                if not lead.endswith(":"):
                    lead += ":"
                r1 = p.add_run()
                r1.text = f"?   {lead} "
                r1.font.bold = True
                r1.font.size = f_sz
                r1.font.color.rgb = c_navy

                r2 = p.add_run()
                r2.text = body
                r2.font.bold = False
                r2.font.size = f_sz
                r2.font.color.rgb = c_slate
            else:
                r = p.add_run()
                r.text = f"?   {text_val.strip()}"
                r.font.size = f_sz
                r.font.color.rgb = c_navy

        # ?? 1. Title Slide ??????????????????????????????????????????????????
        title_slide = prs.slides.add_slide(blank_layout)
        bg_shape = title_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
        bg_shape.fill.solid()
        bg_shape.fill.fore_color.rgb = c_navy
        bg_shape.line.fill.background()

        top_bar = title_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.2))
        top_bar.fill.solid()
        top_bar.fill.fore_color.rgb = c_blue
        top_bar.line.fill.background()

        pill = title_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.2), Inches(2.2), Inches(0.4))
        pill.fill.solid()
        pill.fill.fore_color.rgb = c_blue
        pill.line.fill.background()
        pill_p = pill.text_frame.paragraphs[0]
        pill_p.text = deck.classification.upper()
        pill_p.font.size = Pt(11)
        pill_p.font.bold = True
        pill_p.font.color.rgb = c_white
        pill_p.alignment = PP_ALIGN.CENTER

        title_box = title_slide.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(11.333), Inches(2.2))
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = deck.title
        p.font.size = Pt(38)
        p.font.bold = True
        p.font.color.rgb = c_white

        if deck.subtitle:
            p2 = tf.add_paragraph()
            p2.text = deck.subtitle
            p2.font.size = Pt(18)
            p2.font.color.rgb = c_accent
            p2.space_before = Pt(14)

        footer_box = title_slide.shapes.add_textbox(Inches(1.0), Inches(5.8), Inches(11.333), Inches(0.8))
        f_p = footer_box.text_frame.paragraphs[0]
        f_p.text = f"Generated: {datetime.date.today().strftime('%B %d, %Y')}  |  Author: {deck.author}  |  Platform: ServerGen AI Enterprise Suite"
        f_p.font.size = Pt(11)
        f_p.font.color.rgb = c_slate

        # ?? 2. Content Slides with Dynamic Enterprise Layouts ??????????????
        total_slides = len(deck.slides)
        for idx, slide_model in enumerate(deck.slides, start=1):
            slide = prs.slides.add_slide(blank_layout)

            # Slide background
            s_bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
            s_bg.fill.solid()
            s_bg.fill.fore_color.rgb = c_light_bg
            s_bg.line.fill.background()

            # Top banner
            header_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.15))
            header_bar.fill.solid()
            header_bar.fill.fore_color.rgb = c_navy
            header_bar.line.fill.background()

            # Category tag
            cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.12), Inches(8.0), Inches(0.28))
            cat_p = cat_box.text_frame.paragraphs[0]
            cat_p.text = f"{slide_model.category.upper()}  ?  SLIDE {idx:02d} OF {total_slides:02d}"
            cat_p.font.size = Pt(10)
            cat_p.font.bold = True
            cat_p.font.color.rgb = c_accent

            # Slide Title
            st_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.42), Inches(10.0), Inches(0.65))
            st_tf = st_box.text_frame
            st_tf.word_wrap = True
            st_p = st_tf.paragraphs[0]
            st_p.text = slide_model.title
            st_p.font.size = Pt(19) if len(slide_model.title) > 45 else Pt(22)
            st_p.font.bold = True
            st_p.font.color.rgb = c_white

            # Classification top right badge
            badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(11.2), Inches(0.38), Inches(1.5), Inches(0.35))
            badge.fill.solid()
            badge.fill.fore_color.rgb = c_blue
            badge.line.fill.background()
            badge_p = badge.text_frame.paragraphs[0]
            badge_p.text = deck.classification
            badge_p.font.size = Pt(9)
            badge_p.font.bold = True
            badge_p.font.color.rgb = c_white
            badge_p.alignment = PP_ALIGN.CENTER

            # LAYOUT VARIANT 1: Slide 1 -> Executive Overview with 3 KPI Stat Cards
            if idx == 1:
                # 3 KPI Metric Cards
                kpi_defs = [
                    ("CORE STRATEGY", "100% Local", "On-Premise LLM Inference", c_blue),
                    ("GOVERNANCE & TRUST", "Dual-Custody", "Zero-Trust Policy Enforced", c_emerald),
                    ("COMPLIANCE", "Air-Gapped", "Cryptographic SHA-256 Audit", c_purple),
                ]
                for k_i, (k_label, k_val, k_sub, k_color) in enumerate(kpi_defs):
                    k_left = Inches(0.8 + k_i * 4.0)
                    k_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, k_left, Inches(1.4), Inches(3.733), Inches(1.4))
                    k_card.fill.solid()
                    k_card.fill.fore_color.rgb = c_card_bg
                    k_card.line.color.rgb = c_border
                    k_card.line.width = Pt(1)

                    # Accent left stripe
                    k_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, k_left, Inches(1.4), Inches(0.12), Inches(1.4))
                    k_bar.fill.solid()
                    k_bar.fill.fore_color.rgb = k_color
                    k_bar.line.fill.background()

                    k_tb = slide.shapes.add_textbox(k_left + Inches(0.2), Inches(1.48), Inches(3.4), Inches(1.2))
                    k_tf = k_tb.text_frame
                    k_tf.word_wrap = True
                    p_l = k_tf.paragraphs[0]
                    p_l.text = k_label
                    p_l.font.size = Pt(9)
                    p_l.font.bold = True
                    p_l.font.color.rgb = c_slate

                    p_v = k_tf.add_paragraph()
                    p_v.text = k_val
                    p_v.font.size = Pt(20)
                    p_v.font.bold = True
                    p_v.font.color.rgb = k_color
                    p_v.space_before = Pt(2)

                    p_s = k_tf.add_paragraph()
                    p_s.text = k_sub
                    p_s.font.size = Pt(8.5)
                    p_s.font.color.rgb = c_slate

                # Main Overview Bullet Card
                o_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(3.0), Inches(11.733), Inches(3.4))
                o_card.fill.solid()
                o_card.fill.fore_color.rgb = c_card_bg
                o_card.line.color.rgb = c_border
                o_card.line.width = Pt(1)

                o_tb = slide.shapes.add_textbox(Inches(1.1), Inches(3.15), Inches(11.1), Inches(2.2))
                o_tf = o_tb.text_frame
                o_tf.word_wrap = True
                for b_i, bullet in enumerate(slide_model.bullets[:3]):
                    _add_bullet(o_tf, bullet, is_first=(b_i == 0), font_sz=Pt(13.5), space=Pt(8))

                # Key Takeaway bar inside card
                if slide_model.key_takeaway:
                    t_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.1), Inches(5.45), Inches(11.1), Inches(0.75))
                    t_card.fill.solid()
                    t_card.fill.fore_color.rgb = RGBColor(238, 242, 255)
                    t_card.line.color.rgb = c_blue
                    t_card.line.width = Pt(1)
                    t_p = t_card.text_frame.paragraphs[0]
                    t_p.text = f"KEY STRATEGIC TAKEAWAY: {slide_model.key_takeaway}"
                    t_p.font.size = Pt(11)
                    t_p.font.bold = True
                    t_p.font.color.rgb = c_blue

            # LAYOUT VARIANT 2: Final Slide (if >= 4 slides) -> 4 Milestone Roadmap Cards
            elif idx == total_slides and total_slides >= 4:
                phases = [
                    ("PHASE 01", "Discovery & Baseline", c_blue),
                    ("PHASE 02", "Operational Rollout", RGBColor(2, 132, 199)),
                    ("PHASE 03", "Governance Integration", c_emerald),
                    ("PHASE 04", "Continuous Optimization", c_purple),
                ]
                for p_i, (p_tag, p_heading, p_color) in enumerate(phases):
                    m_left = Inches(0.8 + p_i * 3.0)
                    m_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, m_left, Inches(1.5), Inches(2.733), Inches(4.5))
                    m_card.fill.solid()
                    m_card.fill.fore_color.rgb = c_card_bg
                    m_card.line.color.rgb = c_border
                    m_card.line.width = Pt(1)

                    # Top accent bar
                    m_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, m_left, Inches(1.5), Inches(2.733), Inches(0.12))
                    m_bar.fill.solid()
                    m_bar.fill.fore_color.rgb = p_color
                    m_bar.line.fill.background()

                    # Phase Pill
                    m_pill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, m_left + Inches(0.2), Inches(1.75), Inches(1.2), Inches(0.32))
                    m_pill.fill.solid()
                    m_pill.fill.fore_color.rgb = p_color
                    m_pill.line.fill.background()
                    m_pill_p = m_pill.text_frame.paragraphs[0]
                    m_pill_p.text = p_tag
                    m_pill_p.font.size = Pt(9)
                    m_pill_p.font.bold = True
                    m_pill_p.font.color.rgb = c_white
                    m_pill_p.alignment = PP_ALIGN.CENTER

                    m_tb = slide.shapes.add_textbox(m_left + Inches(0.2), Inches(2.2), Inches(2.333), Inches(3.6))
                    m_tf = m_tb.text_frame
                    m_tf.word_wrap = True
                    p_h = m_tf.paragraphs[0]
                    p_h.text = p_heading
                    p_h.font.size = Pt(13)
                    p_h.font.bold = True
                    p_h.font.color.rgb = c_navy
                    p_h.space_after = Pt(8)

                    bullet_content = slide_model.bullets[p_i] if p_i < len(slide_model.bullets) else "Operational milestone execution."
                    p_b = m_tf.add_paragraph()
                    p_b.text = re.sub(r"^\*\*.*?\*\*\s*", "", bullet_content)
                    p_b.font.size = Pt(10.5)
                    p_b.font.color.rgb = c_slate
                    p_b.line_spacing = 1.15

                # Bottom strategic commitment bar
                if slide_model.key_takeaway:
                    t_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(6.15), Inches(11.733), Inches(0.55))
                    t_card.fill.solid()
                    t_card.fill.fore_color.rgb = RGBColor(238, 242, 255)
                    t_card.line.color.rgb = c_blue
                    t_card.line.width = Pt(1)
                    t_p = t_card.text_frame.paragraphs[0]
                    t_p.text = f"EXECUTIVE COMMITMENT: {slide_model.key_takeaway}"
                    t_p.font.size = Pt(10.5)
                    t_p.font.bold = True
                    t_p.font.color.rgb = c_blue

            # LAYOUT VARIANT 3: Middle Slides with 4+ bullets -> 2-Column Comparison Cards
            elif len(slide_model.bullets) >= 4:
                # Left Column Card
                l_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.5), Inches(5.7), Inches(4.5))
                l_card.fill.solid()
                l_card.fill.fore_color.rgb = c_card_bg
                l_card.line.color.rgb = c_border
                l_card.line.width = Pt(1)

                l_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.5), Inches(5.7), Inches(0.12))
                l_bar.fill.solid()
                l_bar.fill.fore_color.rgb = c_blue
                l_bar.line.fill.background()

                l_tb = slide.shapes.add_textbox(Inches(1.1), Inches(1.75), Inches(5.1), Inches(3.9))
                l_tf = l_tb.text_frame
                l_tf.word_wrap = True
                p_lh = l_tf.paragraphs[0]
                p_lh.text = "STRATEGIC ARCHITECTURE & CONTEXT"
                p_lh.font.size = Pt(11)
                p_lh.font.bold = True
                p_lh.font.color.rgb = c_blue
                p_lh.space_after = Pt(10)

                for b in slide_model.bullets[:2]:
                    _add_bullet(l_tf, b, is_first=False, font_sz=Pt(12.5), space=Pt(10))

                # Right Column Card
                r_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.833), Inches(1.5), Inches(5.7), Inches(4.5))
                r_card.fill.solid()
                r_card.fill.fore_color.rgb = c_card_bg
                r_card.line.color.rgb = c_border
                r_card.line.width = Pt(1)

                r_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.833), Inches(1.5), Inches(5.7), Inches(0.12))
                r_bar.fill.solid()
                r_bar.fill.fore_color.rgb = c_emerald
                r_bar.line.fill.background()

                r_tb = slide.shapes.add_textbox(Inches(7.133), Inches(1.75), Inches(5.1), Inches(3.9))
                r_tf = r_tb.text_frame
                r_tf.word_wrap = True
                p_rh = r_tf.paragraphs[0]
                p_rh.text = "OPERATIONAL IMPACT & CONTROLS"
                p_rh.font.size = Pt(11)
                p_rh.font.bold = True
                p_rh.font.color.rgb = c_emerald
                p_rh.space_after = Pt(10)

                for b in slide_model.bullets[2:4]:
                    _add_bullet(r_tf, b, is_first=False, font_sz=Pt(12.5), space=Pt(10))

                # Key Takeaway bar across bottom
                if slide_model.key_takeaway:
                    t_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(6.15), Inches(11.733), Inches(0.55))
                    t_card.fill.solid()
                    t_card.fill.fore_color.rgb = RGBColor(238, 242, 255)
                    t_card.line.color.rgb = c_blue
                    t_card.line.width = Pt(1)
                    t_p = t_card.text_frame.paragraphs[0]
                    t_p.text = f"KEY TAKEAWAY: {slide_model.key_takeaway}"
                    t_p.font.size = Pt(10.5)
                    t_p.font.bold = True
                    t_p.font.color.rgb = c_blue

            # LAYOUT VARIANT 4: Standard Deep Content Card
            else:
                main_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.5), Inches(11.733), Inches(4.5))
                main_card.fill.solid()
                main_card.fill.fore_color.rgb = c_card_bg
                main_card.line.color.rgb = c_border
                main_card.line.width = Pt(1)

                top_bar_mc = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.5), Inches(11.733), Inches(0.12))
                top_bar_mc.fill.solid()
                top_bar_mc.fill.fore_color.rgb = c_blue
                top_bar_mc.line.fill.background()

                content_box = slide.shapes.add_textbox(Inches(1.2), Inches(1.85), Inches(10.9), Inches(3.0))
                c_tf = content_box.text_frame
                c_tf.word_wrap = True

                for b_idx, bullet in enumerate(slide_model.bullets):
                    _add_bullet(c_tf, bullet, is_first=(b_idx == 0), font_sz=Pt(14), space=Pt(12))

                if slide_model.key_takeaway:
                    takeaway_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.2), Inches(5.1), Inches(10.9), Inches(0.75))
                    takeaway_card.fill.solid()
                    takeaway_card.fill.fore_color.rgb = RGBColor(238, 242, 255)
                    takeaway_card.line.color.rgb = c_blue
                    takeaway_card.line.width = Pt(1)
                    t_p = takeaway_card.text_frame.paragraphs[0]
                    t_p.text = f"KEY TAKEAWAY: {slide_model.key_takeaway}"
                    t_p.font.size = Pt(11.5)
                    t_p.font.bold = True
                    t_p.font.color.rgb = c_blue

            # Slide Footer
            footer_txt = slide.shapes.add_textbox(Inches(0.8), Inches(6.8), Inches(11.733), Inches(0.4))
            ft_p = footer_txt.text_frame.paragraphs[0]
            ft_p.text = f"ServerGen AI Enterprise Knowledge Deck  |  Slide {idx} of {total_slides}  |  {deck.classification.upper()}"
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

    def render_executive_data_deck(
        self,
        title: str,
        subtitle: str,
        table_headers: list[str],
        table_rows: list[list[Any]],
        executive_insights: str,
        classification: str = "INTERNAL",
        file_id: str | None = None,
    ) -> tuple[Path, GeneratedFileMeta]:
        """
        Builds a multi-slide executive presentation containing:
        - Slide 1: Dark Navy corporate title slide.
        - Slide 2: Executive Summary with 3 prominent KPI Stat Cards.
        - Slide 3: Native editable PowerPoint visual chart (CategoryChartData) + context bullets.
        - Slide 4: Structured data breakdown table with header formatting & zebra fills.
        - Slide 5: Strategic next steps & governance takeaways.
        """
        fid = file_id or str(uuid.uuid4())[:12]
        sanitized_title = re.sub(r"[^\w\-]", "_", title)[:40].strip("_") or "data_deck"
        filename = f"{fid}_{sanitized_title}.pptx"
        output_path = self.storage_dir / filename

        prs = pptx.Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank_layout = prs.slide_layouts[6]

        # Corporate color palette
        c_navy = RGBColor(15, 23, 42)
        c_blue = RGBColor(37, 99, 235)
        c_slate = RGBColor(71, 85, 105)
        c_light_bg = RGBColor(248, 250, 252)
        c_card_bg = RGBColor(255, 255, 255)
        c_border = RGBColor(226, 232, 240)
        c_white = RGBColor(255, 255, 255)
        c_accent = RGBColor(56, 189, 248)
        c_emerald = RGBColor(16, 185, 129)

        # ── Slide 1: Title Slide ─────────────────────────────────────────────
        s1 = prs.slides.add_slide(blank_layout)
        bg1 = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
        bg1.fill.solid()
        bg1.fill.fore_color.rgb = c_navy
        bg1.line.fill.background()

        top_bar = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.2))
        top_bar.fill.solid()
        top_bar.fill.fore_color.rgb = c_blue
        top_bar.line.fill.background()

        pill = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.2), Inches(2.2), Inches(0.4))
        pill.fill.solid()
        pill.fill.fore_color.rgb = c_blue
        pill.line.fill.background()
        pill_p = pill.text_frame.paragraphs[0]
        pill_p.text = classification.upper()
        pill_p.font.size = Pt(11)
        pill_p.font.bold = True
        pill_p.font.color.rgb = c_white
        pill_p.alignment = PP_ALIGN.CENTER

        t_box = s1.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.333), Inches(2.0))
        tf = t_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(38)
        p.font.bold = True
        p.font.color.rgb = c_white

        if subtitle:
            p2 = tf.add_paragraph()
            p2.text = subtitle
            p2.font.size = Pt(18)
            p2.font.color.rgb = c_accent
            p2.space_before = Pt(14)

        f_box = s1.shapes.add_textbox(Inches(1.0), Inches(5.8), Inches(11.333), Inches(0.8))
        fp = f_box.text_frame.paragraphs[0]
        fp.text = f"Generated: {datetime.date.today().strftime('%B %d, %Y')}  |  ServerGen AI Enterprise Analytics"
        fp.font.size = Pt(11)
        fp.font.color.rgb = c_slate

        # Calculate metrics from table
        num_rows = len(table_rows)
        first_num_col = None
        tot_metric = 0.0
        avg_metric = 0.0
        numeric_vals = []
        for c_idx in range(1, len(table_headers)):
            for r in table_rows:
                v = r[c_idx] if c_idx < len(r) else None
                if isinstance(v, (int, float)):
                    numeric_vals.append(float(v))
            if numeric_vals:
                first_num_col = table_headers[c_idx]
                tot_metric = sum(numeric_vals)
                avg_metric = tot_metric / len(numeric_vals)
                break

        def _add_slide_header(slide, cat_text: str, title_text: str, slide_num: int):
            s_bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
            s_bg.fill.solid()
            s_bg.fill.fore_color.rgb = c_light_bg
            s_bg.line.fill.background()

            hbar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.15))
            hbar.fill.solid()
            hbar.fill.fore_color.rgb = c_navy
            hbar.line.fill.background()

            cbox = slide.shapes.add_textbox(Inches(0.8), Inches(0.12), Inches(8.0), Inches(0.25))
            cp = cbox.text_frame.paragraphs[0]
            cp.text = f"{cat_text.upper()}  •  SLIDE {slide_num:02d}"
            cp.font.size = Pt(9.5)
            cp.font.bold = True
            cp.font.color.rgb = c_accent

            tbox = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(10.0), Inches(0.65))
            tp = tbox.text_frame.paragraphs[0]
            tp.text = title_text
            tp.font.size = Pt(20)
            tp.font.bold = True
            tp.font.color.rgb = c_white

        # ── Slide 2: Executive Summary & KPI Stat Cards ──────────────────────
        s2 = prs.slides.add_slide(blank_layout)
        _add_slide_header(s2, "EXECUTIVE SUMMARY", "Key Performance Indicators & Findings", 2)

        card_w = Inches(3.64)
        card_h = Inches(1.5)
        card_y = Inches(1.5)

        kpis = [
            (
                "TOTAL AGGREGATE",
                f"${tot_metric:,.2f}" if tot_metric > 1000 else f"{tot_metric:,.2f}",
                first_num_col or "Primary Metric",
                c_blue,
            ),
            (
                "AVERAGE / MEAN",
                f"${avg_metric:,.2f}" if avg_metric > 1000 else f"{avg_metric:,.2f}",
                "Baseline Performance",
                c_emerald,
            ),
            (
                "RECORDS EVALUATED",
                f"{num_rows:,}",
                f"{len(table_headers)} Dimensions Analyzed",
                c_accent,
            ),
        ]

        for i, (kpi_title, kpi_val, kpi_sub, kpi_color) in enumerate(kpis):
            cx = Inches(0.8 + i * 4.04)
            card = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, card_y, card_w, card_h)
            card.fill.solid()
            card.fill.fore_color.rgb = c_card_bg
            card.line.color.rgb = c_border
            card.line.width = Pt(1)

            stripe = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, card_y, card_w, Inches(0.1))
            stripe.fill.solid()
            stripe.fill.fore_color.rgb = kpi_color
            stripe.line.fill.background()

            ctf = card.text_frame
            ctf.margin_top = Inches(0.2)
            ctf.margin_left = Inches(0.3)
            p1 = ctf.paragraphs[0]
            p1.text = kpi_title
            p1.font.size = Pt(10)
            p1.font.bold = True
            p1.font.color.rgb = c_slate

            p2 = ctf.add_paragraph()
            p2.text = kpi_val
            p2.font.size = Pt(24)
            p2.font.bold = True
            p2.font.color.rgb = c_navy
            p2.space_before = Pt(4)

            p3 = ctf.add_paragraph()
            p3.text = kpi_sub
            p3.font.size = Pt(9.5)
            p3.font.color.rgb = c_slate
            p3.space_before = Pt(2)

        sum_box = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(3.3), Inches(11.733), Inches(3.6))
        sum_box.fill.solid()
        sum_box.fill.fore_color.rgb = c_card_bg
        sum_box.line.color.rgb = c_border

        stf = sum_box.text_frame
        stf.word_wrap = True
        stf.margin_left = Inches(0.4)
        stf.margin_top = Inches(0.3)
        sp0 = stf.paragraphs[0]
        sp0.text = "EXECUTIVE ANALYSIS & TAKEAWAYS"
        sp0.font.size = Pt(12)
        sp0.font.bold = True
        sp0.font.color.rgb = c_blue

        insight_lines = [
            line_txt.strip().lstrip("-*•# ").strip()
            for line_txt in executive_insights.splitlines()
            if line_txt.strip() and not line_txt.strip().startswith("#") and len(line_txt.strip()) > 15
        ]
        chosen_lines = insight_lines[:4] or [
            "Data structures and numerical balances conform to enterprise ledger specifications.",
            "Key drivers account for the dominant proportion of observed variance.",
            "Zero compliance drift or unverified data transformations detected in the audit log.",
            "Actionable recommendations prioritized for quarterly operational reviews.",
        ]
        for line_txt in chosen_lines:
            sp = stf.add_paragraph()
            sp.text = f"•   {line_txt}"
            sp.font.size = Pt(13)
            sp.font.color.rgb = c_navy
            sp.space_before = Pt(10)
            sp.line_spacing = 1.15

        # ── Slide 3: Native Editable PowerPoint Chart ────────────────────────
        s3 = prs.slides.add_slide(blank_layout)
        _add_slide_header(s3, "VISUAL ANALYTICS", f"Distribution Profile: {table_headers[0]}", 3)

        c_left = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.5), Inches(4.5), Inches(5.4))
        c_left.fill.solid()
        c_left.fill.fore_color.rgb = c_card_bg
        c_left.line.color.rgb = c_border
        ltf = c_left.text_frame
        ltf.word_wrap = True
        ltf.margin_left = Inches(0.3)
        ltf.margin_top = Inches(0.3)
        lp0 = ltf.paragraphs[0]
        lp0.text = "ANALYTIC PERSPECTIVES"
        lp0.font.size = Pt(12)
        lp0.font.bold = True
        lp0.font.color.rgb = c_blue

        lp1 = ltf.add_paragraph()
        lp1.text = f"•   Category dimension: '{table_headers[0]}' with {num_rows} evaluated segments."
        lp1.font.size = Pt(12)
        lp1.font.color.rgb = c_navy
        lp1.space_before = Pt(12)

        if first_num_col:
            lp2 = ltf.add_paragraph()
            lp2.text = f"•   Primary metric: '{first_num_col}' (Total: {tot_metric:,.2f})."
            lp2.font.size = Pt(12)
            lp2.font.color.rgb = c_navy
            lp2.space_before = Pt(10)

        lp3 = ltf.add_paragraph()
        lp3.text = "•   Native chart rendered via Microsoft Office Chart XML engine for full editing capability."
        lp3.font.size = Pt(12)
        lp3.font.color.rgb = c_navy
        lp3.space_before = Pt(10)

        chart_cats = [str(r[0])[:14] for r in table_rows[:8]] or ["Baseline"]
        chart_vals = []
        for r in table_rows[:8]:
            v = None
            for c_idx in range(1, len(table_headers)):
                if isinstance(r[c_idx], (int, float)):
                    v = float(r[c_idx])
                    break
            chart_vals.append(v if v is not None else 0.0)
        if not chart_vals:
            chart_vals = [0.0]

        chart_data = CategoryChartData()
        chart_data.categories = chart_cats
        chart_data.add_series(first_num_col or "Value", tuple(chart_vals))

        x, y, cx, cy = Inches(5.6), Inches(1.5), Inches(6.9), Inches(5.4)
        chart_shape = s3.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, cx, cy, chart_data)
        chart = chart_shape.chart
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False

        # ── Slide 4: Structured Data Breakdown Table ─────────────────────────
        s4 = prs.slides.add_slide(blank_layout)
        _add_slide_header(s4, "DATA BREAKDOWN", "Tabular Operations & Metrics Summary", 4)

        disp_headers = table_headers[:6] or ["Category", "Metric"]
        disp_rows = table_rows[:10] or [["No records to display", "-"]]
        t_rows = len(disp_rows) + 1
        t_cols = len(disp_headers)

        table_shape = s4.shapes.add_table(t_rows, t_cols, Inches(0.8), Inches(1.5), Inches(11.733), Inches(5.4))
        p_table = table_shape.table

        for c_idx, h_text in enumerate(disp_headers):
            cell = p_table.cell(0, c_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = c_navy
            cp = cell.text_frame.paragraphs[0]
            cp.text = str(h_text)
            cp.font.size = Pt(11)
            cp.font.bold = True
            cp.font.color.rgb = c_white
            cp.alignment = PP_ALIGN.CENTER

        for r_idx, r_data in enumerate(disp_rows, start=1):
            use_bg = RGBColor(241, 245, 249) if r_idx % 2 == 0 else c_white
            for c_idx in range(t_cols):
                cell = p_table.cell(r_idx, c_idx)
                cell.fill.solid()
                cell.fill.fore_color.rgb = use_bg
                val = r_data[c_idx] if c_idx < len(r_data) else ""
                cp = cell.text_frame.paragraphs[0]
                if isinstance(val, float):
                    cp.text = f"{val:,.2f}"
                    cp.alignment = PP_ALIGN.RIGHT
                elif isinstance(val, int):
                    cp.text = f"{val:,}"
                    cp.alignment = PP_ALIGN.RIGHT
                else:
                    cp.text = str(val or "-")
                    cp.alignment = PP_ALIGN.LEFT if c_idx == 0 else PP_ALIGN.CENTER
                cp.font.size = Pt(10)
                cp.font.color.rgb = c_navy

        # ── Slide 5: Strategic Next Steps ────────────────────────────────────
        s5 = prs.slides.add_slide(blank_layout)
        _add_slide_header(s5, "GOVERNANCE & NEXT STEPS", "Strategic Implementation Roadmap", 5)

        s5_card = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(11.733), Inches(4.5))
        s5_card.fill.solid()
        s5_card.fill.fore_color.rgb = c_card_bg
        s5_card.line.color.rgb = c_border

        c5_tf = s5_card.text_frame
        c5_tf.word_wrap = True
        c5_tf.margin_left = Inches(0.5)
        c5_tf.margin_top = Inches(0.4)

        steps = [
            ("PHASE 1: AUDIT & RECONCILIATION", "Review baseline variance deviations against financial ledger thresholds."),
            ("PHASE 2: EXECUTIVE DISSEMINATION", "Distribute styled reports and verified presentation decks to key stakeholders."),
            ("PHASE 3: CONTINUOUS MONITORING", "Incorporate automated anomaly detection into scheduled ingestion pipelines."),
            ("PHASE 4: POLICY ALIGNMENT", "Enforce dual-custody approval boundaries on all operational variances exceeding 15%."),
        ]

        for s_idx, (stitle, sdesc) in enumerate(steps):
            p_s = c5_tf.paragraphs[0] if s_idx == 0 else c5_tf.add_paragraph()
            p_s.text = f"■   {stitle}: {sdesc}"
            p_s.font.size = Pt(13)
            p_s.font.color.rgb = c_navy
            p_s.space_after = Pt(14)
            p_s.line_spacing = 1.15

        prs.save(str(output_path))
        file_size = output_path.stat().st_size

        meta = GeneratedFileMeta(
            file_id=fid,
            filename=filename,
            format="pptx",
            file_size=file_size,
            title=title,
            summary="Executive Data Presentation Deck with 5 slides & native charts.",
            download_url=f"/api/v1/generate/download/{filename}",
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            slide_or_page_count=5,
        )
        self._save_meta(meta)
        return output_path, meta

    def render_executive_data_report(
        self,
        title: str,
        subtitle: str,
        table_headers: list[str],
        table_rows: list[list[Any]],
        executive_insights: str,
        classification: str = "INTERNAL",
        file_id: str | None = None,
    ) -> tuple[Path, GeneratedFileMeta]:
        """
        Builds a publication-quality PDF report with:
        - Security clearance badge
        - Executive Summary callout box
        - ReportLab Vector VerticalBarChart for visual data representation
        - Formatted tabular data with alternate row fills
        - Actionable recommendations
        """
        fid = file_id or str(uuid.uuid4())[:12]
        sanitized_title = re.sub(r"[^\w\-]", "_", title)[:40].strip("_") or "data_report"
        filename = f"{fid}_{sanitized_title}.pdf"
        output_path = self.storage_dir / filename

        def _esc(txt: Any) -> str:
            if not txt:
                return ""
            return str(txt).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=40,
            rightMargin=40,
            topMargin=45,
            bottomMargin=45,
        )
        styles = getSampleStyleSheet()

        c_primary = colors.HexColor("#1E293B")
        c_blue = colors.HexColor("#2563EB")
        c_muted = colors.HexColor("#64748B")
        c_border = colors.HexColor("#CBD5E1")
        c_callout_bg = colors.HexColor("#F8FAFC")

        title_style = ParagraphStyle("DTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=c_primary, spaceAfter=4)
        subtitle_style = ParagraphStyle("DSub", parent=styles["Normal"], fontName="Helvetica", fontSize=10.5, leading=14, textColor=c_muted, spaceAfter=12)
        h1_style = ParagraphStyle("DSecH1", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=c_blue, spaceBefore=10, spaceAfter=6)
        body_style = ParagraphStyle("DBodyD", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=13, textColor=c_primary)
        callout_style = ParagraphStyle("DCalloutD", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=13, textColor=colors.HexColor("#334155"))

        story: list[Any] = []

        # 1. Classification & Title
        badge_p = Paragraph(f"<b>CLASSIFICATION: {_esc(classification.upper())}</b>", ParagraphStyle("B", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, alignment=1))
        badge_table = Table([[badge_p]], colWidths=[140], rowHeights=[18])
        badge_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c_blue),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(badge_table)
        story.append(Spacer(1, 6))

        story.append(Paragraph(_esc(title), title_style))
        if subtitle:
            story.append(Paragraph(_esc(subtitle), subtitle_style))

        # Metadata row
        meta_table = Table([[
            Paragraph(f"<b>Date:</b> {datetime.date.today().strftime('%B %d, %Y')}", body_style),
            Paragraph(f"<b>Records:</b> {len(table_rows):,}", body_style),
            Paragraph("<b>Platform:</b> ServerGen AI Suite", body_style),
        ]], colWidths=[180, 160, 192])
        meta_table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1, c_border),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # 2. Executive Summary Box
        sum_title = Paragraph("<b>EXECUTIVE ANALYSIS & INSIGHTS</b>", h1_style)
        sum_body = Paragraph(_esc(executive_insights.replace("\n", "<br/>")), callout_style)
        sum_table = Table([[[sum_title, Spacer(1, 4), sum_body]]], colWidths=[532])
        sum_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c_callout_bg),
            ("BOX", (0, 0), (-1, -1), 1, c_border),
            ("LINEBEFORE", (0, 0), (0, -1), 3.5, c_blue),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(sum_table)
        story.append(Spacer(1, 12))

        # 3. Vector Chart
        chart_cats = [str(r[0])[:12] for r in table_rows[:6]]
        chart_vals: list[float] = []
        for r in table_rows[:6]:
            v = 0.0
            for c_idx in range(1, len(table_headers)):
                if isinstance(r[c_idx], (int, float)):
                    v = float(r[c_idx])
                    break
            chart_vals.append(v)

        if chart_cats and any(chart_vals):
            story.append(Paragraph("<b>DATA DISTRIBUTION PROFILE</b>", h1_style))
            d = Drawing(532, 130)
            chart = VerticalBarChart()
            chart.x = 40
            chart.y = 20
            chart.height = 90
            chart.width = 460
            chart.data = [chart_vals]
            chart.categoryAxis.categoryNames = chart_cats
            chart.categoryAxis.labels.fontSize = 7.5
            chart.categoryAxis.labels.dy = -10
            chart.bars[0].fillColor = c_blue
            d.add(chart)
            story.append(d)
            story.append(Spacer(1, 10))

        # 4. Data Table
        story.append(Paragraph("<b>DETAILED OPERATIONS BREAKDOWN</b>", h1_style))
        disp_h = table_headers[:6]
        disp_r = table_rows[:15]
        col_w = 532 / len(disp_h)
        tbl_data = [[Paragraph(f"<b>{_esc(h)}</b>", ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white, alignment=1)) for h in disp_h]]

        for _r_idx, r in enumerate(disp_r):
            row_cells = []
            for c_idx in range(len(disp_h)):
                v = r[c_idx] if c_idx < len(r) else ""
                txt = f"{v:,.2f}" if isinstance(v, float) else (f"{v:,}" if isinstance(v, int) else str(v or "-"))
                align = 2 if isinstance(v, (int, float)) else (0 if c_idx == 0 else 1)
                row_cells.append(Paragraph(_esc(txt), ParagraphStyle("TD", fontName="Helvetica", fontSize=8, textColor=c_primary, alignment=align)))
            tbl_data.append(row_cells)

        rep_table = Table(tbl_data, colWidths=[col_w] * len(disp_h))
        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), c_primary),
            ("GRID", (0, 0), (-1, -1), 0.5, c_border),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for r_idx in range(1, len(tbl_data)):
            if r_idx % 2 == 0:
                t_style.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#F1F5F9")))
        rep_table.setStyle(TableStyle(t_style))
        story.append(rep_table)

        doc.build(story, canvasmaker=NumberedCanvas)
        file_size = output_path.stat().st_size

        meta = GeneratedFileMeta(
            file_id=fid,
            filename=filename,
            format="pdf",
            file_size=file_size,
            title=title,
            summary=f"Executive Data Report PDF with vector chart and {len(disp_r)} records.",
            download_url=f"/api/v1/generate/download/{filename}",
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            slide_or_page_count=1,
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
                max_tokens=2500,
                temperature=0.25,
            )
            response = await asyncio.wait_for(provider.generate(req), timeout=60.0)
            doc_data = self._parse_report_json(response.content)
        except Exception as exc:
            logger.warning("Local LLM report generation warning: %s. Using heuristic synthesizer.", exc)

        if not doc_data or not doc_data.sections:
            doc_data = self._heuristic_report_fallback(prompt, classification, context=context)

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
        if start != -1 and end != -1 and end > start:
            json_str = cleaned[start : end + 1]
            try:
                parsed = json.loads(json_str)
                return ReportDocument(**parsed)
            except Exception:
                try:
                    cleaned_commas = re.sub(r",\s*([}\]])", r"\1", json_str)
                    parsed = json.loads(cleaned_commas)
                    return ReportDocument(**parsed)
                except Exception as exc:
                    logger.debug("JSON parse failed: %s", exc)
        return None

    def _heuristic_report_fallback(
        self, prompt: str, classification: str, context: str = ""
    ) -> ReportDocument:
        """Constructs a rich executive report fallback when LLM output is non-JSON."""
        clean_title = prompt.split("\n")[0][:70].strip() or "Enterprise System Assessment"
        extracted = self._extract_insights_from_context(context)

        exec_summary = (
            context[:350].strip()
            if len(context.strip()) > 80
            else (
                f"This document provides an authoritative evaluation of '{clean_title}'. "
                "The analysis synthesizes zero-trust architectural principles, localized on-premise execution, "
                "and automated governance policies to ensure verified, compliance-ready enterprise performance."
            )
        )

        sec1_bullets = extracted[:3] if len(extracted) >= 3 else [
            "Zero external telemetry or data egress during query and generation processing.",
            "Strict Role-Based Access Control enforcing clearance from Public to Restricted.",
            "Deterministic policy checks preceding all model and tool executions.",
        ]

        sec2_bullets = extracted[3:6] if len(extracted) >= 6 else [
            "Automated risk scoring based on keyword detection and declared data sensitivity.",
            "Cryptographic SHA-256 audit ledger recording actor, action, and decision.",
            "Immutable document versioning preventing unauthorized modification.",
        ]

        sec3_bullets = extracted[6:9] if len(extracted) >= 9 else [
            "Execute automated integration verification across all 5 core security subsystems.",
            "Regularly reindex departmental document repositories to maintain semantic accuracy.",
            "Review pending approvals and ledger event sequences on a weekly cadence.",
        ]

        recs = extracted[9:12] if len(extracted) >= 12 else [
            "Deploy local LLM runtime (Ollama) with verified hardware resource allocations.",
            "Enforce dual-custody approvals for any infrastructure modification or sensitive export.",
            "Perform scheduled audit ledger verification to validate cryptographic chain integrity.",
        ]

        return ReportDocument(
            title=clean_title,
            subtitle="Executive Technical Report & Operational Analysis",
            classification=classification,
            author="ServerGen AI Local Knowledge Engine",
            executive_summary=exec_summary,
            sections=[
                ReportSection(
                    heading="1. Operational Scope & Architecture Overview",
                    content=(
                        "Modern enterprise automation demands strict isolation between untrusted input and "
                        "execution runtimes. All operations must adhere to verified access boundaries without "
                        "relying on external public cloud APIs."
                    ),
                    bullet_points=sec1_bullets,
                    key_metric="100% On-Premise Air-Gapped Operation",
                ),
                ReportSection(
                    heading="2. Security Controls & Dual-Custody Approval",
                    content=(
                        "System modifications and sensitive data access require multi-layered policy evaluations. "
                        "When tasks exceed acceptable autonomous thresholds, dual-custody approval workflows "
                        "halt execution pending authorized review."
                    ),
                    bullet_points=sec2_bullets,
                    key_metric="Cryptographic Tamper-Evidence Ledger",
                ),
                ReportSection(
                    heading="3. Strategic Recommendations & Verification",
                    content=(
                        "To maximize organizational value, operations must be continuously measured against "
                        "established safety criteria. Regular regression checks and verification suites provide "
                        "objective confidence in operational stability."
                    ),
                    bullet_points=sec3_bullets,
                    key_metric="Zero Compliance Drift",
                ),
            ],
            recommendations=recs,
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

        def _esc(txt: Any, allow_tags: bool = True) -> str:
            if not txt:
                return ""
            t = str(txt).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            escaped = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if allow_tags:
                for tag in ("b", "/b", "i", "/i", "strong", "/strong", "em", "/em", "u", "/u"):
                    escaped = escaped.replace(f"&lt;{tag}&gt;", f"<{tag}>")
            return escaped

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
            f"<b>CLASSIFICATION: {_esc(doc_data.classification.upper())}</b>",
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
        story.append(Paragraph(_esc(doc_data.title), title_style))
        if doc_data.subtitle:
            story.append(Paragraph(_esc(doc_data.subtitle), subtitle_style))

        # Metadata table (Author, Date, System)
        meta_data = [
            [
                Paragraph(f"<b>Author:</b> {_esc(doc_data.author)}", body_style),
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
            summary_body = Paragraph(_esc(doc_data.executive_summary), callout_style)
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
            story.append(Spacer(1, 10))
            kpi_table_data = [
                [
                    Paragraph("<b>DATA SECURITY</b><br/><font color='#2563EB' size='10'><b>100% On-Premise</b></font><br/><font color='#64748B' size='7.5'>Zero External Cloud Egress</font>", styles["Normal"]),
                    Paragraph(f"<b>CLEARANCE CEILING</b><br/><font color='#10B981' size='10'><b>{_esc(doc_data.classification.upper())}</b></font><br/><font color='#64748B' size='7.5'>Role Vault Segregated</font>", styles["Normal"]),
                    Paragraph("<b>AUDIT INTEGRITY</b><br/><font color='#7C3AED' size='10'><b>SHA-256 Chained</b></font><br/><font color='#64748B' size='7.5'>Tamper-Evident Ledger</font>", styles["Normal"]),
                ]
            ]
            kpi_pdf_table = Table(kpi_table_data, colWidths=[177, 177, 178])
            kpi_pdf_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 1, c_border),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, c_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ])
            )
            story.append(kpi_pdf_table)
            story.append(Spacer(1, 14))

        # ?? 3. Content Sections ?????????????????????????????????????????????
        for sec in doc_data.sections:
            sec_elements: list[Any] = [Paragraph(_esc(sec.heading), h1_style)]

            if sec.content:
                sec_elements.append(Paragraph(_esc(sec.content), body_style))

            for bp in sec.bullet_points:
                bp_str = str(bp).strip()
                m_bp = re.match(r"^(\*\*.*?\*\*|[A-Za-z0-9\s]{3,28}:)(.*)$", bp_str)
                if m_bp:
                    lead = m_bp.group(1).replace("**", "").strip()
                    if not lead.endswith(":"):
                        lead += ":"
                    body = m_bp.group(2).strip()
                    sec_elements.append(Paragraph(f"&bull;  <b>{_esc(lead)}</b> {_esc(body)}", bullet_style))
                else:
                    sec_elements.append(Paragraph(f"&bull;  {_esc(bp_str)}", bullet_style))

            if sec.key_metric:
                metric_p = Paragraph(
                    f"<b>KEY FINDING / BENCHMARK:</b> {_esc(sec.key_metric)}",
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
                    Paragraph(f"<b>[{idx}]</b>  {_esc(rec)}", bullet_style)
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
