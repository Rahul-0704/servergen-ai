"""
ServerGen AI — Human-Grade Architectural System Diagrams PDF Generator.

Produces professional, high-resolution, human-engineered UML diagrams:
5.1 Data Flow Diagram (DFD Level 1)
5.2 Use Case Diagram
5.3 Activity Diagram (with 5 Enterprise Swimlanes)
5.4 Class Diagram (3-Compartment UML Domain Models)
5.5 Sequence Diagram (Lifelines with Activation Bars)
5.6 Collaboration Diagram (Spatial Object Interactions)

Compiles diagrams into an authoritative architectural specification PDF:
storage/generated/ServerGen_AI_System_Architecture_and_Design_Diagrams.pdf
"""

from __future__ import annotations

import datetime
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image as RLImage,
)
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Canvas settings (Supersampled 2400x1400 -> Downscaled 1200x700 for crisp anti-aliasing)
RAW_W, RAW_H = 2400, 1400
FINAL_W, FINAL_H = 1200, 700

# Palette - Corporate Slate & Indigo
C_BG = (255, 255, 255)
C_DARK = (15, 23, 42)         # Slate 900
C_SLATE = (30, 41, 59)        # Slate 800
C_MUTED = (100, 116, 139)     # Slate 500
C_LIGHT_BG = (248, 250, 252)  # Slate 50
C_BORDER = (203, 213, 225)    # Slate 300
C_BORDER_DARK = (71, 85, 105) # Slate 600

C_BLUE = (37, 99, 235)        # Blue 600
C_BLUE_LIGHT = (239, 246, 255) # Blue 50
C_BLUE_BORDER = (147, 197, 253) # Blue 300

C_GREEN = (5, 150, 105)       # Emerald 600
C_GREEN_LIGHT = (236, 253, 245) # Emerald 50
C_GREEN_BORDER = (110, 231, 183) # Emerald 300

C_AMBER = (217, 119, 6)       # Amber 600
C_AMBER_LIGHT = (254, 243, 199) # Amber 100
C_AMBER_BORDER = (252, 211, 77) # Amber 300

C_PURPLE = (124, 58, 237)     # Violet 600
C_PURPLE_LIGHT = (245, 243, 255) # Violet 50
C_PURPLE_BORDER = (196, 181, 253) # Violet 300

C_WHITE = (255, 255, 255)

# Fonts
try:
    F_SUPER = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 36)
    F_TITLE = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 28)
    F_HEAD = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
    F_SUB = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 19)
    F_BODY = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)
    F_SMALL = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
    F_CODE = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 16)
except Exception:
    F_SUPER = ImageFont.load_default()
    F_TITLE = ImageFont.load_default()
    F_HEAD = ImageFont.load_default()
    F_SUB = ImageFont.load_default()
    F_BODY = ImageFont.load_default()
    F_SMALL = ImageFont.load_default()
    F_CODE = ImageFont.load_default()


def draw_header_banner(draw: ImageDraw.ImageDraw, section_num: str, title: str, subtitle: str) -> None:
    draw.rectangle([0, 0, RAW_W, 90], fill=C_DARK)
    draw.text((45, 25), f"{section_num}  |  {title.upper()}", fill=C_WHITE, font=F_HEAD)
    bbox = F_SUB.getbbox(subtitle)
    tw = bbox[2] - bbox[0]
    draw.text((RAW_W - tw - 45, 28), subtitle, fill=(148, 163, 184), font=F_SUB)
    draw.rectangle([0, 90, RAW_W, 95], fill=C_BLUE)


def draw_orthogonal_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    color: tuple[int, int, int] = C_SLATE,
    width: int = 3,
    label: str = "",
    label_offset: tuple[float, float] = (0, 0),
) -> None:
    if len(points) < 2:
        return
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color, width=width)

    # Arrowhead at last segment
    p_prev = points[-2]
    p_last = points[-1]
    dx = p_last[0] - p_prev[0]
    dy = p_last[1] - p_prev[1]
    angle = math.atan2(dy, dx)
    arrow_len = 16
    arrow_w = 8
    p1 = (
        p_last[0] - arrow_len * math.cos(angle) + arrow_w * math.sin(angle),
        p_last[1] - arrow_len * math.sin(angle) - arrow_w * math.cos(angle),
    )
    p2 = (
        p_last[0] - arrow_len * math.cos(angle) - arrow_w * math.sin(angle),
        p_last[1] - arrow_len * math.sin(angle) + arrow_w * math.cos(angle),
    )
    draw.polygon([p_last, p1, p2], fill=color)

    if label:
        mid_idx = len(points) // 2
        lx = (points[mid_idx - 1][0] + points[mid_idx][0]) / 2 + label_offset[0]
        ly = (points[mid_idx - 1][1] + points[mid_idx][1]) / 2 + label_offset[1] - 22
        # Text background
        t_box = F_SMALL.getbbox(label)
        tw = t_box[2] - t_box[0]
        th = t_box[3] - t_box[1]
        draw.rectangle([lx - 4, ly - 2, lx + tw + 4, ly + th + 4], fill=C_WHITE, outline=C_BORDER)
        draw.text((lx, ly), label, fill=color, font=F_SMALL)


def draw_clean_box(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    desc: str = "",
    fill: tuple[int, int, int] = C_BLUE_LIGHT,
    border: tuple[int, int, int] = C_BLUE,
    radius: int = 10,
    tag: str = "",
) -> None:
    # Soft shadow
    draw.rounded_rectangle([x + 3, y + 3, x + w + 3, y + h + 3], radius=radius, fill=(241, 245, 249))
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=border, width=3)

    if tag:
        t_box = F_SMALL.getbbox(tag)
        tw = t_box[2] - t_box[0]
        draw.rounded_rectangle([x + 16, y - 10, x + 24 + tw, y + 12], radius=4, fill=border)
        draw.text((x + 20, y - 8), tag, fill=C_WHITE, font=F_SMALL)

    # Title
    t_box = F_HEAD.getbbox(title)
    tw = t_box[2] - t_box[0]
    draw.text((x + (w - tw) / 2, y + (14 if desc else (h - 26) / 2)), title, fill=C_DARK, font=F_HEAD)

    if desc:
        d_box = F_BODY.getbbox(desc)
        dw = d_box[2] - d_box[0]
        draw.text((x + (w - dw) / 2, y + h - 34), desc, fill=C_MUTED, font=F_BODY)


# ── 1. Data Flow Diagram (DFD) — Level 1 ────────────────────────────────────
def build_dfd_image(output_path: Path) -> None:
    img = Image.new("RGB", (RAW_W, RAW_H), C_BG)
    draw = ImageDraw.Draw(img)

    draw_header_banner(
        draw, "5.1", "Data Flow Diagram (Level 1)", "Logical Information Flow & Boundary Isolations"
    )

    # Top: External Entities
    draw_clean_box(draw, 80, 160, 320, 110, "External User / Client", "Web UI / Developer CLI", fill=C_BLUE_LIGHT, border=C_BLUE, tag="ENTITY")
    draw_clean_box(draw, 1040, 160, 320, 110, "Enterprise File Storage", "Local Docs (PDF / TXT / MD)", fill=C_GREEN_LIGHT, border=C_GREEN, tag="ENTITY")
    draw_clean_box(draw, 2000, 160, 320, 110, "Local Ollama LLM Runtime", "llama3.2:3b On-Premise", fill=C_PURPLE_LIGHT, border=C_PURPLE, tag="ENTITY")

    # Center: Core Processes (1.0 to 6.0)
    draw_clean_box(draw, 80, 430, 360, 120, "1.0 Auth & Session Engine", "Argon2id + JWT + Refresh Family", fill=C_BLUE_LIGHT, border=C_BLUE, tag="PROCESS")
    draw_clean_box(draw, 640, 430, 380, 120, "2.0 Zero-Trust Policy Engine", "Clearance Ceiling & Risk Check", fill=C_AMBER_LIGHT, border=C_AMBER, tag="PROCESS")
    draw_clean_box(draw, 1220, 430, 380, 120, "3.0 Hybrid RAG Retriever", "Vector Cosine + BM25 RRF Ranker", fill=C_GREEN_LIGHT, border=C_GREEN, tag="PROCESS")
    draw_clean_box(draw, 1800, 430, 380, 120, "4.0 Task & Doc Orchestrator", "Prompt Synthesis & Tool Registry", fill=C_PURPLE_LIGHT, border=C_PURPLE, tag="PROCESS")

    draw_clean_box(draw, 640, 720, 380, 120, "5.0 Dual-Custody Interceptor", "Manager Approval Ticket Review", fill=C_AMBER_LIGHT, border=C_AMBER, tag="PROCESS")
    draw_clean_box(draw, 1220, 720, 380, 120, "6.0 Ingestion & Chunker", "Text Chunking & Vectorization", fill=C_GREEN_LIGHT, border=C_GREEN, tag="PROCESS")
    draw_clean_box(draw, 1800, 720, 380, 120, "7.0 Doc & Slide Studio", "16:9 PPTX Decks & Corporate PDF", fill=C_BLUE_LIGHT, border=C_BLUE, tag="PROCESS")

    # Bottom: Data Stores (Open-ended DFD bars)
    def draw_data_store(x: float, y: float, w: float, h: float, store_id: str, name: str) -> None:
        draw.rectangle([x, y, x + w, y + h], fill=C_LIGHT_BG, outline=None)
        draw.line([(x, y), (x + w, y)], fill=C_DARK, width=3)
        draw.line([(x, y + h), (x + w, y + h)], fill=C_DARK, width=3)
        draw.line([(x, y), (x, y + h)], fill=C_DARK, width=3)
        draw.text((x + 18, y + 16), f"[{store_id}]", fill=C_BLUE, font=F_HEAD)
        draw.text((x + 90, y + 16), name, fill=C_DARK, font=F_HEAD)

    draw_data_store(80, 1020, 480, 75, "D1", "User Accounts & Role Permissions DB")
    draw_data_store(660, 1020, 480, 75, "D2", "Document Chunks & Vector Embedding Store")
    draw_data_store(1240, 1020, 480, 75, "D3", "Dual-Custody Approval Tickets Ledger")
    draw_data_store(1820, 1020, 480, 75, "D4", "SHA-256 Tamper-Evident Audit Ledger")

    # Data Flow Connectors (Orthogonal lines)
    draw_orthogonal_arrow(draw, [(240, 270), (240, 430)], C_BLUE, label="1. Credentials [user, pass]")
    draw_orthogonal_arrow(draw, [(240, 550), (240, 1020)], C_SLATE, label="Validate Hash")
    draw_orthogonal_arrow(draw, [(440, 490), (640, 490)], C_BLUE, label="2. AuthContext [role, ceiling]")
    draw_orthogonal_arrow(draw, [(830, 550), (830, 720)], C_AMBER, label="3. Escalate High Risk")
    draw_orthogonal_arrow(draw, [(830, 840), (1240, 1040)], C_AMBER, label="Ticket State")
    draw_orthogonal_arrow(draw, [(1020, 490), (1220, 490)], C_BLUE, label="4. Cleared Query Scope")
    draw_orthogonal_arrow(draw, [(1410, 550), (1140, 1040)], C_GREEN, label="Cosine Similarity Match")
    draw_orthogonal_arrow(draw, [(1200, 270), (1410, 430)], C_GREEN, label="Ingest Files")
    draw_orthogonal_arrow(draw, [(1600, 490), (1800, 490)], C_GREEN, label="5. Ranked Chunks & Citations")
    draw_orthogonal_arrow(draw, [(2020, 430), (2160, 270)], C_PURPLE, label="6. Inference Request")
    draw_orthogonal_arrow(draw, [(2160, 270), (2080, 430)], C_PURPLE, label="Raw Model Tokens")
    draw_orthogonal_arrow(draw, [(1990, 550), (1990, 720)], C_BLUE, label="Export Request")
    draw_orthogonal_arrow(draw, [(1990, 840), (1990, 1020)], C_DARK, label="7. Log SHA-256 Chained Event")
    draw_orthogonal_arrow(draw, [(1800, 510), (440, 510), (260, 270)], C_BLUE, label="Verified Response & Download Link", label_offset=(-200, -20))

    img.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS).save(output_path, quality=95)


# ── 2. Use Case Diagram ─────────────────────────────────────────────────────
def build_use_case_image(output_path: Path) -> None:
    img = Image.new("RGB", (RAW_W, RAW_H), C_BG)
    draw = ImageDraw.Draw(img)

    draw_header_banner(
        draw, "5.2", "Use Case Diagram", "Role Entitlements & Autonomous Boundary Scopes"
    )

    # System Boundary Box
    draw.rounded_rectangle([440, 140, 1960, 1340], radius=16, fill=C_LIGHT_BG, outline=C_BLUE, width=3)
    draw.text((470, 160), "System Boundary: ServerGen AI Enterprise Platform", fill=C_BLUE, font=F_HEAD)

    # Actor Drawing
    def draw_human_actor(cx: float, cy: float, role_name: str, clearance: str, color: tuple[int, int, int]) -> None:
        draw.ellipse([cx - 24, cy - 65, cx + 24, cy - 17], outline=color, width=3)
        draw.line([(cx, cy - 17), (cx, cy + 35)], fill=color, width=3)
        draw.line([(cx - 36, cy), (cx + 36, cy)], fill=color, width=3)
        draw.line([(cx, cy + 35), (cx - 26, cy + 75)], fill=color, width=3)
        draw.line([(cx, cy + 35), (cx + 26, cy + 75)], fill=color, width=3)
        # Role Pill
        bbox = F_HEAD.getbbox(role_name)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw / 2, cy + 85), role_name, fill=C_DARK, font=F_HEAD)
        cbox = F_SMALL.getbbox(f"({clearance})")
        cw = cbox[2] - cbox[0]
        draw.text((cx - cw / 2, cy + 112), f"({clearance})", fill=C_MUTED, font=F_SMALL)

    # Left Actors
    draw_human_actor(200, 260, "General Employee", "INTERNAL", C_BLUE)
    draw_human_actor(200, 560, "IT Operator", "CONFIDENTIAL", C_SLATE)
    draw_human_actor(200, 860, "Security Analyst", "CONFIDENTIAL", C_AMBER)
    draw_human_actor(200, 1140, "Department Manager", "RESTRICTED", C_GREEN)

    # Right Actors
    draw_human_actor(2200, 480, "System Administrator", "SUPERUSER", C_PURPLE)
    draw_human_actor(2200, 940, "Local Ollama LLM", "llama3.2:3b", C_DARK)

    # Use Case Ellipses
    ucs = [
        (650, 210, 480, 85, "UC1: Authenticate with Argon2id", "Rotate JWT Session Tokens"),
        (1300, 210, 480, 85, "UC2: Inspect Clearance Ceiling", "Zero-Trust RBAC Resolution"),
        (650, 360, 480, 85, "UC3: Query Knowledge Base (RAG)", "Hybrid Cosine & Keyword Search"),
        (1300, 360, 480, 85, "UC4: Ingest & Vectorize Files", "Air-Gapped Embedding Sync"),
        (650, 510, 480, 85, "UC5: Execute Verified AI Tasks", "Tool Execution & Diagnostics"),
        (1300, 510, 480, 85, "UC6: Dual-Custody Approval Ticket", "Intercept High-Risk Actions"),
        (650, 660, 480, 85, "UC7: Generate Widescreen 16:9 Deck", "Corporate PowerPoint (.pptx)"),
        (1300, 660, 480, 85, "UC8: Authorize / Reject Ticket", "Managerial Cryptographic Sign-Off"),
        (650, 810, 480, 85, "UC9: Generate Executive PDF Report", "Numbered Canvas & Section Outlines"),
        (1300, 810, 480, 85, "UC10: Export AI Answer to File", "One-Click Grounded Publication"),
        (650, 960, 480, 85, "UC11: Verify Audit Ledger Integrity", "Cryptographic SHA-256 Hash Chaining"),
        (1300, 960, 480, 85, "UC12: Manage Users, Roles & ACLs", "Enterprise Administration"),
    ]

    for x, y, w, h, title, sub in ucs:
        draw.ellipse([x, y, x + w, y + h], fill=C_WHITE, outline=C_BLUE, width=3)
        t_box = F_HEAD.getbbox(title)
        tw = t_box[2] - t_box[0]
        draw.text((x + (w - tw) / 2, y + 16), title, fill=C_DARK, font=F_HEAD)
        s_box = F_SMALL.getbbox(sub)
        sw = s_box[2] - s_box[0]
        draw.text((x + (w - sw) / 2, y + 46), sub, fill=C_MUTED, font=F_SMALL)

    # Actor to Use Case Connectors
    # Employee
    for target in [(650, 252), (650, 402), (650, 552), (650, 702), (650, 852), (1300, 852)]:
        draw.line([(310, 280), target], fill=C_BLUE, width=2)

    # Operator
    for target in [(650, 252), (1300, 402), (650, 552), (650, 702), (650, 852)]:
        draw.line([(310, 580), target], fill=C_SLATE, width=2)

    # Analyst
    for target in [(650, 252), (1300, 252), (650, 402), (650, 1002)]:
        draw.line([(310, 880), target], fill=C_AMBER, width=2)

    # Manager
    for target in [(650, 252), (650, 402), (1300, 552), (1300, 702)]:
        draw.line([(310, 1150), target], fill=C_GREEN, width=3)

    # Administrator
    for target in [(1780, 252), (1780, 402), (1780, 702), (1780, 1002)]:
        draw.line([(2080, 500), target], fill=C_PURPLE, width=2)

    # LLM
    for target in [(1130, 402), (1130, 552), (1130, 702), (1130, 852)]:
        draw.line([(2080, 940), target], fill=C_MUTED, width=2)

    img.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS).save(output_path, quality=95)


# ── 3. Activity Diagram — with 5 Enterprise Swimlanes ───────────────────────
def build_activity_image(output_path: Path) -> None:
    img = Image.new("RGB", (RAW_W, RAW_H), C_BG)
    draw = ImageDraw.Draw(img)

    draw_header_banner(
        draw, "5.3", "Activity Diagram", "Zero-Trust Operational Pipeline across 5 Architectural Swimlanes"
    )

    # 5 Swimlanes
    lanes = [
        ("Client / User Interface", 40, 480, C_BLUE_LIGHT),
        ("API Gateway & Policy Engine", 520, 480, C_AMBER_LIGHT),
        ("Retriever & Vector Store (RAG)", 1000, 480, C_GREEN_LIGHT),
        ("Local Ollama Engine & DocGen", 1480, 480, C_PURPLE_LIGHT),
        ("Audit Ledger & Governance", 1960, 400, C_LIGHT_BG),
    ]

    for title, x, w, bg in lanes:
        draw.rectangle([x, 110, x + w, RAW_H - 40], fill=bg, outline=C_BORDER, width=2)
        draw.rectangle([x, 110, x + w, 160], fill=C_SLATE)
        t_box = F_HEAD.getbbox(title)
        tw = t_box[2] - t_box[0]
        draw.text((x + (w - tw) / 2, 122), title, fill=C_WHITE, font=F_HEAD)

    # Nodes
    # Lane 1: Start
    draw.ellipse([250, 190, 310, 250], fill=C_DARK, outline=C_BLUE, width=4)
    draw.text((160, 260), "Start: Submit Prompt", fill=C_DARK, font=F_HEAD)

    draw_orthogonal_arrow(draw, [(280, 250), (280, 320), (760, 320)], C_BLUE, label="1. POST /execute")

    # Lane 2: Auth & Clearance
    draw_clean_box(draw, 560, 280, 400, 80, "Validate Session & Role", "Resolve Clearance Ceiling", fill=C_WHITE, border=C_BLUE)

    draw_orthogonal_arrow(draw, [(760, 360), (760, 430)], C_SLATE)

    # Decision 1: Clearance Exceeded?
    draw.polygon([(760, 430), (880, 490), (760, 550), (640, 490)], fill=C_AMBER_LIGHT, outline=C_AMBER, width=3)
    draw.text((680, 480), "Clearance OK?", fill=C_AMBER, font=F_HEAD)

    # No -> Withhold context
    draw_orthogonal_arrow(draw, [(640, 490), (280, 490), (280, 580)], C_AMBER, label="[No: Exceeds Role Ceiling]")
    draw_clean_box(draw, 80, 580, 400, 80, "Withhold Restricted Chunks", "Flag Zero-Trust Audit Banner", fill=C_AMBER_LIGHT, border=C_AMBER)
    draw_orthogonal_arrow(draw, [(280, 660), (280, 780), (1240, 780)], C_SLATE)

    # Yes -> Check Risk
    draw_orthogonal_arrow(draw, [(760, 550), (760, 620)], C_BLUE, label="[Yes: Authorized]")
    # Decision 2: High Risk?
    draw.polygon([(760, 620), (880, 680), (760, 740), (640, 680)], fill=C_AMBER_LIGHT, outline=C_AMBER, width=3)
    draw.text((690, 670), "High Risk?", fill=C_AMBER, font=F_HEAD)

    # Yes -> Dual Custody
    draw_orthogonal_arrow(draw, [(880, 680), (1050, 680), (1050, 860), (760, 860)], C_AMBER, label="[Yes: Mutating/Sensitive]")
    draw_clean_box(draw, 560, 820, 400, 80, "Intercept & Queue Approval", "Manager Sign-off Required", fill=C_AMBER_LIGHT, border=C_AMBER)

    # Safe -> Hybrid Search (Lane 3)
    draw_orthogonal_arrow(draw, [(760, 740), (760, 780), (1240, 780)], C_BLUE, label="[No: Safe]")
    draw_clean_box(draw, 1040, 740, 400, 80, "Hybrid Search Fusion", "Cosine Vector + BM25 RRF Rank", fill=C_GREEN_LIGHT, border=C_GREEN)

    # Lane 3 -> Lane 4: Model Inference
    draw_orthogonal_arrow(draw, [(1440, 780), (1520, 780)], C_GREEN, label="Grounded Evidence")
    draw_clean_box(draw, 1520, 740, 400, 80, "Synthesize with Local LLM", "llama3.2:3b On-Premise Engine", fill=C_PURPLE_LIGHT, border=C_PURPLE)

    # Lane 4: Format Document / Deck
    draw_orthogonal_arrow(draw, [(1720, 820), (1720, 920)], C_PURPLE)
    draw_clean_box(draw, 1520, 920, 400, 80, "Compile Output Artifacts", "16:9 PPTX Deck / Executive PDF", fill=C_BLUE_LIGHT, border=C_BLUE)

    # Lane 4 -> Lane 5: Audit Ledger
    draw_orthogonal_arrow(draw, [(1920, 960), (2160, 960), (2160, 1040)], C_DARK)
    draw_clean_box(draw, 1980, 1040, 360, 80, "Record Audit Event", "SHA-256 Chained Hash Commit", fill=C_DARK, border=C_BLUE)

    # Lane 5 -> Lane 1: Final Deliver
    draw_orthogonal_arrow(draw, [(2160, 1120), (2160, 1240), (280, 1240), (280, 1120)], C_GREEN, label="Deliver Verified Result & Download URL", label_offset=(400, 0))

    # Bullseye End Node
    draw.ellipse([250, 1060, 310, 1120], fill=C_WHITE, outline=C_DARK, width=3)
    draw.ellipse([262, 1072, 298, 1108], fill=C_DARK, outline=None)
    draw.text((150, 1130), "End: Task Verified & Audited", fill=C_DARK, font=F_HEAD)

    img.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS).save(output_path, quality=95)


# ── 4. Class Diagram — 3-Compartment Domain Model ───────────────────────────
def build_class_image(output_path: Path) -> None:
    img = Image.new("RGB", (RAW_W, RAW_H), C_BG)
    draw = ImageDraw.Draw(img)

    draw_header_banner(
        draw, "5.4", "Class Diagram", "Object-Oriented Subsystems, Typed Attributes & Methods"
    )

    def draw_uml_class(
        x: float, y: float, w: float, h: float,
        stereotype: str, name: str,
        attributes: list[str], methods: list[str],
        color: tuple[int, int, int] = C_BLUE,
    ) -> None:
        draw.rectangle([x + 4, y + 4, x + w + 4, y + h + 4], fill=(241, 245, 249))
        draw.rectangle([x, y, x + w, y + h], fill=C_WHITE, outline=color, width=3)

        # Header Compartment
        head_h = 55
        draw.rectangle([x, y, x + w, y + head_h], fill=color)
        s_box = F_SMALL.getbbox(f"<<{stereotype}>>")
        sw = s_box[2] - s_box[0]
        draw.text((x + (w - sw) / 2, y + 6), f"<<{stereotype}>>", fill=(226, 232, 240), font=F_SMALL)
        t_box = F_HEAD.getbbox(name)
        tw = t_box[2] - t_box[0]
        draw.text((x + (w - tw) / 2, y + 26), name, fill=C_WHITE, font=F_HEAD)

        # Attribute Compartment
        cy = y + head_h + 10
        for attr in attributes:
            draw.text((x + 14, cy), attr, fill=C_DARK, font=F_CODE)
            cy += 24

        draw.line([(x, cy + 4), (x + w, cy + 4)], fill=C_BORDER, width=2)
        cy += 14

        # Method Compartment
        for meth in methods:
            draw.text((x + 14, cy), meth, fill=C_SLATE, font=F_CODE)
            cy += 24

    # 1. Identity & Session
    draw_uml_class(60, 130, 480, 280, "entity", "User",
                   ["+ id: UUID", "+ username: string", "+ email: string", "+ hashed_password: str", "+ role_id: UUID"],
                   ["+ verify_password(plain): bool", "+ get_clearance_ceiling(): DataSensitivity"], C_BLUE)

    draw_uml_class(60, 450, 480, 220, "entity", "Role",
                   ["+ id: UUID", "+ name: string", "+ is_system_role: bool"],
                   ["+ has_permission(res, act): bool", "+ get_permissions(): list<Permission>"], C_BLUE)

    # 2. Security & Policy Engine
    draw_uml_class(600, 130, 540, 280, "service", "SecurityPolicyEngine",
                   ["- role_clearances: dict<Role, Sensitivity>", "- risk_keywords: list<str>", "- dual_custody_threshold: float"],
                   ["+ evaluate_policy(auth_ctx, action): PolicyDecision", "+ check_clearance(role, sens): bool", "+ evaluate_risk(prompt, tool): RiskLevel"], C_AMBER)

    draw_uml_class(600, 450, 540, 220, "entity", "ApprovalRequest",
                   ["+ id: UUID", "+ task_id: UUID", "+ requester_id: UUID", "+ status: ApprovalStatus", "+ reviewer_id: UUID"],
                   ["+ approve(reviewer, notes): void", "+ reject(reviewer, notes): void"], C_AMBER)

    # 3. AI Orchestration
    draw_uml_class(1200, 130, 540, 280, "orchestrator", "TaskOrchestrator",
                   ["- llm_provider: BaseModelProvider", "- tool_registry: ToolRegistry", "- retriever: RoleFilteredRetriever"],
                   ["+ execute_task(task_input, auth): TaskResult", "- enforce_guardrails(prompt, auth): bool", "- synthesize_output(context): str"], C_PURPLE)

    draw_uml_class(1200, 450, 540, 220, "provider", "OllamaProvider",
                   ["- base_url: string", "- default_model: string", "- timeout: float = 30.0"],
                   ["+ generate(req: LLMRequest): LLMResponse", "+ embed(text: string): list<float>", "+ health_check(): bool"], C_PURPLE)

    # 4. RAG Knowledge Store
    draw_uml_class(1800, 130, 540, 280, "retriever", "RoleFilteredRetriever",
                   ["- _ROLE_MAX_CLEARANCE: dict", "- _SENSITIVITY_ORDER: dict", "- store: KnowledgeStore"],
                   ["+ retrieve(query, auth, top_k): RAGResult", "- hybrid_rrf_rank(semantic, keyword): list", "- filter_clearance(chunks, ceiling): list"], C_GREEN)

    draw_uml_class(1800, 450, 540, 220, "entity", "DocumentChunk",
                   ["+ id: UUID", "+ document_id: UUID", "+ chunk_index: int", "+ content: string", "+ embedding_vector: list<float>"],
                   ["+ cosine_similarity(query_vec): float"], C_GREEN)

    # 5. Document Studio
    draw_uml_class(300, 720, 600, 280, "service", "DocumentGeneratorService",
                   ["- llm: OllamaProvider", "- storage_dir: Path"],
                   ["+ generate_presentation(prompt, slides): tuple", "+ generate_pdf(prompt, context): tuple", "- compile_pptx(deck, path): int", "- compile_pdf(doc, path): int"], C_BLUE)

    draw_uml_class(960, 720, 500, 280, "model", "PresentationDeck",
                   ["+ title: string", "+ classification: string", "+ slides: list<SlideContent>"],
                   ["+ add_slide(title, bullets): void", "+ to_widescreen_16_9(): void"], C_BLUE)

    # 6. Audit & Governance
    draw_uml_class(1520, 720, 600, 280, "governance", "AuditService",
                   ["- db: AsyncSession", "- last_event_hash: string"],
                   ["+ record(event, action, user_id, meta): AuditEvent", "+ verify_ledger_integrity(): bool", "- calculate_sha256(payload, prev): str"], C_DARK)

    # Orthogonal Relationships
    draw_orthogonal_arrow(draw, [(300, 410), (300, 450)], C_BLUE, label="1..* has_role")
    draw_orthogonal_arrow(draw, [(540, 240), (600, 240)], C_BLUE, label="validates")
    draw_orthogonal_arrow(draw, [(870, 410), (870, 450)], C_AMBER, label="creates ticket")
    draw_orthogonal_arrow(draw, [(1140, 240), (1200, 240)], C_AMBER, label="guards execution")
    draw_orthogonal_arrow(draw, [(1470, 410), (1470, 450)], C_PURPLE, label="dispatches")
    draw_orthogonal_arrow(draw, [(1740, 240), (1800, 240)], C_GREEN, label="queries")
    draw_orthogonal_arrow(draw, [(2070, 410), (2070, 450)], C_GREEN, label="1..* chunks")
    draw_orthogonal_arrow(draw, [(1350, 410), (600, 720)], C_BLUE, label="triggers DocGen")
    draw_orthogonal_arrow(draw, [(900, 860), (960, 860)], C_BLUE, label="builds")
    draw_orthogonal_arrow(draw, [(1470, 410), (1820, 720)], C_DARK, label="logs all tasks")

    img.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS).save(output_path, quality=95)


# ── 5. Sequence Diagram ─────────────────────────────────────────────────────
def build_sequence_image(output_path: Path) -> None:
    img = Image.new("RGB", (RAW_W, RAW_H), C_BG)
    draw = ImageDraw.Draw(img)

    draw_header_banner(
        draw, "5.5", "Sequence Diagram", "Interactive Chronological Lifelines & Verification Cycles"
    )

    lifelines = [
        (160, "User / Client", C_BLUE),
        (500, "FastAPI Gateway", C_BLUE),
        (840, "TaskOrchestrator", C_PURPLE),
        (1180, "SecurityPolicy", C_AMBER),
        (1520, "RoleRetriever", C_GREEN),
        (1860, "Ollama LLM", C_PURPLE),
        (2200, "AuditService", C_DARK),
    ]

    for lx, name, color in lifelines:
        draw_clean_box(draw, lx - 110, 120, 220, 60, name, fill=C_WHITE, border=color, radius=6)
        draw.line([(lx, 180), (lx, 1340)], fill=C_BORDER_DARK, width=2)
        # Activation Box
        draw.rectangle([lx - 12, 220, lx + 12, 1300], fill=C_LIGHT_BG, outline=color, width=2)

    steps = [
        (240, 160, 500, "1: POST /api/v1/ai/execute (query, sensitivity)", C_BLUE, False),
        (330, 500, 840, "2: dispatchTask(authContext, inputPayload)", C_BLUE, False),
        (420, 840, 1180, "3: evaluateClearance(role, sensitivity)", C_AMBER, False),
        (510, 1180, 840, "4: return Decision::ALLOW (Within Ceiling)", C_GREEN, True),
        (600, 840, 1520, "5: retrieve(query, authContext, top_k=4)", C_GREEN, False),
        (690, 1520, 1520, "6: hybrid_rrf_rank(semantic_cosine, keyword_bm25)", C_SLATE, False),
        (780, 1520, 840, "7: return GroundedEvidence [chunks, citations]", C_GREEN, True),
        (870, 840, 1860, "8: generate(prompt + RAG context, temp=0.3)", C_PURPLE, False),
        (960, 1860, 840, "9: return Synthesized Model Response", C_PURPLE, True),
        (1050, 840, 2200, "10: record(event, user_id, action, payload)", C_DARK, False),
        (1140, 2200, 840, "11: commit SHA-256 Chained Hash Entry", C_DARK, True),
        (1230, 840, 160, "12: HTTP 200 OK (verified answer + citations + exports)", C_BLUE, True),
    ]

    for y, x1, x2, label, color, is_dash in steps:
        if x1 == x2:
            # Self delegation loop
            draw.line([(x1 + 12, y), (x1 + 80, y)], fill=color, width=3)
            draw.line([(x1 + 80, y), (x1 + 80, y + 45)], fill=color, width=3)
            draw.line([(x1 + 80, y + 45), (x1 + 12, y + 45)], fill=color, width=3)
            draw_orthogonal_arrow(draw, [(x1 + 30, y + 45), (x1 + 12, y + 45)], color, width=3)
            draw.text((x1 + 95, y + 10), label, fill=color, font=F_BODY)
        else:
            if is_dash:
                # Dashed return line
                cx = x1 + (12 if x1 < x2 else -12)
                end_x = x2 + (-12 if x1 < x2 else 12)
                step = 16
                sign = 1 if end_x > cx else -1
                cur = cx
                while (cur < end_x if sign > 0 else cur > end_x):
                    nxt = cur + sign * (step - 6)
                    draw.line([(cur, y), (nxt, y)], fill=color, width=3)
                    cur = cur + sign * step
                draw_orthogonal_arrow(draw, [(end_x - sign * 15, y), (end_x, y)], color, width=3)
            else:
                draw_orthogonal_arrow(
                    draw,
                    [(x1 + (12 if x1 < x2 else -12), y), (x2 + (-12 if x1 < x2 else 12), y)],
                    color,
                    width=3,
                )

            lx = min(x1, x2) + abs(x2 - x1) * 0.15
            t_box = F_BODY.getbbox(label)
            tw = t_box[2] - t_box[0]
            draw.rectangle([lx - 4, y - 26, lx + tw + 4, y - 2], fill=C_WHITE, outline=C_BORDER)
            draw.text((lx, y - 24), label, fill=color, font=F_BODY)

    img.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS).save(output_path, quality=95)


# ── 6. Collaboration Diagram ────────────────────────────────────────────────
def build_collaboration_image(output_path: Path) -> None:
    img = Image.new("RGB", (RAW_W, RAW_H), C_BG)
    draw = ImageDraw.Draw(img)

    draw_header_banner(
        draw, "5.6", "Collaboration (Communication) Diagram", "Structural Object Meshes & Numbered Message Sequence"
    )

    # Spatial Object Nodes
    objects = {
        "UI": (120, 580, 280, 100, ":WebInterface", "Client SPA / Test Tool"),
        "API": (560, 260, 320, 100, ":FastAPIGateway", "Route Handler & Auth"),
        "ORCH": (1100, 580, 340, 100, ":TaskOrchestrator", "Task Execution Core"),
        "POL": (560, 900, 320, 100, ":SecurityPolicy", "Clearance & Risk Engine"),
        "RAG": (1100, 220, 340, 100, ":RoleRetriever", "Hybrid RRF Ranker"),
        "LLM": (1740, 260, 320, 100, ":OllamaProvider", "llama3.2:3b Local Engine"),
        "DOC": (1740, 580, 320, 100, ":DocGenService", "16:9 PPTX & PDF Studio"),
        "AUD": (1740, 900, 320, 100, ":AuditService", "SHA-256 Chained Hash"),
        "DB": (1100, 1140, 340, 100, ":DatabaseStore", "SQLite / Persistent Store"),
    }

    for key, (x, y, w, h, name, sub) in objects.items():
        draw_clean_box(
            draw, x, y, w, h, name, sub,
            fill=C_BLUE_LIGHT if key in ("API", "ORCH") else C_WHITE,
            border=C_BLUE if key in ("API", "ORCH") else C_SLATE,
        )

    # Links with numbered messages
    def draw_collab_link(
        p1: tuple[float, float], p2: tuple[float, float],
        forward_msg: str = "", back_msg: str = "",
        color: tuple[int, int, int] = C_SLATE,
    ) -> None:
        draw.line([p1, p2], fill=C_BORDER_DARK, width=3)
        mx = (p1[0] + p2[0]) / 2
        my = (p1[1] + p2[1]) / 2

        if forward_msg:
            t_box = F_BODY.getbbox(forward_msg + " >")
            tw = t_box[2] - t_box[0]
            draw.rectangle([mx - tw / 2 - 4, my - 28, mx + tw / 2 + 4, my - 6], fill=C_WHITE, outline=C_BORDER)
            draw.text((mx - tw / 2, my - 26), forward_msg + " >", fill=color, font=F_BODY)

        if back_msg:
            t_box = F_BODY.getbbox("< " + back_msg)
            tw = t_box[2] - t_box[0]
            draw.rectangle([mx - tw / 2 - 4, my + 6, mx + tw / 2 + 4, my + 28], fill=C_WHITE, outline=C_BORDER)
            draw.text((mx - tw / 2, my + 8), "< " + back_msg, fill=C_MUTED, font=F_BODY)

    # 1. UI <-> API
    draw_collab_link((380, 600), (580, 360), "1: submitTask(query, sens)", "8: returnResponse()", C_BLUE)

    # 2. API <-> ORCH
    draw_collab_link((880, 330), (1100, 580), "2: dispatch(authCtx, payload)", "", C_BLUE)

    # 3. ORCH <-> POL
    draw_collab_link((1100, 650), (880, 930), "3: checkClearance(role, sens)", "Decision::ALLOW", C_AMBER)

    # 4. ORCH <-> RAG
    draw_collab_link((1270, 580), (1270, 320), "4: retrieve(query, ceiling)", "EvidenceItems", C_GREEN)

    # 5. ORCH <-> LLM
    draw_collab_link((1440, 600), (1740, 340), "5: generate(prompt, context)", "RawModelTokens", C_PURPLE)

    # 6. ORCH <-> DOC
    draw_collab_link((1440, 630), (1740, 630), "6: compileDeckOrPdf(data)", "FileMetadata", C_BLUE)

    # 7. ORCH <-> AUD
    draw_collab_link((1440, 660), (1740, 920), "7: appendLedgerEvent()", "", C_DARK)

    # 8. AUD <-> DB
    draw_collab_link((1740, 980), (1440, 1160), "7.1: commitChainedHash()", "CommitOK", C_DARK)

    img.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS).save(output_path, quality=95)


# ── ReportLab Numbered Canvas for Dynamic Page Count ────────────────────────
class NumberedCanvas(canvas.Canvas):
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
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 34, letter[0] - 36, 34)
        self.drawString(36, 22, "ServerGen AI — Secure Enterprise Automation Platform (Architectural Specification)")
        self.drawRightString(letter[0] - 36, 22, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


# ── Compiler ────────────────────────────────────────────────────────────────
def compile_human_grade_pdf(storage_dir: Path) -> Path:
    storage_dir.mkdir(parents=True, exist_ok=True)
    images_dir = storage_dir / "human_diagrams"
    images_dir.mkdir(parents=True, exist_ok=True)

    dfd_path = images_dir / "5_1_dfd.png"
    use_case_path = images_dir / "5_2_use_case.png"
    activity_path = images_dir / "5_3_activity.png"
    class_path = images_dir / "5_4_class.png"
    seq_path = images_dir / "5_5_sequence.png"
    collab_path = images_dir / "5_6_collaboration.png"

    print("Building Human-Grade Diagram 5.1 (DFD)...")
    build_dfd_image(dfd_path)
    print("Building Human-Grade Diagram 5.2 (Use Case)...")
    build_use_case_image(use_case_path)
    print("Building Human-Grade Diagram 5.3 (Activity Swimlanes)...")
    build_activity_image(activity_path)
    print("Building Human-Grade Diagram 5.4 (3-Compartment Class)...")
    build_class_image(class_path)
    print("Building Human-Grade Diagram 5.5 (Sequence)...")
    build_sequence_image(seq_path)
    print("Building Human-Grade Diagram 5.6 (Collaboration)...")
    build_collaboration_image(collab_path)

    pdf_filename = "ServerGen_AI_System_Architecture_and_Design_Diagrams.pdf"
    pdf_path = storage_dir / pdf_filename

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=42,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )

    h1_style = ParagraphStyle(
        "SecH1",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#1D4ED8"),
        spaceBefore=4,
        spaceAfter=4,
    )

    body_style = ParagraphStyle(
        "SecBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )

    table_head = ParagraphStyle(
        "THead",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=colors.HexColor("#0F172A"),
    )
    table_cell = ParagraphStyle(
        "TCell",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )

    story: list[Any] = []

    # ── Cover Page Header ───────────────────────────────────────────────────
    badge_p = Paragraph(
        "<b>ENTERPRISE ARCHITECTURAL SPECIFICATION &bull; SOFTWARE DESIGN MODELS (5.1 - 5.6)</b>",
        ParagraphStyle("CoverBadge", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white, alignment=1),
    )
    badge_table = Table([[badge_p]], colWidths=[540], rowHeights=[20])
    badge_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(badge_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("ServerGen AI: System Architecture & Design Diagrams", title_style))
    story.append(
        Paragraph(
            "Formal Software Engineering Architectural Models for On-Premise Enterprise Automation: "
            "Data Flow (Level 1), Actor Entitlements (Use Case), Swimlane Workflows (Activity), "
            "Domain Schemas (Class), Interactive Lifelines (Sequence), and Object Meshes (Collaboration).",
            subtitle_style,
        )
    )

    meta_table = Table(
        [
            [
                Paragraph("<b>Author:</b> Rahul Raut & ServerGen Core Team", body_style),
                Paragraph(f"<b>Date:</b> {datetime.date.today().strftime('%B %d, %Y')}", body_style),
                Paragraph("<b>Classification:</b> RESTRICTED (Internal Arch)", body_style),
            ]
        ],
        colWidths=[210, 160, 170],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Diagram Sections with Engineering Breakdown Tables
    diagrams_meta = [
        (
            "5.1 Data Flow Diagram (DFD) — Level 1 Decomposition",
            dfd_path,
            "Traces the boundary-controlled data exchange across 3 external entities, 7 core processes, and 4 database stores.",
            [
                ["Component", "Architectural Role & Guarantees", "Primary Data Structures"],
                ["Processes 1.0 - 2.0", "Session management & local file vectorization", "Argon2id hashes, Cosine embeddings"],
                ["Processes 3.0 - 5.0", "Clearance ceiling gating & Dual-custody review", "Role ceilings, Approval UUID tickets"],
                ["Processes 6.0 - 7.0", "On-premise inference & SHA-256 hash chaining", "llama3.2:3b tokens, Audit ledger blocks"],
            ],
        ),
        (
            "5.2 Use Case Diagram — Role Entitlements & Access Boundaries",
            use_case_path,
            "Maps the complete interaction matrix across 6 enterprise actors and 12 operational use cases.",
            [
                ["Actor Role", "Permitted Operational Boundary", "Security Ceiling"],
                ["General Employee", "Query knowledge base, generate PPTX/PDF reports, execute safe tasks", "INTERNAL"],
                ["IT Operator", "Document ingestion, system diagnostics, performance probing", "CONFIDENTIAL"],
                ["Security Analyst", "Audit log inspection, cryptographic hash chain integrity checks", "CONFIDENTIAL"],
                ["Department Manager", "High-risk task authorization, dual-custody approval sign-off", "RESTRICTED"],
                ["Administrator", "User/role management, access control matrices, system governance", "SUPERUSER"],
            ],
        ),
        (
            "5.3 Activity Diagram — 5 Enterprise Swimlanes Pipeline",
            activity_path,
            "Details operational control passing across Client, Gateway, Retriever, Local LLM, and Governance swimlanes.",
            [
                ["Swimlane Phase", "Decision & Control Gate", "Outcome / Fallback"],
                ["Gateway Lane", "Clearance Ceiling vs Declared Sensitivity", "Withhold higher-classification chunks"],
                ["Policy Lane", "Risk Scoring & Mutating Tool Check", "Intercept & require dual-custody review"],
                ["RAG Lane", "Hybrid Cosine Vector + BM25 Keyword Search", "Reciprocal Rank Fusion (RRF) evidence"],
                ["Governance Lane", "SHA-256 Chained Hash Ledger Commit", "Cryptographic immutability verification"],
            ],
        ),
        (
            "5.4 Class Diagram — 3-Compartment Domain Model",
            class_path,
            "Object-oriented static structure showing typed attributes, methods, and relationships across 6 core subsystems.",
            [
                ["Subsystem", "Core Classes", "Key Responsibilities"],
                ["Identity & Access", "User, Role, Permission, RefreshToken", "Argon2id hashing, family token rotation"],
                ["Policy & Approvals", "SecurityPolicyEngine, ApprovalRequest", "Zero-trust clearance resolution, risk gating"],
                ["AI & Storage", "TaskOrchestrator, RoleFilteredRetriever, Chunk", "Hybrid vector retrieval, local Ollama LLM"],
                ["DocGen & Audit", "DocumentGeneratorService, AuditService", "16:9 PPTX decks, PDFs, SHA-256 ledger"],
            ],
        ),
        (
            "5.5 Sequence Diagram — Interactive Execution Lifelines",
            seq_path,
            "Chronological message sequence across 7 active lifelines from prompt dispatch to audit commit.",
            [
                ["Step Range", "Participating Lifelines", "Operational Transaction"],
                ["Steps 1 - 4", "Client -> Gateway -> Orchestrator -> Policy", "Task dispatch, clearance & risk validation"],
                ["Steps 5 - 7", "Orchestrator -> RoleRetriever", "Hybrid RRF evidence retrieval & citation assembly"],
                ["Steps 8 - 9", "Orchestrator -> Ollama LLM (llama3.2:3b)", "Local air-gapped inference & token streaming"],
                ["Steps 10 - 12", "Orchestrator -> AuditService -> Client", "SHA-256 hash commit & verified answer delivery"],
            ],
        ),
        (
            "5.6 Collaboration Diagram — Spatial Object Meshes",
            collab_path,
            "Numbered communication paths illustrating decoupled structural object collaboration without external cloud egress.",
            [
                ["Link Path", "Message Identifier & Method", "Architectural Isolation"],
                ["UI <-> Gateway", "1: submitTask() / 8: returnResponse()", "REST API JSON contract over HTTP/HTTPS"],
                ["Orchestrator <-> Policy", "3: checkClearance() / Decision::ALLOW", "Zero-trust boundary interception"],
                ["Orchestrator <-> Retriever", "4: retrieve() / EvidenceItems", "Role-filtered vector chunk isolation"],
                ["Orchestrator <-> Audit", "7: appendLedgerEvent() / 7.1: commit()", "Append-only cryptographic hash chaining"],
            ],
        ),
    ]

    for title, img_file, desc, table_rows in diagrams_meta:
        sec_elements: list[Any] = []
        sec_elements.append(Paragraph(title, h1_style))
        sec_elements.append(Paragraph(desc, body_style))
        sec_elements.append(Spacer(1, 2))

        # Diagram Image (High DPI downscaled)
        sec_elements.append(RLImage(str(img_file), width=540, height=315))
        sec_elements.append(Spacer(1, 6))

        # Engineering Breakdown Table
        formatted_table = []
        for r_idx, row in enumerate(table_rows):
            cell_style = table_head if r_idx == 0 else table_cell
            formatted_table.append([Paragraph(cell, cell_style) for cell in row])

        t = Table(formatted_table, colWidths=[130, 260, 150])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#CBD5E1")),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        sec_elements.append(t)
        sec_elements.append(Spacer(1, 6))

        story.append(KeepTogether(sec_elements))
        story.append(PageBreak())

    if story and isinstance(story[-1], PageBreak):
        story.pop()

    print("Compiling final human-grade architectural specification PDF...")
    doc.build(story, canvasmaker=NumberedCanvas)
    file_size = pdf_path.stat().st_size
    print(f"Generated PDF: {pdf_path} ({file_size} bytes)")

    # Update index_meta.json
    meta_file = storage_dir / "index_meta.json"
    records = []
    if meta_file.exists():
        try:
            with open(meta_file, encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            records = []

    file_meta = {
        "file_id": "sys-diagrams-501",
        "filename": pdf_filename,
        "format": "pdf",
        "file_size": file_size,
        "title": "ServerGen AI System Architecture & Design Diagrams (5.1 - 5.6)",
        "summary": "Formal Software Engineering Diagrams: DFD, Use Case, Activity Swimlanes, 3-Compartment Class, Sequence, and Collaboration Models.",
        "download_url": f"/api/v1/generate/download/{pdf_filename}",
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "slide_or_page_count": len(diagrams_meta) + 1,
    }

    records = [r for r in records if r.get("file_id") != file_meta["file_id"]]
    records.insert(0, file_meta)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(records[:100], f, indent=2)

    # Clean up intermediate raw image directory
    import shutil
    if images_dir.exists():
        shutil.rmtree(images_dir, ignore_errors=True)

    return pdf_path


if __name__ == "__main__":
    out_dir = Path("docs/diagrams").resolve()
    compile_human_grade_pdf(out_dir)
