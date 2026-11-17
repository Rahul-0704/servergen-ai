# ServerGen AI — Frontend Developer & Integration Guide

Welcome to the **ServerGen AI** backend integration guide! This document is designed for frontend developers building modern client applications (React, Next.js, Vue, Svelte, Angular, React Native, or Mobile) on top of ServerGen AI.

---

## 1. Quick Start for Frontend Developers

### 1.1 Backend Service URLs
- **API Base URL**: `http://127.0.0.1:8000`
- **Interactive Swagger Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Built-in Reference Dashboard**: [http://127.0.0.1:8000/test](http://127.0.0.1:8000/test)
- **API Health Check**: `GET http://127.0.0.1:8000/api/v1/health`

### 1.2 CORS Support
The backend allows CORS requests from all standard local development servers:
- `http://localhost:3000` (Next.js / Create React App)
- `http://localhost:5173` (Vite / React / Vue / Svelte)
- `http://127.0.0.1:3000` & `http://127.0.0.1:5173`
- `http://localhost:8080`

### 1.3 Pre-Seeded Development Accounts

| Username | Password | Role | Clearance Level | Primary Responsibilities |
| :--- | :--- | :--- | :--- | :--- |
| `admin` | `admin123456` | `administrator` | `RESTRICTED` | Full system control, user management, audit logs, policy overrides |
| `manager` | `manager123456` | `manager` | `CONFIDENTIAL` | Operational approvals, departmental documents, report generation |
| `operator` | `operator123456` | `it_operator` | `CONFIDENTIAL` | System diagnostics, runbooks, server operations |
| `analyst` | `analyst123456` | `security_analyst` | `INTERNAL` | RAG analytical queries, audit reviews, policy checks |
| `employee` | `employee123456` | `general_employee` | `PUBLIC` | General knowledge queries, public documents |

---

## 2. Authentication & Authorization Flow

ServerGen AI enforces **Argon2id** password hashing and **cryptographic JWT** (HS256) session tokens.

### 2.1 Login (`POST /api/v1/auth/login`)
Send user credentials to receive rotating tokens:

```typescript
// Request
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin123456"
}

// Response (HTTP 200)
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in": 900 // 15 minutes
}
```

### 2.2 Authenticated Requests Header
Include the access token on all protected endpoints:
```http
Authorization: Bearer <access_token>
```

### 2.3 User Profile (`GET /api/v1/auth/me`)
```typescript
GET /api/v1/auth/me
Authorization: Bearer <access_token>

// Response (HTTP 200)
{
  "id": "ad3b42c1-3390-4ff7-9312-82d78555a695",
  "username": "admin",
  "email": "admin@servergen.local",
  "full_name": "System Administrator",
  "role": "administrator",
  "permissions": ["system.admin", "ai.execute", "document.read", "document.write", ...]
}
```

### 2.4 Token Refresh (`POST /api/v1/auth/refresh`)
```typescript
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn..."
}
```

---

## 3. Core Feature Endpoints & API Contracts

### 3.1 Document & Slide Studio (PDF & PowerPoint Generation)
Generate publication-quality PDF reports and widescreen 16:9 PowerPoint presentations directly using the local Ollama LLM (`llama3.2:3b`).

#### A. Generate PowerPoint Presentation (.pptx)
```typescript
POST /api/v1/generate/presentation
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "topic": "Enterprise Zero Trust Cloud Architecture & Governance",
  "num_slides": 5, // 3 to 12 slides
  "classification": "CONFIDENTIAL", // PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED
  "context": "Optional technical constraints or key requirements...",
  "model": "llama3.2:3b" // optional override
}

// Response (HTTP 200)
{
  "success": true,
  "message": "Generated 5-slide presentation successfully.",
  "meta": {
    "file_id": "0fe51e57-743",
    "filename": "0fe51e57-743_Enterprise_Zero_Trust.pptx",
    "format": "pptx",
    "file_size": 43792,
    "title": "Enterprise Zero Trust Cloud Architecture",
    "summary": "Widescreen 16:9 Presentation with 5 slides.",
    "download_url": "/api/v1/generate/download/0fe51e57-743_Enterprise_Zero_Trust.pptx",
    "created_at": "2026-11-17T05:30:00Z",
    "slide_or_page_count": 5
  },
  "outline": {
    "title": "Enterprise Zero Trust Cloud Architecture",
    "slides": [
      {
        "title": "Executive Overview & Objectives",
        "category": "STRATEGY",
        "bullets": ["Point 1...", "Point 2..."],
        "key_takeaway": "Takeaway 1...",
        "notes": "Speaker notes..."
      }
    ]
  }
}
```

#### B. Generate Executive PDF Report (.pdf)
```typescript
POST /api/v1/generate/pdf
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "topic": "Incident Response Retrospective & Remediation Plan",
  "classification": "INTERNAL",
  "context": "Details regarding the recent service event and mitigation steps..."
}

// Response (HTTP 200)
{
  "success": true,
  "message": "Generated executive PDF report successfully.",
  "meta": {
    "file_id": "2ed602dc-eb3",
    "filename": "2ed602dc-eb3_Incident_Response_Plan.pdf",
    "format": "pdf",
    "file_size": 18240,
    "title": "Incident Response Retrospective & Remediation Plan",
    "download_url": "/api/v1/generate/download/2ed602dc-eb3_Incident_Response_Plan.pdf",
    "created_at": "2026-11-17T05:30:00Z"
  },
  "outline": {
    "executive_summary": "High-density synthesis...",
    "sections": [
      {
        "heading": "1. Root Cause Analysis",
        "content": "Narrative explanation...",
        "bullet_points": ["Item 1", "Item 2"],
        "key_metric": "Mean Time to Recovery: 18 minutes"
      }
    ],
    "recommendations": ["Step 1", "Step 2"]
  }
}
```

#### C. Grounded Generation from RAG Knowledge Base
```typescript
POST /api/v1/generate/from-rag
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "query": "Kubernetes cluster failure recovery and backup policies",
  "target_format": "pptx", // "pdf" or "pptx"
  "num_slides": 5,
  "classification": "INTERNAL"
}
```

#### D. Download Generated File
```http
GET /api/v1/generate/download/{file_id_or_filename}
```
*Note: This endpoint can be linked directly with `<a href="/api/v1/generate/download/..." download>`. No Bearer token required on the download link for straightforward browser file saving.*

#### E. Generation History (`GET /api/v1/generate/history`)
```typescript
GET /api/v1/generate/history
Authorization: Bearer <access_token>
```

---

### 3.2 AI Task Execution & Orchestration (`POST /api/v1/ai/execute`)
Executes user queries through the 10-stage security pipeline (classification &rarr; sensitivity &rarr; risk &rarr; policy &rarr; local LLM &rarr; verification &rarr; audit).

```typescript
POST /api/v1/ai/execute
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "input": "Summarize our cloud security runbook and list critical steps",
  "data_sensitivity": "internal", // public, internal, confidential, restricted
  "model": "llama3.2:3b", // optional
  "tool": null, // or "calculator", "system_info", "pdf_generator", "presentation_generator"
  "tool_parameters": {},
  "structured": false
}

// Successful Response (HTTP 200)
{
  "request_id": "f83b27b9-1d4e-4f06-9321-12a849f12345",
  "task_category": "knowledge_retrieval",
  "risk_level": "low",
  "policy_decision": "allow",
  "model_used": "llama3.2:3b",
  "content": "### Executive Summary\n...\n### Technical Breakdown & Core Concepts\n...\n### Best Practices\n...",
  "evidence": ["rag_knowledge_grounding", "model=llama3.2:3b"],
  "citations": [
    {
      "document_id": "61d77109-8472-4ce0-a29d-bd83196a090b",
      "title": "Cloud Security Architecture Spec",
      "page_number": 2,
      "snippet": "All microservices must enforce mutual TLS..."
    }
  ],
  "verification_status": "verified",
  "success": true
}

// When Policy Requires Dual-Custody Approval (HTTP 200)
{
  "request_id": "...",
  "policy_decision": "require_approval",
  "approval_id": "a55d53ab-...",
  "error": "Operation requires approval: High-risk system modification",
  "success": false
}
```

---

### 3.3 Enterprise Knowledge Base (RAG & Storage)

#### A. Upload Document (`POST /api/v1/rag/upload`)
Uploads `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.csv`, `.txt`, `.md`, or `.html` files:
```typescript
POST /api/v1/rag/upload
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <File Binary>
title: "Production Infrastructure Runbook"
category: "operations" // general, technical, hr, finance, legal, security, operations
classification: "confidential" // public, internal, confidential, restricted
description: "Standard operating procedures for container nodes"
```

#### B. List Documents (`GET /api/v1/rag/documents`)
```typescript
GET /api/v1/rag/documents?page=1&limit=20&search=infrastructure
Authorization: Bearer <access_token>
```

#### C. Grounded RAG Query (`POST /api/v1/rag/test/grounded`)
```typescript
POST /api/v1/rag/test/grounded
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "query": "What are the database connection pool thresholds?",
  "top_k": 4,
  "min_relevance": 0.25
}
```

---

### 3.4 Governance: Dual-Custody Approvals

#### A. List Pending Approvals (`GET /api/v1/approvals/pending`)
```typescript
GET /api/v1/approvals/pending
Authorization: Bearer <access_token>
```

#### B. Approve / Reject Request (`POST /api/v1/approvals/{id}/approve` or `/reject`)
```typescript
POST /api/v1/approvals/{approval_id}/approve
Authorization: Bearer <access_token> // Requires Manager or Admin role
Content-Type: application/json

{
  "comments": "Verified and approved for execution."
}

// Response includes the auto-executed result!
{
  "id": "a55d53ab-...",
  "status": "approved",
  "execution_result": {
    "content": "Execution output...",
    "success": true
  }
}
```

---

### 3.5 Tamper-Evident Audit Ledger

#### A. Query Ledger Events (`GET /api/v1/audit/events`)
```typescript
GET /api/v1/audit/events?limit=25&event_type=ai:execute
Authorization: Bearer <access_token>
```

#### B. Verify Cryptographic SHA-256 Chain (`GET /api/v1/audit/verify`)
```typescript
GET /api/v1/audit/verify
Authorization: Bearer <access_token>

// Response
{
  "status": "verified",
  "events_checked": 1125,
  "broken_at_sequence": null,
  "reason": ""
}
```

---

## 4. Ready-to-Use Frontend Client (TypeScript / Axios)

Save this file in your frontend repository as `src/lib/api.ts`:

```typescript
import axios from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Automatic token attachment
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Automatic 401 handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem('access_token', res.data.access_token);
          if (res.data.refresh_token) {
            localStorage.setItem('refresh_token', res.data.refresh_token);
          }
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`;
          return axios(error.config);
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

// High-level API helper functions
export const api = {
  // Auth
  login: (username: string, password: string) =>
    apiClient.post('/api/v1/auth/login', { username, password }),
  getProfile: () => apiClient.get('/api/v1/auth/me'),

  // Document & Presentation Studio
  generatePresentation: (topic: string, numSlides = 5, classification = 'INTERNAL', context = '') =>
    apiClient.post('/api/v1/generate/presentation', { topic, num_slides: numSlides, classification, context }),
  generatePDF: (topic: string, classification = 'INTERNAL', context = '') =>
    apiClient.post('/api/v1/generate/pdf', { topic, classification, context }),
  getGenerationHistory: () => apiClient.get('/api/v1/generate/history'),
  getDownloadUrl: (filename: string) => `${BASE_URL}/api/v1/generate/download/${filename}`,

  // AI & RAG
  executeAI: (input: string, dataSensitivity = 'internal', model?: string) =>
    apiClient.post('/api/v1/ai/execute', { input, data_sensitivity: dataSensitivity, model }),
  uploadDocument: (formData: FormData) =>
    apiClient.post('/api/v1/rag/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  getDocuments: () => apiClient.get('/api/v1/rag/documents'),

  // Governance
  getPendingApprovals: () => apiClient.get('/api/v1/approvals/pending'),
  approveTicket: (id: string, comments = '') =>
    apiClient.post(`/api/v1/approvals/${id}/approve`, { comments }),
  verifyAuditLedger: () => apiClient.get('/api/v1/audit/verify'),
};
```

---

## 5. Suggested Frontend Page Structure

To create a clean, modern user experience, we recommend structuring your frontend with the following navigation layout:

1. **Dashboard Overview** (`/` or `/dashboard`)
   - Telemetry pills: Backend Health, Active Local Model (`llama3.2:3b`), Logged-in User & Role Badge
   - Quick Action Cards: Start AI Query, Upload Knowledge Doc, Generate Presentation, Pending Approvals Count
2. **AI Assistant & Grounded Chat** (`/chat`)
   - Conversational or task-based prompt interface with sensitivity pills (`PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`)
   - Grounded citations card with document references and page tags
   - Dual-custody approval banner when an operation triggers a security review
3. **Document & Slide Studio** (`/studio`)
   - Dual tabs: "PowerPoint Presentation (16:9 PPTX)" vs "Executive PDF Report"
   - Prompt input, slide count selector (3-12), and security classification picker
   - Live rendered outline preview (slides or section breakdown)
   - One-click Download button directly pulling from `/api/v1/generate/download/{file_id}`
   - Recent generations table
4. **Knowledge Base Repository** (`/documents`)
   - Drag-and-drop document uploader with file type validation (.pdf, .docx, .xlsx, .pptx, .csv, .md)
   - Searchable document table with classification badges, owner, and chunk preview modal
5. **Approvals & Governance** (`/approvals`)
   - Pending tickets queue with risk level pills (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
   - One-click Approve/Reject buttons (for Managers & Administrators) with immediate execution preview
6. **Security & Cryptographic Audit** (`/audit`)
   - Real-time audit events timeline
   - "Verify Ledger Integrity" button showing SHA-256 hash chain status (0 broken links)
