# ServerGen AI — Secure Enterprise Automation & Local Document Studio

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Local_LLM-Ollama-orange.svg)](https://ollama.ai)
[![Zero-Trust](https://img.shields.io/badge/Security-Zero--Trust_RBAC-purple.svg)](#security-architecture)
[![License](https://img.shields.io/badge/license-Proprietary-gray.svg)](#)

> A controlled, on-premise enterprise AI automation platform powered by **local LLMs (Ollama `llama3.2:3b`)**, zero-trust clearance gating, hybrid RAG knowledge bases, tamper-evident cryptographic audit ledgers, and an automated **PDF & PowerPoint (PPTX) Generation Studio**.

---

## 🌟 Key Capabilities

### 1. 🛡️ Zero-Trust Identity & Access Control (RBAC/ABAC)
- **Argon2id** password hashing with memory-hard protection against brute force and timing attacks.
- **Cryptographic JWT** tokens with automatic rotation and 15-minute access token lifetimes.
- **Hierarchical Clearances**: `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, and `RESTRICTED`.
- **Dual-Custody Approvals**: Critical operational mutations require explicit managerial sign-off before execution.

### 2. 🧠 Local AI Orchestration & Guardrails
- **100% On-Premise Inference** via local Ollama runtime (`llama3.2:3b`) — zero external cloud data egress.
- **Deterministic 10-Stage Pipeline**: Classification &rarr; Sensitivity Resolution &rarr; Risk Engine &rarr; Policy Decision &rarr; Model Routing &rarr; Verification &rarr; SHA-256 Audit Logging.
- **Structured Synthesis**: Outputs include executive summaries, deep technical breakdowns, and actionable best practices.

### 3. 📚 Enterprise Knowledge Base (Hybrid RAG)
- Multi-format ingestion: `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.csv`, `.txt`, `.md`, and `.html`.
- Structural heading-aware semantic chunking with overlap protection.
- Hybrid vector & keyword retrieval with strict zero-trust role-filtered clearance boundaries.

### 4. 📊 PDF & PowerPoint (PPTX) Generation Studio *(New)*
- **Widescreen 16:9 Presentation Decks (.pptx)**: Generates structured, corporate-styled slide decks with categories, bullet points, speaker notes, and key takeaways using `python-pptx`.
- **Executive PDF Reports (.pdf)**: Generates publication-ready corporate reports with dynamic page numbering ("Page X of Y"), classification banners, and callout tables using ReportLab.
- **Grounded Generation**: Synthesizes decks and reports directly from internal organizational knowledge bases.

### 5. 🔍 Tamper-Evident SHA-256 Audit Ledger
- Cryptographic hash-chained audit logging (`Hash_N = SHA-256(Hash_{N-1} + Timestamp + Actor + Action + Payload)`).
- Instant verification of ledger integrity with zero tolerance for record tampering.

---

## 🚀 Quick Start (Running the Platform)

### 1. Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com) installed with `llama3.2:3b`:
  ```bash
  ollama pull llama3.2:3b
  ```

### 2. Setup Environment
```bash
# Clone the repository
git clone https://github.com/Rahul-0704/servergen-ai.git
cd servergen-ai

# Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux / macOS:
# source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 3. Configure Environment
```bash
# Copy template configuration
copy .env.example .env    # Windows
# cp .env.example .env    # Linux/macOS
```
*The default `.env` is pre-configured with SQLite WAL mode for instant, zero-setup local development.*

### 4. Start Local Services
In terminal 1 (Start Ollama LLM):
```bash
ollama serve
```

In terminal 2 (Start ServerGen AI API):
```bash
uvicorn src.app:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🖥️ User Interfaces & Endpoints

| Service | URL | Description |
| :--- | :--- | :--- |
| **Test & Demo Dashboard** | [http://127.0.0.1:8000/test](http://127.0.0.1:8000/test) | Full testing UI: AI Assistant, Doc & Slide Studio, Knowledge Base, Approvals |
| **API Documentation (Swagger)** | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Interactive REST API tester and OpenAPI schemas |
| **Health Check** | [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health) | Backend, database, and local Ollama model status |

---

## 👥 Pre-Configured Test Accounts

| Username | Password | Role | Clearance | Scope |
| :--- | :--- | :--- | :--- | :--- |
| `admin` | `admin` | `administrator` | `RESTRICTED` | Full system control, user management, audit logs |
| `manager` | `Manager1!` | `manager` | `CONFIDENTIAL` | Operational approvals, departmental documents |
| `operator` | `Operator1!` | `it_operator` | `CONFIDENTIAL` | Server diagnostics, runbooks, IT operations |
| `analyst` | `Analyst1!` | `security_analyst` | `INTERNAL` | RAG analytical queries, audit reviews |
| `employee` | `Employee1!` | `general_employee` | `PUBLIC` | General knowledge queries, public documents |

---

## 🎨 Building a Custom Frontend?

If your team is building a frontend (React, Next.js, Vue, Svelte, or Mobile), explore our guides and architecture blueprints:

👉 **[docs/FRONTEND_GUIDE.md](docs/FRONTEND_GUIDE.md)** — **Primary Guide for Frontend Collaborators**: Quickstart setup, seed credentials, REST API contracts with JSON request/response payloads, and UI wireframes.

👉 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — Architectural blueprint, 10-stage orchestration pipeline, and security boundaries.

👉 **[docs/API.md](docs/API.md)** — Comprehensive REST API endpoint reference and OpenAPI schemas.

👉 **[docs/SECURITY.md](docs/SECURITY.md)** — Zero-trust access policies, Argon2id security model, and cryptographic ledger proofs.

👉 **[System Architecture & Design Diagrams (PDF)](docs/diagrams/ServerGen_AI_System_Architecture_and_Design_Diagrams.pdf)** — High-resolution 7-page PDF containing 5.1 DFD, 5.2 Use Case, 5.3 Activity, 5.4 Class, 5.5 Sequence, and 5.6 Collaboration diagrams.

---

## 📁 Clean Project Structure

```text
servergen-ai/
├── docs/                # Architecture, API specifications, and frontend guide
│   ├── API.md
│   ├── ARCHITECTURE.md
│   ├── FRONTEND_GUIDE.md
│   └── SECURITY.md
├── scripts/             # Operational scripts
│   ├── generate_diagrams.py   # High-resolution architectural diagram generator
│   ├── seed_db.py             # Database initializer (roles, permissions, accounts)
│   └── verify_all_5_tests.py  # 5-stage automated verification runner
├── src/                 # Application source code
│   ├── ai/              # Local LLM orchestration (Ollama provider, model registry)
│   ├── api/v1/          # REST API endpoints (Auth, RAG, AI, Approvals, Generate)
│   ├── auth/            # Zero-trust RBAC/ABAC and Argon2id security
│   ├── core/            # Database engine, config, and exceptions
│   ├── models/          # SQLAlchemy async models
│   ├── orchestrator/    # 10-stage execution pipeline and risk engine
│   ├── rag/             # Multi-format ingestion, chunking, and hybrid search
│   └── services/        # Business services (Auth, DocGen, Approvals, Audit)
├── storage/             # Managed document repository and generated PPTX/PDFs
├── tests/               # Automated unit and integration test suite (162 tests)
├── test-interface.html  # Live browser test dashboard and interactive playground
├── pyproject.toml       # Dependencies, build system, and linter configuration
├── run.bat              # Master runner script (checks & launcher)
└── start.bat            # Quick local services launcher (Ollama + Uvicorn)
```




---

## 🧪 Testing & Verification

Run the core 5-stage verification suite:
```bash
python scripts/verify_all_5_tests.py
```

Run unit tests with pytest:
```bash
pytest tests/unit/ -v
```
