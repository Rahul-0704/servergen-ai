"""
ServerGen AI — Comprehensive System Diagrams PDF Generator.

Generates high-resolution graphical software engineering diagrams:
5.1 Data Flow Diagram (DFD)
5.2 Use Case Diagram
5.3 Activity Diagram
5.4 Class Diagram
5.5 Sequence Diagram
5.6 Collaboration Diagram

Compiles all diagrams with technical descriptions into an executive PDF report:
storage/generated/ServerGen_AI_System_Architecture_and_Design_Diagrams.pdf
"""

from __future__ import annotations

import datetime
import json
import math
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Colors
C_BG = (255, 255, 255)
C_DARK = (15, 23, 42)      # Slate 900
C_NAVY = (30, 41, 59)      # Slate 800
C_BLUE = (37, 99, 235)     # Blue 600
C_BLUE_LIGHT = (239, 246, 255) # Blue 50
C_GREEN = (5, 150, 105)    # Emerald 600
C_GREEN_LIGHT = (236, 253, 245) # Emerald 50
C_AMBER = (217, 119, 6)    # Amber 600
C_AMBER_LIGHT = (255, 251, 235) # Amber 50
C_PURPLE = (124, 58, 237)  # Violet 600
C_PURPLE_LIGHT = (245, 243, 255) # Violet 50
C_GRAY = (100, 116, 139)   # Slate 500
C_GRAY_LIGHT = (241, 245, 249) # Slate 100
C_BORDER = (203, 213, 225) # Slate 300
C_WHITE = (255, 255, 255)

try:
    FONT_TITLE = ImageFont.truetype("arialbd.ttf", 20)
    FONT_HEAD = ImageFont.truetype("arialbd.ttf", 15)
    FONT_BODY = ImageFont.truetype("arial.ttf", 13)
    FONT_SMALL = ImageFont.truetype("arial.ttf", 11)
    FONT_CODE = ImageFont.truetype("cour.ttf", 11)
except Exception:
    FONT_TITLE = ImageFont.load_default()
    FONT_HEAD = ImageFont.load_default()
    FONT_BODY = ImageFont.load_default()
    FONT_SMALL = ImageFont.load_default()
    FONT_CODE = ImageFont.load_default()


def draw_arrow(draw: ImageDraw.ImageDraw, x1: float, y1: float, x2: float, y2: float,
               color: tuple[int, int, int] = C_GRAY, width: int = 2,
               label: str = "", label_pos: float = 0.5, font: ImageFont.ImageFont = FONT_SMALL) -> None:
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    dx = x2 - x1
    dy = y2 - y1
    angle = math.atan2(dy, dx)
    arrow_len = 10
    arrow_w = 5
    p1 = (x2 - arrow_len * math.cos(angle) + arrow_w * math.sin(angle),
          y2 - arrow_len * math.sin(angle) - arrow_w * math.cos(angle))
    p2 = (x2 - arrow_len * math.cos(angle) - arrow_w * math.sin(angle),
          y2 - arrow_len * math.sin(angle) + arrow_w * math.cos(angle))
    draw.polygon([(x2, y2), p1, p2], fill=color)

    if label:
        lx = x1 + dx * label_pos
        ly = y1 + dy * label_pos - 12
        draw.text((lx, ly), label, fill=color, font=font)


def draw_box(draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float,
             title: str, subtitle: str = "",
             fill: tuple[int, int, int] = C_BLUE_LIGHT,
             border: tuple[int, int, int] = C_BLUE,
             radius: int = 8) -> None:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=border, width=2)
    # Center text
    bbox = FONT_HEAD.getbbox(title)
    tw = bbox[2] - bbox[0]
    draw.text((x + (w - tw) / 2, y + (10 if subtitle else (h - 18) / 2)), title, fill=C_DARK, font=FONT_HEAD)
    if subtitle:
        sub_box = FONT_SMALL.getbbox(subtitle)
        sw = sub_box[2] - sub_box[0]
        draw.text((x + (w - sw) / 2, y + h - 22), subtitle, fill=C_GRAY, font=FONT_SMALL)


def draw_actor(draw: ImageDraw.ImageDraw, cx: float, cy: float, name: str,
               color: tuple[int, int, int] = C_DARK) -> None:
    # Head
    draw.ellipse([cx - 14, cy - 35, cx + 14, cy - 7], outline=color, width=2)
    # Body
    draw.line([(cx, cy - 7), (cx, cy + 20)], fill=color, width=2)
    # Arms
    draw.line([(cx - 20, cy + 3), (cx + 20, cy + 3)], fill=color, width=2)
    # Legs
    draw.line([(cx, cy + 20), (cx - 15, cy + 42)], fill=color, width=2)
    draw.line([(cx, cy + 20), (cx + 15, cy + 42)], fill=color, width=2)
    # Name
    bbox = FONT_HEAD.getbbox(name)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw / 2, cy + 48), name, fill=color, font=FONT_HEAD)


def draw_cylinder(draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float,
                  title: str, fill: tuple[int, int, int] = C_GRAY_LIGHT,
                  border: tuple[int, int, int] = C_GRAY) -> None:
    # Top ellipse
    draw.rectangle([x, y + 10, x + w, y + h - 10], fill=fill, outline=None)
    draw.line([(x, y + 10), (x, y + h - 10)], fill=border, width=2)
    draw.line([(x + w, y + 10), (x + w, y + h - 10)], fill=border, width=2)
    draw.ellipse([x, y + h - 20, x + w, y + h], fill=fill, outline=border, width=2)
    draw.ellipse([x, y, x + w, y + 20], fill=fill, outline=border, width=2)
    bbox = FONT_HEAD.getbbox(title)
    tw = bbox[2] - bbox[0]
    draw.text((x + (w - tw) / 2, y + (h - 16) / 2), title, fill=C_DARK, font=FONT_HEAD)


# ── 1. Data Flow Diagram (DFD) ──────────────────────────────────────────────
def generate_dfd_image(output_path: Path) -> None:
    img = Image.new("RGB", (1400, 850), C_WHITE)
    draw = ImageDraw.Draw(img)

    # Header Banner
    draw.rectangle([0, 0, 1400, 50], fill=C_DARK)
    draw.text((30, 14), "5.1 DATA FLOW DIAGRAM (DFD) — LEVEL 1 SYSTEM DECOMPOSITION", fill=C_WHITE, font=FONT_HEAD)
    draw.text((1050, 14), "ServerGen AI Enterprise Architecture", fill=C_BORDER, font=FONT_SMALL)

    # External Entities (Rectangles with shadow)
    draw_box(draw, 50, 120, 180, 70, "[Entity: User]", "Employee / Analyst", fill=C_BLUE_LIGHT, border=C_BLUE)
    draw_box(draw, 50, 480, 180, 70, "[Entity: Docs]", "Local Files (PDF/TXT)", fill=C_GREEN_LIGHT, border=C_GREEN)
    draw_box(draw, 1160, 320, 190, 70, "[Entity: Local LLM]", "Ollama llama3.2:3b", fill=C_PURPLE_LIGHT, border=C_PURPLE)

    # Core Processes (Rounded circles/capsules)
    draw_box(draw, 340, 120, 240, 70, "P1: Auth & Token Mgmt", "Argon2id + JWT + Refresh", fill=C_BLUE_LIGHT, border=C_BLUE)
    draw_box(draw, 340, 480, 240, 70, "P2: Ingestion & Chunker", "Parsing + Cosine Embed", fill=C_GREEN_LIGHT, border=C_GREEN)
    draw_box(draw, 680, 120, 250, 70, "P3: Zero-Trust Guardrails", "Clearance Ceiling + Risk", fill=C_AMBER_LIGHT, border=C_AMBER)
    draw_box(draw, 680, 290, 250, 70, "P4: Dual-Custody Approval", "Manager Ticket Review", fill=C_AMBER_LIGHT, border=C_AMBER)
    draw_box(draw, 680, 480, 250, 70, "P5: Hybrid RAG Retriever", "Cosine Vector + BM25 RRF", fill=C_GREEN_LIGHT, border=C_GREEN)
    draw_box(draw, 1020, 120, 260, 70, "P6: Task Orchestrator", "Tool Engine + DocGen", fill=C_BLUE_LIGHT, border=C_BLUE)
    draw_box(draw, 680, 680, 250, 70, "P7: Tamper-Evident Audit", "SHA-256 Ledger Chaining", fill=C_PURPLE_LIGHT, border=C_PURPLE)

    # Data Stores (Cylinders)
    draw_cylinder(draw, 340, 280, 240, 65, "D1: Users & Roles DB")
    draw_cylinder(draw, 340, 660, 240, 65, "D2: Vector & Chunk Store")
    draw_cylinder(draw, 1030, 480, 240, 65, "D3: Approvals Ledger")
    draw_cylinder(draw, 1030, 680, 240, 65, "D4: Chained Audit DB")

    # Arrows & Data Flows
    draw_arrow(draw, 230, 155, 340, 155, C_BLUE, label="Credentials")
    draw_arrow(draw, 460, 190, 460, 280, C_GRAY, label="Validate")
    draw_arrow(draw, 580, 155, 680, 155, C_BLUE, label="AuthContext (Role/Perms)")
    draw_arrow(draw, 230, 515, 340, 515, C_GREEN, label="Raw Files")
    draw_arrow(draw, 460, 550, 460, 660, C_GREEN, label="Store Chunks & Embeds")
    draw_arrow(draw, 805, 190, 805, 290, C_AMBER, label="High-Risk Escalate")
    draw_arrow(draw, 930, 325, 1030, 490, C_AMBER, label="Ticket State")
    draw_arrow(draw, 805, 480, 805, 360, C_GREEN, label="Authorized Context")
    draw_arrow(draw, 580, 515, 680, 515, C_GREEN, label="Query Embeddings")
    draw_arrow(draw, 930, 155, 1020, 155, C_BLUE, label="Approved Task")
    draw_arrow(draw, 1150, 190, 1220, 320, C_PURPLE, label="Inference Req")
    draw_arrow(draw, 1220, 320, 1150, 190, C_PURPLE, label="Synthesized Output")
    draw_arrow(draw, 1150, 190, 880, 680, C_PURPLE, label="Record Event & Hash")
    draw_arrow(draw, 930, 715, 1030, 715, C_PURPLE, label="SHA-256 Commit")
    draw_arrow(draw, 1020, 175, 230, 175, C_BLUE, label="Verified Response / PPTX / PDF (Air-Gapped)", label_pos=0.4)

    img.save(output_path, quality=95)


# ── 2. Use Case Diagram ─────────────────────────────────────────────────────
def generate_use_case_image(output_path: Path) -> None:
    img = Image.new("RGB", (1400, 900), C_WHITE)
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([0, 0, 1400, 50], fill=C_DARK)
    draw.text((30, 14), "5.2 USE CASE DIAGRAM — ACTOR ENTITLEMENTS & ACCESS BOUNDARIES", fill=C_WHITE, font=FONT_HEAD)

    # System Boundary Box
    draw.rounded_rectangle([250, 80, 1150, 860], radius=12, fill=C_GRAY_LIGHT, outline=C_BLUE, width=2)
    draw.text((270, 95), "System Boundary: ServerGen AI Enterprise Suite", fill=C_BLUE, font=FONT_HEAD)

    # Actors Left
    draw_actor(draw, 120, 170, "General Employee", C_BLUE)
    draw_actor(draw, 120, 370, "IT Operator", C_NAVY)
    draw_actor(draw, 120, 570, "Security Analyst", C_AMBER)
    draw_actor(draw, 120, 750, "Manager", C_GREEN)

    # Actors Right
    draw_actor(draw, 1280, 320, "Administrator", C_PURPLE)
    draw_actor(draw, 1280, 620, "Ollama LLM", C_DARK)

    # Use Cases (Ellipses)
    ucs = [
        (400, 140, 280, 50, "UC1: Sign In & Token Rotation"),
        (750, 140, 320, 50, "UC2: Inspect Clearance Ceiling"),
        (400, 250, 300, 50, "UC3: Query Knowledge Base (RAG)"),
        (750, 250, 320, 50, "UC4: Upload & Index Documents"),
        (400, 360, 300, 50, "UC5: Execute Verified AI Tasks"),
        (750, 360, 320, 50, "UC6: Run Diagnostics & Tools"),
        (400, 480, 300, 50, "UC7: Request Dual-Custody Approval"),
        (750, 480, 320, 50, "UC8: Approve / Reject High-Risk Tasks"),
        (400, 600, 320, 50, "UC9: Generate 16:9 Slide Deck (.pptx)"),
        (750, 600, 320, 50, "UC10: Generate Executive PDF Report"),
        (400, 730, 320, 50, "UC11: Export AI Response to Doc"),
        (750, 730, 320, 50, "UC12: Verify Cryptographic Audit Ledger"),
    ]

    for x, y, w, h, title in ucs:
        draw.ellipse([x, y, x + w, y + h], fill=C_WHITE, outline=C_BLUE, width=2)
        bbox = FONT_BODY.getbbox(title)
        tw = bbox[2] - bbox[0]
        draw.text((x + (w - tw) / 2, y + (h - 14) / 2), title, fill=C_DARK, font=FONT_BODY)

    # Connector Lines
    # Employee
    draw.line([(180, 180), (400, 165)], fill=C_BLUE, width=1)
    draw.line([(180, 180), (400, 275)], fill=C_BLUE, width=1)
    draw.line([(180, 180), (400, 385)], fill=C_BLUE, width=1)
    draw.line([(180, 180), (400, 625)], fill=C_BLUE, width=1)
    draw.line([(180, 180), (400, 755)], fill=C_BLUE, width=1)

    # IT Operator
    draw.line([(180, 380), (750, 275)], fill=C_NAVY, width=1)
    draw.line([(180, 380), (750, 385)], fill=C_NAVY, width=1)

    # Security Analyst
    draw.line([(180, 580), (750, 165)], fill=C_AMBER, width=1)
    draw.line([(180, 580), (750, 755)], fill=C_AMBER, width=1)

    # Manager
    draw.line([(180, 760), (750, 505)], fill=C_GREEN, width=2)

    # Administrator (Full access)
    draw.line([(1220, 320), (1070, 165)], fill=C_PURPLE, width=1)
    draw.line([(1220, 320), (1070, 275)], fill=C_PURPLE, width=1)
    draw.line([(1220, 320), (1070, 505)], fill=C_PURPLE, width=1)
    draw.line([(1220, 320), (1070, 755)], fill=C_PURPLE, width=1)

    # LLM
    draw.line([(1220, 630), (700, 385)], fill=C_GRAY, width=1)
    draw.line([(1220, 630), (720, 625)], fill=C_GRAY, width=1)
    draw.line([(1220, 630), (750, 625)], fill=C_GRAY, width=1)

    img.save(output_path, quality=95)


# ── 3. Activity Diagram ─────────────────────────────────────────────────────
def generate_activity_image(output_path: Path) -> None:
    img = Image.new("RGB", (1400, 900), C_WHITE)
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([0, 0, 1400, 50], fill=C_DARK)
    draw.text((30, 14), "5.3 ACTIVITY DIAGRAM — ZERO-TRUST WORKFLOW & INFERENCE PIPELINE", fill=C_WHITE, font=FONT_HEAD)

    # Initial Node (Black circle)
    draw.ellipse([675, 70, 725, 120], fill=C_DARK, outline=C_BLUE, width=2)
    draw.text((740, 85), "User Submits Prompt & Sensitivity", fill=C_DARK, font=FONT_HEAD)

    draw_arrow(draw, 700, 120, 700, 160, C_GRAY)
    draw_box(draw, 520, 160, 360, 50, "1. Authenticate & Resolve Role Clearance", fill=C_BLUE_LIGHT, border=C_BLUE)

    draw_arrow(draw, 700, 210, 700, 250, C_GRAY)
    # Decision Diamond 1: Clearance Check
    draw.polygon([(700, 250), (780, 290), (700, 330), (620, 290)], fill=C_AMBER_LIGHT, outline=C_AMBER, width=2)
    draw.text((645, 282), "Clearance OK?", fill=C_AMBER, font=FONT_HEAD)

    # Branch No
    draw_arrow(draw, 620, 290, 300, 290, C_AMBER, label="[No: Exceeds Role Ceiling]")
    draw_box(draw, 140, 265, 160, 50, "Withhold Chunks", "Flag Zero-Trust Alert", fill=C_AMBER_LIGHT, border=C_AMBER)
    draw_arrow(draw, 220, 315, 220, 480, C_GRAY)

    # Branch Yes
    draw_arrow(draw, 700, 330, 700, 370, C_BLUE, label="[Yes: Within Bounds]")
    draw_box(draw, 520, 370, 360, 50, "2. Evaluate Policy & Tool Risk Level", fill=C_BLUE_LIGHT, border=C_BLUE)

    draw_arrow(draw, 700, 420, 700, 460, C_GRAY)
    # Decision Diamond 2: High Risk?
    draw.polygon([(700, 460), (780, 500), (700, 540), (620, 500)], fill=C_AMBER_LIGHT, outline=C_AMBER, width=2)
    draw.text((650, 492), "High Risk?", fill=C_AMBER, font=FONT_HEAD)

    # High Risk Branch
    draw_arrow(draw, 780, 500, 1050, 500, C_AMBER, label="[Yes: Mutating/Sensitive]")
    draw_box(draw, 1050, 475, 280, 50, "Intercept & Queue Approval", "Manager Sign-off Required", fill=C_AMBER_LIGHT, border=C_AMBER)
    draw_arrow(draw, 1190, 525, 1190, 620, C_AMBER)

    # Normal Branch
    draw_arrow(draw, 700, 540, 700, 580, C_BLUE, label="[No: Safe Execution]")
    draw_box(draw, 500, 580, 400, 50, "3. Hybrid RAG Search (Cosine + BM25 RRF)", fill=C_GREEN_LIGHT, border=C_GREEN)
    draw_arrow(draw, 220, 480, 500, 605, C_GRAY)

    draw_arrow(draw, 700, 630, 700, 670, C_GRAY)
    draw_box(draw, 500, 670, 400, 50, "4. Synthesize with Local LLM (llama3.2:3b)", fill=C_PURPLE_LIGHT, border=C_PURPLE)

    # Manager Approval convergence
    draw_arrow(draw, 1050, 620, 900, 695, C_GREEN, label="[Manager Approved]")

    draw_arrow(draw, 700, 720, 700, 760, C_GRAY)
    draw_box(draw, 480, 760, 440, 50, "5. Format Output & Append SHA-256 Chained Hash", fill=C_PURPLE_LIGHT, border=C_PURPLE)

    # End Node (Bullseye)
    draw_arrow(draw, 700, 810, 700, 840, C_GRAY)
    draw.ellipse([680, 840, 720, 880], fill=C_WHITE, outline=C_DARK, width=2)
    draw.ellipse([688, 848, 712, 872], fill=C_DARK, outline=None)
    draw.text((735, 852), "Deliver Verified Response / File", fill=C_DARK, font=FONT_HEAD)

    img.save(output_path, quality=95)


# ── 4. Class Diagram ────────────────────────────────────────────────────────
def generate_class_image(output_path: Path) -> None:
    img = Image.new("RGB", (1400, 900), C_WHITE)
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([0, 0, 1400, 50], fill=C_DARK)
    draw.text((30, 14), "5.4 CLASS DIAGRAM — OBJECT-ORIENTED DOMAIN MODEL & RELATIONSHIPS", fill=C_WHITE, font=FONT_HEAD)

    def draw_class_box(x: float, y: float, w: float, h: float, name: str, attrs: list[str], methods: list[str],
                       header_color: tuple[int, int, int] = C_BLUE) -> None:
        draw.rectangle([x, y, x + w, y + h], fill=C_WHITE, outline=header_color, width=2)
        draw.rectangle([x, y, x + w, y + 28], fill=header_color, outline=None)
        bbox = FONT_HEAD.getbbox(name)
        tw = bbox[2] - bbox[0]
        draw.text((x + (w - tw) / 2, y + 5), name, fill=C_WHITE, font=FONT_HEAD)

        cy = y + 34
        for a in attrs:
            draw.text((x + 8, cy), a, fill=C_DARK, font=FONT_CODE)
            cy += 16
        draw.line([(x, cy + 4), (x + w, cy + 4)], fill=C_BORDER, width=1)
        cy += 10
        for m in methods:
            draw.text((x + 8, cy), m, fill=C_NAVY, font=FONT_CODE)
            cy += 16

    # 1. User & Role
    draw_class_box(40, 80, 240, 150, "User",
                   ["+ UUID id", "+ string username", "+ string email", "+ UUID role_id"],
                   ["+ verify_password()", "+ get_clearance()"], C_BLUE)

    draw_class_box(40, 260, 240, 120, "Role",
                   ["+ UUID id", "+ string name", "+ bool is_system_role"],
                   ["+ has_permission()"], C_BLUE)

    # 2. Security & Policy
    draw_class_box(330, 80, 280, 160, "SecurityPolicyEngine",
                   ["- dict role_clearances", "- float risk_threshold"],
                   ["+ evaluate_policy()", "+ check_clearance()", "+ evaluate_risk()"], C_AMBER)

    draw_class_box(330, 270, 280, 140, "ApprovalRequest",
                   ["+ UUID id", "+ UUID task_id", "+ string status", "+ UUID reviewer_id"],
                   ["+ approve()", "+ reject()"], C_AMBER)

    # 3. Task Orchestrator & LLM
    draw_class_box(660, 80, 320, 180, "TaskOrchestrator",
                   ["- BaseModelProvider llm", "- ToolRegistry registry", "- RoleRetriever retriever"],
                   ["+ execute_task()", "- apply_guardrails()", "- synthesize_output()"], C_PURPLE)

    draw_class_box(660, 290, 320, 140, "OllamaProvider",
                   ["- string base_url", "- string model_name"],
                   ["+ generate(prompt)", "+ embed(text)", "+ health_check()"], C_PURPLE)

    # 4. RAG & Storage
    draw_class_box(1030, 80, 330, 180, "RoleFilteredRetriever",
                   ["- dict _ROLE_CLEARANCE", "- KnowledgeStore store"],
                   ["+ retrieve(query, auth)", "- hybrid_rrf_rank()", "- filter_clearance()"], C_GREEN)

    draw_class_box(1030, 290, 330, 150, "DocumentChunk",
                   ["+ UUID id", "+ UUID document_id", "+ string content", "+ list embedding"],
                   ["+ cosine_similarity()"], C_GREEN)

    # 5. DocGen Studio
    draw_class_box(200, 500, 350, 180, "DocumentGeneratorService",
                   ["- OllamaProvider llm", "- Path storage_dir"],
                   ["+ generate_presentation()", "+ generate_pdf()", "- compile_pptx()", "- compile_pdf()"], C_BLUE)

    draw_class_box(600, 500, 350, 180, "PresentationDeck",
                   ["+ string title", "+ string classification", "+ list<SlideContent> slides"],
                   ["+ to_pptx_widescreen()", "+ add_slide()"], C_BLUE)

    # 6. Audit Service
    draw_class_box(1000, 500, 360, 180, "AuditService",
                   ["- AsyncSession db", "- string last_hash"],
                   ["+ record(event, action)", "+ verify_integrity()", "- calculate_sha256()"], C_DARK)

    # Relationships Lines
    draw_arrow(draw, 160, 230, 160, 260, C_BLUE, label="1..*")
    draw_arrow(draw, 280, 140, 330, 140, C_BLUE, label="auth_ctx")
    draw_arrow(draw, 610, 140, 660, 140, C_AMBER, label="guards")
    draw_arrow(draw, 820, 260, 820, 290, C_PURPLE, label="uses")
    draw_arrow(draw, 980, 140, 1030, 140, C_GREEN, label="queries")
    draw_arrow(draw, 1190, 260, 1190, 290, C_GREEN, label="1..*")
    draw_arrow(draw, 490, 240, 490, 270, C_AMBER, label="creates")
    draw_arrow(draw, 770, 260, 400, 500, C_BLUE, label="triggers")
    draw_arrow(draw, 550, 590, 600, 590, C_BLUE, label="builds")
    draw_arrow(draw, 820, 260, 1080, 500, C_DARK, label="logs")

    img.save(output_path, quality=95)


# ── 5. Sequence Diagram ─────────────────────────────────────────────────────
def generate_sequence_image(output_path: Path) -> None:
    img = Image.new("RGB", (1400, 850), C_WHITE)
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([0, 0, 1400, 50], fill=C_DARK)
    draw.text((30, 14), "5.5 SEQUENCE DIAGRAM — INTERACTIVE EXECUTION & AUDIT LIFELINES", fill=C_WHITE, font=FONT_HEAD)

    lifelines = [
        (100, "Client / User"),
        (280, "API Gateway"),
        (460, "TaskOrchestrator"),
        (660, "SecurityPolicy"),
        (860, "RoleRetriever"),
        (1060, "Ollama LLM"),
        (1260, "AuditService"),
    ]

    # Draw lifelines headers & dashed lines
    for lx, name in lifelines:
        draw_box(draw, lx - 65, 75, 130, 36, name, fill=C_BLUE_LIGHT, border=C_BLUE, radius=4)
        draw.line([(lx, 115), (lx, 810)], fill=C_BORDER, width=2)
        # Activation bar
        draw.rectangle([lx - 6, 140, lx + 6, 780], fill=C_GRAY_LIGHT, outline=C_BLUE, width=1)

    steps = [
        (150, 100, 280, "1: POST /api/v1/ai/execute (query, sensitivity)", C_BLUE),
        (200, 280, 460, "2: dispatchTask(authContext, input)", C_BLUE),
        (260, 460, 660, "3: evaluateClearance(role, sensitivity)", C_AMBER),
        (310, 660, 460, "4: return Decision::ALLOW", C_GREEN),
        (370, 460, 860, "5: retrieve(query, max_clearance)", C_GREEN),
        (430, 860, 860, "6: hybrid_rrf_rank(semantic, keyword)", C_GRAY),
        (490, 860, 460, "7: return GroundedEvidence [chunks]", C_GREEN),
        (550, 460, 1060, "8: generate(prompt + RAG context)", C_PURPLE),
        (620, 1060, 460, "9: return Synthesized Answer", C_PURPLE),
        (680, 460, 1260, "10: record(event, prev_hash, new_hash)", C_DARK),
        (740, 1260, 460, "11: commit SHA-256 Chained Event", C_DARK),
        (780, 460, 100, "12: HTTP 200 OK (verified answer + citations + export)", C_BLUE),
    ]

    for y, x1, x2, label, color in steps:
        if x1 == x2:
            # Self call loop
            draw.arc([x1 - 10, y - 10, x1 + 50, y + 25], start=270, end=90, fill=color, width=2)
            draw_arrow(draw, x1 + 20, y + 25, x1 + 6, y + 25, color)
            draw.text((x1 + 55, y), label, fill=color, font=FONT_SMALL)
        else:
            draw_arrow(draw, x1 + (6 if x1 < x2 else -6), y, x2 + (-6 if x1 < x2 else 6), y, color, label=label, font=FONT_SMALL)

    img.save(output_path, quality=95)


# ── 6. Collaboration Diagram ────────────────────────────────────────────────
def generate_collaboration_image(output_path: Path) -> None:
    img = Image.new("RGB", (1400, 850), C_WHITE)
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([0, 0, 1400, 50], fill=C_DARK)
    draw.text((30, 14), "5.6 COLLABORATION (COMMUNICATION) DIAGRAM — SPATIAL OBJECT INTERACTIONS", fill=C_WHITE, font=FONT_HEAD)

    # Nodes arranged circularly/spatially
    nodes = {
        "UI": (120, 360, 180, 65, ":WebInterface"),
        "API": (400, 180, 200, 65, ":FastAPIGateway"),
        "ORCH": (720, 360, 220, 65, ":TaskOrchestrator"),
        "POL": (400, 540, 200, 65, ":SecurityPolicy"),
        "RAG": (720, 140, 220, 65, ":RoleRetriever"),
        "LLM": (1080, 180, 200, 65, ":OllamaProvider"),
        "DOC": (1080, 360, 200, 65, ":DocGenService"),
        "AUD": (1080, 540, 200, 65, ":AuditService"),
        "DB": (720, 680, 220, 65, ":DatabaseStore"),
    }

    for key, (x, y, w, h, label) in nodes.items():
        draw_box(draw, x, y, w, h, label, fill=C_BLUE_LIGHT if "API" in label or "ORCH" in label else C_WHITE,
                 border=C_BLUE if "API" in label or "ORCH" in label else C_GRAY)

    # Links with numbered messages
    # 1. UI <-> API
    draw.line([(300, 380), (400, 230)], fill=C_GRAY, width=2)
    draw.text((260, 270), "1: submitTask(query, sens) >", fill=C_BLUE, font=FONT_SMALL)
    draw.text((250, 290), "< 8: returnVerifiedResponse()", fill=C_BLUE, font=FONT_SMALL)

    # 2. API <-> ORCH
    draw.line([(600, 220), (720, 360)], fill=C_GRAY, width=2)
    draw.text((610, 260), "2: dispatch() >", fill=C_BLUE, font=FONT_SMALL)

    # 3. ORCH <-> POL
    draw.line([(720, 400), (600, 550)], fill=C_GRAY, width=2)
    draw.text((560, 450), "3: checkClearance() >", fill=C_AMBER, font=FONT_SMALL)
    draw.text((580, 470), "< return Decision", fill=C_AMBER, font=FONT_SMALL)

    # 4. ORCH <-> RAG
    draw.line([(830, 360), (830, 205)], fill=C_GRAY, width=2)
    draw.text((840, 270), "4: retrieveGroundedChunks() >", fill=C_GREEN, font=FONT_SMALL)
    draw.text((840, 290), "< return EvidenceItems", fill=C_GREEN, font=FONT_SMALL)

    # 5. ORCH <-> LLM
    draw.line([(940, 370), (1080, 240)], fill=C_GRAY, width=2)
    draw.text((950, 280), "5: synthesize(prompt, rag) >", fill=C_PURPLE, font=FONT_SMALL)
    draw.text((970, 300), "< return RawTokens", fill=C_PURPLE, font=FONT_SMALL)

    # 6. ORCH <-> DOC
    draw.line([(940, 392), (1080, 392)], fill=C_GRAY, width=2)
    draw.text((950, 400), "6: compileDeckOrPdf() >", fill=C_BLUE, font=FONT_SMALL)

    # 7. ORCH <-> AUD
    draw.line([(940, 415), (1080, 545)], fill=C_GRAY, width=2)
    draw.text((960, 470), "7: appendLedgerEvent() >", fill=C_DARK, font=FONT_SMALL)

    # 8. AUD <-> DB
    draw.line([(1080, 580), (940, 690)], fill=C_GRAY, width=2)
    draw.text((980, 630), "7.1: commitChainedHash() >", fill=C_DARK, font=FONT_SMALL)

    img.save(output_path, quality=95)


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
        self.line(40, 36, letter[0] - 40, 36)
        self.drawString(40, 24, "ServerGen AI — Secure Enterprise Automation Platform (Architectural Specification)")
        self.drawRightString(letter[0] - 40, 24, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


# ── Main PDF Compiler ───────────────────────────────────────────────────────
def compile_diagrams_pdf(storage_dir: Path) -> Path:
    storage_dir.mkdir(parents=True, exist_ok=True)
    images_dir = storage_dir / "diagram_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    dfd_path = images_dir / "5_1_dfd.png"
    use_case_path = images_dir / "5_2_use_case.png"
    activity_path = images_dir / "5_3_activity.png"
    class_path = images_dir / "5_4_class.png"
    seq_path = images_dir / "5_5_sequence.png"
    collab_path = images_dir / "5_6_collaboration.png"

    print("Rendering Diagram 5.1 (DFD)...")
    generate_dfd_image(dfd_path)
    print("Rendering Diagram 5.2 (Use Case)...")
    generate_use_case_image(use_case_path)
    print("Rendering Diagram 5.3 (Activity)...")
    generate_activity_image(activity_path)
    print("Rendering Diagram 5.4 (Class)...")
    generate_class_image(class_path)
    print("Rendering Diagram 5.5 (Sequence)...")
    generate_sequence_image(seq_path)
    print("Rendering Diagram 5.6 (Collaboration)...")
    generate_collaboration_image(collab_path)

    pdf_filename = "ServerGen_AI_System_Architecture_and_Design_Diagrams.pdf"
    pdf_path = storage_dir / pdf_filename

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=45,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#475569"),
        spaceAfter=14,
    )

    h1_style = ParagraphStyle(
        "SecH1",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1D4ED8"),
        spaceBefore=8,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "SecBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )

    story: list[Any] = []

    # ── Cover Page / Header ─────────────────────────────────────────────────
    badge_p = Paragraph(
        "<b>ENTERPRISE SPECIFICATION &bull; ARCHITECTURAL DESIGN DIAGRAMS</b>",
        ParagraphStyle("CoverBadge", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=1),
    )
    badge_table = Table([[badge_p]], colWidths=[540], rowHeights=[22])
    badge_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E293B")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(badge_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("ServerGen AI: System Architecture Diagrams", title_style))
    story.append(
        Paragraph(
            "Complete Software Engineering Diagrams (Sections 5.1 to 5.6): Data Flow, Use Case, Activity, "
            "Class, Sequence, and Collaboration Models illustrating zero-trust RBAC, hybrid RAG, local LLM orchestration, "
            "and tamper-evident audit logging.",
            subtitle_style,
        )
    )

    meta_table = Table(
        [
            [
                Paragraph("<b>Author:</b> ServerGen AI System Architecture Team", body_style),
                Paragraph(f"<b>Date:</b> {datetime.date.today().strftime('%B %d, %Y')}", body_style),
                Paragraph("<b>Classification:</b> RESTRICTED (Internal Arch)", body_style),
            ]
        ],
        colWidths=[200, 160, 180],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # Diagram Sections
    diagrams = [
        (
            "5.1 Data Flow Diagram (DFD) — Level 1 Decomposition",
            dfd_path,
            "<b>Description:</b> Illustrates the end-to-end data pipelines and boundary controls of ServerGen AI. "
            "Depicts data exchange across 3 external entities (Enterprise User, Document Files, Local Ollama Engine), "
            "7 core processes (Authentication, Ingestion & Embedding, Zero-Trust Guardrails, Dual-Custody Interception, "
            "Hybrid RAG Retrieval, Task Orchestration & Document Studio, and Chained Audit Logging), and 5 database stores.",
        ),
        (
            "5.2 Use Case Diagram — Actor Entitlements & Access Boundaries",
            use_case_path,
            "<b>Description:</b> Visualizes the complete matrix of role-based interactions across 6 primary enterprise actors "
            "(General Employee, IT Operator, Security Analyst, Department Manager, System Administrator, and Local LLM). "
            "Outlines permitted operations including session management, grounded RAG queries, document ingestion, dual-custody review, "
            "widescreen PowerPoint (.pptx) & executive PDF generation, and cryptographic audit ledger verification.",
        ),
        (
            "5.3 Activity Diagram — Zero-Trust Workflow & Inference Pipeline",
            activity_path,
            "<b>Description:</b> Models the step-by-step decision logic and operational branches executed during task evaluation. "
            "Covers authentication verification, role clearance ceiling checks, high-risk policy interception, dual-custody approval gating, "
            "hybrid cosine semantic and BM25 keyword retrieval fusion (RRF), local LLM inference (llama3.2:3b), and SHA-256 hash chaining.",
        ),
        (
            "5.4 Class Diagram — Object-Oriented Domain Model & Relationships",
            class_path,
            "<b>Description:</b> Defines the static architectural structure of ServerGen AI. Displays class schemas, private/public attributes, "
            "and core methods across 6 subsystems: Identity & Session (User, Role), Policy & Approvals (SecurityPolicyEngine, ApprovalRequest), "
            "Local AI Orchestration (TaskOrchestrator, OllamaProvider), Knowledge Storage (DocumentChunk, RoleFilteredRetriever), "
            "Document Studio (DocumentGeneratorService, PresentationDeck), and Cryptographic Governance (AuditService).",
        ),
        (
            "5.5 Sequence Diagram — Interactive Execution & Audit Lifelines",
            seq_path,
            "<b>Description:</b> Details the chronological message sequence across 7 active lifelines (Client, API Gateway, "
            "TaskOrchestrator, SecurityPolicy, RoleRetriever, Ollama LLM, and AuditService). Traces the full round-trip execution flow "
            "from initial prompt dispatch, clearance validation, and context fusion to model synthesis and tamper-evident event commitment.",
        ),
        (
            "5.6 Collaboration Diagram — Spatial Object Interactions",
            collab_path,
            "<b>Description:</b> Emphasizes the structural organization and numbered communication paths between collaborating system objects. "
            "Highlights spatial decoupling between API controllers, orchestration engines, isolated local model providers, and persistent "
            "database ledgers ensuring zero unauthorized data egress.",
        ),
    ]

    for title, img_file, desc in diagrams:
        sec_elements: list[Any] = []
        sec_elements.append(Paragraph(title, h1_style))
        sec_elements.append(Paragraph(desc, body_style))
        sec_elements.append(Spacer(1, 4))
        # 540 width image fits letter page perfectly
        sec_elements.append(RLImage(str(img_file), width=540, height=325))
        sec_elements.append(Spacer(1, 14))
        story.append(KeepTogether(sec_elements))
        story.append(PageBreak())

    # Build PDF
    # Pop last PageBreak so document doesn't end with blank page
    if story and isinstance(story[-1], PageBreak):
        story.pop()

    print("Compiling final PDF with NumberedCanvas...")
    doc.build(story, canvasmaker=NumberedCanvas)
    file_size = pdf_path.stat().st_size
    print(f"Generated PDF: {pdf_path} ({file_size} bytes)")

    # Register in index_meta.json
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
        "summary": "Complete Software Engineering Diagrams: DFD, Use Case, Activity, Class, Sequence, and Collaboration Models.",
        "download_url": f"/api/v1/generate/download/{pdf_filename}",
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "slide_or_page_count": len(diagrams) + 1,
    }

    records = [r for r in records if r.get("file_id") != file_meta["file_id"]]
    records.insert(0, file_meta)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(records[:100], f, indent=2)

    print("Registered file in index_meta.json successfully.")
    return pdf_path


if __name__ == "__main__":
    out_dir = Path("storage/generated").resolve()
    compile_diagrams_pdf(out_dir)
