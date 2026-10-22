# ServerGen AI — Comprehensive System Logic, Problem Analysis & Roadmap

**Date:** October 22, 2026  
**System Version:** v0.2.0  
**Target Hardware:** Intel Core i5-12450H | 16 GB DDR4 | NVIDIA GeForce RTX 2050 (4GB VRAM)  
**Stack:** FastAPI + SQLAlchemy 2.x Async + SQLite WAL + Ollama (`llama3.2:3b` via CUDA 13.1)

---

## 1. Executive Summary & Mission

ServerGen AI is an on-premise, zero-trust enterprise AI automation platform. It is engineered to bridge the critical gap between modern Large Language Model (LLM) automation and strict corporate security, regulatory compliance, and role-based access control.

Unlike commercial cloud-dependent AI tools (which expose corporate IP and sensitive internal documents to third-party APIs), ServerGen AI operates **entirely locally on workstation/server hardware**. It combines local GPU-accelerated LLM reasoning with a **deterministic, non-bypassable policy engine**, ensuring that AI agents can never execute unverified commands, access unauthorized internal data, or bypass human governance.

---

## 2. Real-World Problems We Are Solving

1. **Cloud Data Exfiltration & Regulatory Penalties:** Sending internal server runbooks, credentials, and financial metrics to cloud LLM providers breaches data protection mandates (GDPR, HIPAA, SOC 2, ISO 27001). ServerGen AI runs on **local hardware** using Meta's `llama3.2:3b` model offloaded 100% to the local NVIDIA RTX 2050 GPU. No prompt, token, or document chunk ever leaves the local subnet.
2. **The "Wild West" Unconstrained LLM Agent:** Traditional autonomous agents are granted raw shell, database, or API access. A single prompt injection or hallucination can wipe production databases (`DROP TABLE`), restart critical servers, or open firewall ports. In ServerGen AI, the LLM **never decides security clearance or directly executes system actions**. Every request passes through static RBAC checks, deterministic classification, composite risk scoring, and automated policy interception.
3. **Naive RAG Data Bleed (Access Control Blindness):** Standard Retrieval-Augmented Generation (RAG) indexes all company documents into a single vector database. When a junior employee asks about executive salaries or confidential server exploits, naive vector search retrieves those chunks and hands them to the model. ServerGen AI implements **Role-Filtered RAG with Sensitivity Escalation**: unauthorized chunks are filtered out before prompt construction, and sensitive matches elevate task risk to enforce human approval.
4. **Audit Blind Spots & Non-Repudiation Gaps:** Standard AI systems log plain text files that can be altered, truncated, or erased by malicious insiders or compromised accounts. ServerGen AI implements a **Tamper-Evident SHA-256 Cryptographic Audit Ledger** where every event is cryptographically linked to its predecessor. Any tampering breaks the chain.
5. **Superficial Outputs & Hallucinations:** Standardized enterprise response engineering requiring:
   - **Executive Summary**
   - **Itemized Findings** grounded strictly in retrieved context
   - **Operational Recommendations & Runbook Safeguards**
   - **Document Source Citations** (`[Source: <Title> | Classification: <Level>]`)
   - Support for **JSON-Schema Constrained Decoding** (`structured: true`) using Pydantic.

---

## 3. What Has Been Built Right Now

### Module 1: Secure Access & Audit Management (100% Complete)
- **Password Hashing:** Argon2id via `argon2-cffi` with time/memory cost parameters.
- **Authentication:** PyJWT short-lived access tokens (15 minutes) and cryptographically random refresh tokens (7 days).
- **Token Rotation & Family Revocation:** Every token refresh revokes the old refresh token and issues a new one; reuse triggers immediate family revocation.
- **Centralized RBAC Engine:** Strict mapping of 5 system roles (`administrator`, `it_operator`, `security_analyst`, `manager`, `general_employee`) across 14 independent granular permissions (`ai.execute`, `document.read`, `system.execute`, etc.).
- **User Management CRUD:** Administrative API for user provisioning, role assignments, and instant account deactivation.
- **Tamper-Evident Audit Ledger:** Cryptographic hash chaining on every login, failed attempt, token refresh, tool invocation, and AI query.

### Module 2: AI Orchestrator & Local LLM Engine (100% Complete)
- **Hardware-Accelerated LLM Runtime:** Local Ollama daemon serving `llama3.2:3b` with `"num_gpu": 99` layer offloading to the NVIDIA GeForce RTX 2050 (4GB VRAM) via CUDA 13.1.
- **8-Stage Zero-Trust Execution Pipeline:**
  1. Caller JWT authentication & `ai.execute` permission verification.
  2. Rule-based Task Classification & Operation Typing (`QUERY`, `ANALYSIS`, `MODIFY`, `EXECUTE`, `REPORT`).
  3. Role-Filtered RAG Retrieval with document clearance checks.
  4. Server-Side Sensitivity Resolution & dynamic escalation.
  5. Multi-factor Risk Scoring & Security Policy evaluation (`ALLOW`, `DENY`, `REQUIRE_APPROVAL`).
  6. Tool execution (if requested and authorized) or grounded LLM prompt synthesis.
  7. Deterministic verification (token leakage prevention, non-empty validation).
  8. Cryptographic audit event append.
- **Human-in-the-Loop Approvals:** High-risk tasks generate an immutable `ApprovalRequest` record holding execution until reviewed by a Manager or Administrator.
- **Deterministic Sandboxed Tools:** `calculator` (safe AST math parsing), `system_info` (OS metrics), and blocked `shell_execute`.

### Role-Filtered RAG Subsystem (Integrated Ahead of Module 3)
- In-memory structured knowledge store pre-seeded with 5 enterprise documents:
  - *ServerGen AI System Overview & Core Capabilities* (`INTERNAL` | Architecture)
  - *Enterprise Role Permissions & Clearance Standards* (`INTERNAL` | Policy)
  - *IT Operations & Server Diagnostic Runbook* (`CONFIDENTIAL` | Operations)
  - *Defensive Security & Audit Integrity Playbook* (`CONFIDENTIAL` | Security)
  - *Executive Policy & Q3 Enterprise Financial Audit* (`RESTRICTED` | Executive)
- **Role Clearance Limits:**
  - `administrator`: Clearance through `RESTRICTED` (All documents).
  - `it_operator` & `security_analyst`: Clearance through `CONFIDENTIAL`.
  - `manager`: Clearance through `RESTRICTED` (Operations/Executive).
  - `general_employee`: Clearance strictly limited to `INTERNAL` and `PUBLIC`.
- **First-Class Grounding Metadata:** Returned responses provide `grounded_sources` with document title, classification, category, and keyword relevance scores.

### Interactive Management Console (`http://127.0.0.1:8000/test`)
- One-click role presets for rapid switching between test personas.
- Live system health indicators (FastAPI, SQLite DB, Active Session, Local Ollama GPU status).
- AI pipeline visualizer rendering formatted Markdown, source citation badges, and zero-trust warning banners.
- Document registry tab for browsing accessible documents and indexing new organizational knowledge.
- Live Human-in-the-Loop approval resolution queue.
- Cryptographic hash-chain auditor and verification inspector.

---

## 4. Hardware Utilization & Resource Envelope

| Hardware Component | Specification | Allocated Utilization | Status & Behavior |
| :--- | :--- | :--- | :--- |
| **GPU** | NVIDIA GeForce RTX 2050 | ~2.0 GB VRAM | 100% CUDA layer offload; leaves ~2.0 GB VRAM free for Windows DWM |
| **CPU** | 12th Gen Intel Core i5-12450H (8C/12T) | ~5-15% CPU load | Dispatches async FastAPI requests and SQLite I/O |
| **RAM** | 16 GB DDR4 | ~2.4 GB total memory footprint | Minimal footprint; no memory leakage across repeated inferences |
| **Model** | `llama3.2:3b` (Q4_K_M GGUF) | 3.21B parameters | High generation speed (55–75 tokens/sec); sub-second time-to-first-token |

---

## 5. What Problems We Are Solving Right Now (Current Focus)

1. **Advancing from Lexical Search to Dense Embeddings:** Upgrading the RAG retriever with semantic embeddings (e.g. `nomic-embed-text` or `all-MiniLM-L6-v2`) via Ollama/ONNX to support hybrid search (BM25 + vector similarity) within the 4GB GPU VRAM constraint.
2. **Context Window Optimization & Multi-Document Cross-Referencing:** Packing multi-source organizational chunks up to 4,096 tokens with deduplicated citations and RBAC boundaries intact.

---

## 6. Development Roadmap (Modules 3 through 6)

- **Module 3 — Knowledge & Document Intelligence (Next Major Milestone):**
  - Persistent storage for document chunks in SQLite with vector extensions or PostgreSQL `pgvector`.
  - PDF, DOCX, and Markdown document ingest pipeline with automatic chunking and semantic deduplication.
  - Multi-document summarization agents.
- **Module 4 — Autonomous Operations Engine:**
  - Safe, deterministic operational adapters (SSH, Kubernetes, Docker, HTTP health probes).
  - Two-phase commit runbook executions with automated rollback triggers.
- **Module 5 — Defensive Security Posture:**
  - CVE feed monitoring, automated security playbook execution, and configuration compliance checks.
- **Module 6 — Enterprise Reporting & Business Intelligence:**
  - Automated periodic executive reporting, metric trend analysis, and CSV/PDF export.

---

## 7. Current Project Health & Verification Summary

| Metric / Check | Value | Verification Status |
| :--- | :---: | :---: |
| **Unit Test Coverage** | 115 / 115 Passed | 🟢 100% Pass Rate (`pytest tests/unit -q`) |
| **End-to-End Test Suite** | 53 / 53 Passed | 🟢 100% Pass Rate (`python scripts/e2e_test.py`) |
| **Tamper-Evident Audit Chain** | All SHA-256 Hashes Intact | 🟢 Validated via `/api/v1/audit/verify` |
| **Local LLM Offline Inference** | Active on RTX 2050 GPU | 🟢 Tested & Serving on `localhost:11434` |
| **Backend REST API** | Active on `127.0.0.1:8000` | 🟢 Healthy & Responsive |
| **Code Management & Git Status** | Clean Working Tree | 🟢 Committed to Git (`master`) |
