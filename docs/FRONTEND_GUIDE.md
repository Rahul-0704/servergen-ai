# ServerGen AI — Frontend Developer & Collaborator Guide

Welcome to **ServerGen AI**! This guide is written specifically for frontend developers and team collaborators to help you quickly understand the project, run the local backend, and build an exceptional user interface.

---

## 1. Quickstart — Running the Backend

### Prerequisites
- **Git**
- **Python 3.11+** (Python 3.12 or 3.14 recommended)
- **Ollama**: Download and install from [ollama.com](https://ollama.com)
  ```powershell
  # Pull the required local model
  ollama pull llama3.2:3b
  ```

### Clone and Launch
```powershell
# 1. Clone repository
git clone https://github.com/Rahul-0704/servergen-ai.git
cd servergen-ai

# 2. Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch Backend (1-Click)
# Windows:
.\run.bat
# Linux / macOS:
# chmod +x run.sh && ./run.sh

# Or launch manually:
# uvicorn src.app:app --host 127.0.0.1 --port 8000 --reload
```

### Verify Running Services
- **Backend API**: [`http://localhost:8000`](http://localhost:8000)
- **Swagger Docs**: [`http://localhost:8000/docs`](http://localhost:8000/docs)
- **Built-in Test UI**: [`http://localhost:8000/test`](http://localhost:8000/test)
- **Health Check**: [`http://localhost:8000/api/v1/health`](http://localhost:8000/api/v1/health)

---

## 2. Platform Architecture Overview

ServerGen AI is an **on-premise, air-gapped enterprise automation platform** combining:
1. **Zero-Trust Role-Based Access Control (RBAC)**: Users have clearance ceilings (`PUBLIC` ➔ `INTERNAL` ➔ `CONFIDENTIAL` ➔ `RESTRICTED`).
2. **Local AI Inference**: Powered by Ollama (`llama3.2:3b`). Zero data leaves the local machine.
3. **Enterprise Hybrid RAG**: Merges semantic cosine vector search with BM25 keyword matching using Reciprocal Rank Fusion (RRF). Higher-classification chunks are withheld if the user lacks clearance.
4. **Dual-Custody Approvals**: High-risk mutating actions (like infrastructure changes or restricted queries) are intercepted and held in an approval queue until an authorized manager approves.
5. **Document & Slide Studio**: Generates 16:9 widescreen PowerPoint (`.pptx`) decks and corporate executive reports (`.pdf`) directly from retrieved RAG context.
6. **Tamper-Evident Audit Ledger**: Every action, decision, and risk evaluation is cryptographically chained using SHA-256 hashes.

---

## 3. Seed Accounts & Roles

When testing, use these default credentials:

| Username | Password | Role | Clearance Ceiling | Description |
| :--- | :--- | :--- | :--- | :--- |
| **`admin`** | `admin` | `administrator` | **RESTRICTED** | Full governance, role management, clearance override |
| **`operator`** | `Operator1!` | `it_operator` | **CONFIDENTIAL** | System diagnostics, document ingestion, tool runs |
| **`analyst`** | `Analyst1!` | `security_analyst` | **CONFIDENTIAL** | Audit log inspection, ledger hash verification |
| **`manager`** | `Manager1!` | `manager` | **RESTRICTED** | Dual-custody review queue, approve/reject high-risk tasks |
| **`employee`** | `Employee1!` | `general_employee` | **INTERNAL** | Standard Q&A, slide & PDF generation |

---

## 4. Frontend REST API Reference

All protected endpoints require:
```http
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
```

### 4.1 Authentication & Session Management

#### `POST /api/v1/auth/login`
```json
// Request
{
  "username": "admin",
  "password": "admin"
}

// Response (200 OK)
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### `GET /api/v1/auth/me`
Fetch currently authenticated user profile (requires `Authorization: Bearer <ACCESS_TOKEN>`):
```json
// Response (200 OK)
{
  "id": "610cf9d9-e665-4962-98b8-3a29103e91f5",
  "username": "admin",
  "email": "admin@servergen.local",
  "full_name": "System Administrator",
  "role": "administrator",
  "is_active": true
}
```

#### `POST /api/v1/auth/refresh`
Rotate token pair. If a token reuse attack is detected, the family is automatically revoked.
```json
// Request
{
  "refresh_token": "<REFRESH_TOKEN>"
}
```

---

### 4.2 AI Task Execution (The Core Query Engine)

#### `POST /api/v1/ai/execute`
Executes user prompts against local Ollama with zero-trust guardrails and hybrid RAG context.

```json
// Request
{
  "input": "Summarize our zero-trust access control architecture and cloud security controls",
  "data_sensitivity": "internal", // "public" | "internal" | "confidential" | "restricted"
  "tool": "" // optional: "calculator" | "system_info" | "presentation_generator" | "pdf_generator"
}

// Response (200 OK)
{
  "success": true,
  "policy_decision": "allow", // "allow" | "require_approval" | "deny"
  "risk_level": "low",        // "low" | "medium" | "high" | "critical"
  "task_category": "analysis",
  "content": "### Zero-Trust Architecture Summary\n\nServerGen AI implements...",
  "model_used": "llama3.2:3b",
  "citations": [
    {
      "document_title": "Enterprise Security Runbook",
      "relevance_score": 0.89,
      "chunk_index": 2
    }
  ],
  "warnings": [
    // If higher-classification chunks were filtered out:
    // "rag_unauthorized_records_withheld:2"
  ]
}
```

> [!IMPORTANT]
> **Zero-Trust UI Warning**: Check `res.warnings`. If an item starts with `rag_unauthorized_records_withheld:`, display a banner to the user stating:  
> *"N record(s) withheld from knowledge context due to active role clearance limit."*

---

### 4.3 Document & Slide Studio (PDF & PPTX)

#### A. Generate Widescreen 16:9 Presentation (`.pptx`)
`POST /api/v1/generate/presentation`
```json
// Request
{
  "topic": "Zero Trust Cloud Infrastructure & Compliance",
  "num_slides": 5, // 3 to 12 slides
  "classification": "INTERNAL",
  "context": "Optional reference context or prompt text"
}

// Response (200 OK)
{
  "success": true,
  "message": "Generated 5-slide presentation successfully.",
  "meta": {
    "file_id": "9efcfb0e",
    "filename": "9efcfb0e_Zero_Trust_Cloud_Infrastructure.pptx",
    "format": "pptx",
    "file_size": 43480,
    "title": "Zero Trust Cloud Infrastructure & Compliance",
    "download_url": "/api/v1/generate/download/9efcfb0e_Zero_Trust_Cloud_Infrastructure.pptx",
    "slide_or_page_count": 5
  },
  "outline": {
    "title": "Zero Trust Cloud Infrastructure & Compliance",
    "slides": [
      {
        "title": "Executive Overview & Objectives",
        "category": "STRATEGY",
        "bullets": ["Bullet 1...", "Bullet 2..."],
        "key_takeaway": "Takeaway message..."
      }
    ]
  }
}
```

#### B. Generate Executive PDF Report (`.pdf`)
`POST /api/v1/generate/pdf`
```json
// Request
{
  "topic": "Incident Response Post-Mortem Assessment",
  "classification": "CONFIDENTIAL",
  "context": "Context text..."
}

// Response (200 OK)
{
  "success": true,
  "meta": {
    "file_id": "5d5e9ab2",
    "filename": "5d5e9ab2_Incident_Response_Report.pdf",
    "format": "pdf",
    "file_size": 5328,
    "download_url": "/api/v1/generate/download/5d5e9ab2_Incident_Response_Report.pdf"
  },
  "outline": {
    "title": "Incident Response Post-Mortem Assessment",
    "executive_summary": "High density executive summary...",
    "sections": [
      {
        "heading": "1. Operational Scope & Scope",
        "content": "Paragraph...",
        "bullet_points": ["Point 1", "Point 2"]
      }
    ]
  }
}
```

#### C. Grounded RAG-to-Publication (One-Click)
`POST /api/v1/generate/from-rag`
```json
// Request
{
  "query": "Explain database connection pooling and failover architecture",
  "target_format": "pptx", // "pptx" | "pdf"
  "classification": "INTERNAL",
  "num_slides": 5
}
```

#### D. Document History & Download
- **History List**: `GET /api/v1/generate/history` ➔ Returns array of generated file records.
- **Binary Download**: `GET /api/v1/generate/download/{filename}` ➔ Streams binary `.pptx` or `.pdf` file.

---

### 4.4 Dual-Custody Approval Queue

When `res.policy_decision === "require_approval"`, execution is paused and an approval ticket is generated.

- **List Pending Tickets**: `GET /api/v1/approvals/pending`
- **Review Decision**: `POST /api/v1/approvals/{ticket_id}/decision`
  ```json
  {
    "decision": "approve", // "approve" | "reject"
    "notes": "Verified operational readiness and authorized deployment"
  }
  ```

---

### 4.5 Real-Time Audit Ledger Stream

#### `GET /api/v1/audit/events?limit=8`
Poll every 10 seconds to keep the security dashboard up to date.
```json
// Response
[
  {
    "id": "e4f5a6b7-...",
    "sequence_number": 42,
    "timestamp": "2026-11-17T12:00:00Z",
    "user_id": "admin",
    "role": "administrator",
    "event_type": "ai:execute",
    "action": "execute_task",
    "decision": "allow",
    "risk_level": "low",
    "event_hash": "a1b2c3d4e5f6...",
    "previous_hash": "f6e5d4c3b2a1..."
  }
]
```

---

## 5. Recommended Frontend UI Components

For building a modern, clean frontend (React, Next.js, Vue, or Svelte):

```text
┌────────────────────────────────────────────────────────────────────────┐
│  ServerGen AI Enterprise Navigation Header                             │
│  [Role Badge: Admin] [Ollama Status: Online] [Token Rotation: Active] │
├───────────────┬────────────────────────────────────────────────────────┤
│ Side Nav:     │ Main Work Area:                                        │
│ • Ask AI      │ ┌────────────────────────────────────────────────────┐ │
│ • Doc Studio  │ │ Prompt & Topic Execution Input                     │ │
│ • Knowledge   │ │ [ Sensitivity: INTERNAL v ] [ Tool: None v ]       │ │
│ • Approvals   │ │ [ Run Task ]  [ Export PPTX ]  [ Export PDF ]      │ │
│ • Audit Stream│ └────────────────────────────────────────────────────┘ │
│ • Users & RBAC│ ┌────────────────────────────────────────────────────┐ │
│               │ │ AI Response Card with Markdown & Citations         │ │
│               │ │ • Grounded Citations (Click to inspect chunk)      │ │
│               │ │ • Zero-Trust Withheld Context Notice Banner        │ │
│               │ │ • [ Export to PowerPoint ]  [ Export to PDF ]      │ │
│               │ └────────────────────────────────────────────────────┘ │
│               │ ┌────────────────────────────────────────────────────┐ │
│               │ │ Live Tamper-Evident Audit Stream (SHA-256 Hashed)  │ │
│               │ └────────────────────────────────────────────────────┘ │
└───────────────┴────────────────────────────────────────────────────────┘
```

---

## 6. Pro-Tips for Frontend Developers

1. **Authentication Interceptor**:
   In your Axios / Fetch client, store `access_token` and `refresh_token` in memory or session storage. On `401 Unauthorized`, automatically call `POST /api/v1/auth/refresh` to rotate tokens without forcing the user to log in again.
2. **One-Click Presentation Preview**:
   When `POST /api/v1/generate/presentation` returns, the response includes both `meta.download_url` and `outline.slides`. You can render slide cards directly on the screen so users can view slide headlines, categories, and takeaways before downloading the `.pptx` file!
3. **Audit Ledger Hash Badges**:
   Display a small green lock badge `<i class="lock"></i> SHA-256 Verified` on each audit entry. This communicates cryptographic tamper-evidence to enterprise compliance officers.

---
*Happy coding! ServerGen AI backend is fully initialized, tested, and ready for your frontend.*
