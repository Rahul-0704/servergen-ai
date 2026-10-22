# ServerGen AI — Frontend Architecture & Implementation Guide

> **Target Audience**: Frontend Engineering Team / Developer Partner  
> **Backend Base**: FastAPI (Python 3.12+), PostgreSQL, Ollama (Local LLM)  
> **Backend Port**: `http://localhost:8000` (API prefix: `/api/v1`)  
> **App Persona**: Mission-critical, self-hosted enterprise AI workbench for PSUs, refineries, defense, and high-security air-gapped environments.  
> **Design Philosophy**: High density, data-first, industrial dark theme, telemetry-aware, zero-trust deterministic controls.

---

## 1. Executive Overview & Domain Model

ServerGen AI is **NOT** a generic consumer chatbot. It is a **controlled enterprise automation workbench**.
In this system:
1. **The LLM never directly executes actions**: It proposes outputs, but tools, policy, and risk engines strictly control what happens.
2. **Every request is classified & risk-assessed**: Requests are assigned a Data Sensitivity (`PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`) and a Risk Level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
3. **High/Critical actions require Human-in-the-Loop Approval**: The API will block execution and issue an `approval_id`. The user (or manager/admin) must approve it before execution can proceed.
4. **Every action is recorded in a Tamper-Evident Ledger**: A SHA-256 hash-chained audit log tracks all logins, policy denials, executions, and approvals.
5. **Role-Based Access Control (RBAC)**: Five distinct roles (`administrator`, `it_operator`, `security_analyst`, `manager`, `general_employee`) dictate what tabs, buttons, models, and tools are available.

---

## 2. Recommended Frontend Tech Stack

| Layer | Recommended Technology | Why Chosen |
|---|---|---|
| **Build Tool & Framework** | **Vite + React 19 + TypeScript (Strict)** | Fast, lightweight SPA. Builds directly into static assets (`frontend/dist`) that FastAPI can serve natively without requiring a separate Node.js production server. |
| **Styling** | **Tailwind CSS v4** | Rapid styling with industrial theme tokens (slate, zinc, emerald, amber, red). |
| **Component Library** | **shadcn/ui (Radix Primitives)** | Accessible, zero-runtime overhead, copy-paste ownership of components (Buttons, Modals, Drawers, Tables, Tabs). |
| **Icons** | **Lucide React** | Clean, technical icon set (Shield, Terminal, Cpu, FileCheck, Lock, Activity). |
| **Server State & Caching** | **TanStack Query (React Query) v5** | Automated background polling, optimistic updates, request caching, and retry logic for high-availability systems. |
| **Client State** | **Zustand** | Minimalist store for authentication tokens, active user profile, theme, and draft execution payloads. |
| **HTTP Client** | **Axios or Ky** | Automatic token refresh interceptors, abort controllers, request ID headers. |
| **Markdown & Syntax** | **react-markdown + remark-gfm + rehype-highlight** | Rendering AI output with tables, code blocks, and copy-to-clipboard actions. |
| **Notifications** | **Sonner** | Modern toast system for policy denials, approval triggers, and system events. |

---

## 3. System Architecture & Directory Layout

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
└── src/
    ├── app/
    │   ├── App.tsx                     # Top-level routing & layout wrapper
    │   ├── routes.tsx                  # React Router v6/v7 route definitions
    │   └── providers.tsx               # QueryClient, Theme, Toast providers
    ├── api/
    │   ├── client.ts                   # Axios/Ky instance with Bearer & Refresh interceptors
    │   ├── auth.ts                     # Login, refresh, logout, me
    │   ├── orchestrator.ts             # Execute task, list models, list agents
    │   ├── approvals.ts                # List, get, approve, reject, cancel
    │   ├── audit.ts                    # List events, verify chain, event details
    │   └── types.ts                    # Exact TypeScript interfaces matching backend Pydantic models
    ├── components/
    │   ├── ui/                         # shadcn/ui components (button, dialog, badge, table, etc.)
    │   ├── layout/
    │   │   ├── Header.tsx              # Top telemetry bar, model status, user menu
    │   │   ├── Sidebar.tsx             # Role-filtered navigation links
    │   │   └── AppLayout.tsx           # Main container with responsive split
    │   ├── shared/
    │   │   ├── SensitivityBadge.tsx    # PUBLIC (gray), INTERNAL (blue), CONFIDENTIAL (purple), RESTRICTED (red)
    │   │   ├── RiskBadge.tsx           # LOW (green), MEDIUM (yellow), HIGH (orange), CRITICAL (red pulsating)
    │   │   ├── VerificationPill.tsx    # VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, FAILED
    │   │   ├── FingerprintView.tsx     # Truncated hash with copy action & full tooltip
    │   │   └── CodeBlock.tsx           # Syntax highlighted code snippets
    ├── features/
    │   ├── auth/
    │   │   ├── LoginPage.tsx           # Login form, lockout countdown, dev account switcher
    │   │   └── AuthGuard.tsx           # Route protection based on permissions
    │   ├── workbench/
    │   │   ├── WorkbenchPage.tsx       # Main AI workspace
    │   │   ├── TaskInputForm.tsx       # Text input, sensitivity picker, tool options
    │   │   ├── ExecutionResult.tsx     # Render response, evidence tags, warnings
    │   │   └── ApprovalInterceptModal.tsx # Popup when task requires approval
    │   ├── approvals/
    │   │   ├── ApprovalsInboxPage.tsx  # Tabs: "My Requests" and "Review Queue"
    │   │   ├── ApprovalCard.tsx        # Summary card with fingerprint & status
    │   │   └── ApprovalActionDialog.tsx# Reviewer notes & approve/reject buttons
    │   ├── audit/
    │   │   ├── AuditLedgerPage.tsx     # Filterable tamper-evident log table
    │   │   ├── ChainIntegrityBanner.tsx# Real-time green/red ledger integrity badge
    │   │   └── AuditDetailDrawer.tsx   # JSON inspection of canonical event & hash link
    │   └── system/
    │       ├── ModelsPage.tsx          # Registered models & hardware requirements
    │       └── HealthDashboard.tsx     # DB connection probe & Ollama runtime status
    ├── hooks/
    │   ├── useAuth.ts                  # Login/logout actions & current permissions
    │   ├── useTaskExecution.ts         # Mutation for submitting AI tasks
    │   └── useChainVerification.ts     # Query to check ledger integrity
    └── store/
        └── authStore.ts                # Access token, user, role in memory/storage
```

---

## 4. Complete API Contracts & TypeScript Interfaces

### 4.1 Base Configuration
- **API Base URL**: `http://localhost:8000` (or relative `/` when served by FastAPI static)
- **Default Headers**:
  - `Content-Type: application/json`
  - `Authorization: Bearer <access_token>`
  - `X-Request-ID: <auto-generated-uuid>` (for correlation)

### 4.2 TypeScript Type Definitions (`src/api/types.ts`)

```typescript
// --- ENUMS & CONSTANTS ---
export type SystemRole = 
  | 'administrator'
  | 'it_operator'
  | 'security_analyst'
  | 'manager'
  | 'general_employee';

export type DataSensitivity = 'public' | 'internal' | 'confidential' | 'restricted';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type PolicyDecision = 'allow' | 'deny' | 'require_approval';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'cancelled';
export type VerificationStatus = 'verified' | 'partially_verified' | 'unverified' | 'failed';

// --- AUTHENTICATION ---
export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string; // 'bearer'
  expires_in: number; // in seconds (e.g. 900 = 15 mins)
}

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: SystemRole;
  is_active: boolean;
  last_login: string | null;
  created_at: string;
}

// --- AI ORCHESTRATOR ---
export interface TaskRequest {
  input: string;
  data_sensitivity: DataSensitivity;
  tool?: string | null;
  tool_parameters?: Record<string, unknown>;
}

export interface TaskResponse {
  request_id: string;
  task_category: string;
  risk_level: RiskLevel;
  policy_decision: PolicyDecision;
  model_used: string;
  content: string;
  verification_status: VerificationStatus;
  tool_used: string;
  tool_output: string;
  success: boolean;
  error: string;
  approval_id: string | null;
  agent_used: string;
  operation_type: string;
  data_sensitivity: string;
  production_affecting: boolean;
  evidence: string[];
  warnings: string[];
}

export interface ModelMetadata {
  name: string;
  provider: string;
  capabilities: string[];
  context_length: number;
  requires_gpu: boolean;
  minimum_ram_gb: number;
  minimum_vram_gb: number;
  enabled: boolean;
}

export interface AgentMetadata {
  name: string;
  capability: string;
  description: string;
  required_permission: string;
}

// --- APPROVALS ---
export interface ApprovalResponse {
  id: string;
  request_id: string;
  requester_user_id: string;
  requester_role: string;
  operation_summary: string;
  operation_fingerprint: string;
  status: ApprovalStatus;
  risk_assessment_json: {
    risk_level: RiskLevel;
    factors: string[];
    requires_approval: boolean;
  } | null;
  task_classification_json: {
    category: string;
    operation_type: string;
  } | null;
  reviewer_user_id: string | null;
  reviewer_notes: string | null;
  created_at: string;
  expires_at: string;
  resolved_at: string | null;
  consumed_at: string | null;
}

export interface ApprovalPage {
  items: ApprovalResponse[];
  total: number;
  skip: number;
  limit: number;
}

export interface ApprovalActionRequest {
  notes?: string;
}

// --- AUDIT LEDGER ---
export interface AuditEventResponse {
  id: string;
  sequence_number: number;
  timestamp: string;
  user_id: string | null;
  role: string | null;
  request_id: string;
  event_type: string;
  action: string;
  resource: string | null;
  decision: string;
  risk_level: string;
  agent: string | null;
  model: string | null;
  tool: string | null;
  metadata_json: Record<string, unknown> | null;
  previous_hash: string | null;
  event_hash: string;
}

export interface AuditEventPage {
  items: AuditEventResponse[];
  total: number;
  skip: number;
  limit: number;
}

export interface AuditChainVerification {
  status: 'verified' | 'broken';
  events_checked: number;
  broken_at_sequence: number | null;
  reason: string;
}

// --- HEALTH & STATUS ---
export interface HealthStatus {
  status: 'healthy' | 'degraded';
  service: string;
  version: string;
  database: 'connected' | 'unavailable';
}
```

---

## 5. Security Architecture & Token Rotation (Frontend Rules)

### Token Storage & Lifecycle
1. **Access Token**: Store in **Zustand memory** (fast, safe from XSS exfiltration).
2. **Refresh Token**: Store in `localStorage` (or secure session storage) so users stay logged in across tab reloads.
3. **Automatic Refresh Interceptor**:
   - When any API call returns `401 Unauthorized` with `code === "TOKEN_EXPIRED"` or `AUTHENTICATION_FAILED`:
   - Intercept the failure, pause pending requests in a promise queue.
   - Send `POST /api/v1/auth/refresh` with `{ refresh_token }`.
   - Update memory with the newly issued `access_token` and `refresh_token`.
   - Re-execute the original failed requests.
   - If the refresh token is expired or reuse is detected (ServerGen AI revokes token families upon reuse), immediately purge tokens and redirect to `/login` with an alert: `"Session expired or security reset. Please log in again."`

### Handling Account Lockout
- If a login fails with status code `423` or `code === "ACCOUNT_LOCKED"`, the backend locks the user for 30 minutes.
- The UI should display a countdown badge / warning: *"Account locked due to multiple failed login attempts. Contact an IT Administrator or try again in 30 minutes."*

---

## 6. Page-by-Page Feature Specifications

### 6.1 Authentication Screen (`/login`)
- **Visuals**: Clean dark glassmorphic card on dark slate background with ServerGen AI shield badge.
- **Fields**: Username, Password, Submit button with loading spinner.
- **Developer Quick-Switch (Essential for pair testing)**:
  Provide a test-account helper drawer or bottom pill bar allowing 1-click credential autofill:
  - `admin` (Administrator)
  - `operator` (IT Operator)
  - `analyst` (Security Analyst)
  - `manager` (Manager)
  - `employee` (General Employee)

---

### 6.2 AI Automation Workbench (`/workbench`)
The core user interface for task execution.
- **Top Bar**:
  - Current Model Indicator (e.g. `gemma3:4b (Ollama Local)`).
  - Data Sensitivity Selector:
    - `PUBLIC` (Readily shareable data)
    - `INTERNAL` (Default enterprise data)
    - `CONFIDENTIAL` (Departmental, HR, Financial - elevates risk to MEDIUM/HIGH)
    - `RESTRICTED` (Classified / Defense / Secrets - triggers HIGH/CRITICAL & approval)
  - Tool Invocation Toggle (Optional):
    - None (Pure AI Query)
    - `calculator` (Safe AST mathematical evaluator)
    - `system_info` (Read-only OS & Python runtime info)
- **Input Area**:
  - Multi-line autosizing prompt textarea (`Ctrl+Enter` to submit).
  - Sensitivity warning callout if user types sensitive keywords (e.g., regex checks for `classified`, `credentials`, `firewall`).
- **Response Section**:
  - **Status Bar**:
    - Policy Decision Pill (`ALLOW` = Green, `REQUIRE_APPROVAL` = Yellow, `DENY` = Red).
    - Calculated Risk Badge (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
    - Verification Tag (`VERIFIED` = Checked, `UNVERIFIED` = Alert icon).
    - Agent attribution tag (e.g. `general_agent`, `operations_agent`, `security_agent`).
  - **Evidence Tags**: Display badges from `result.evidence` (e.g. `tool_output_included`, `model=gemma3:4b`).
  - **Advisory Warnings**: If `result.warnings` has items (e.g. `advisory_only: no operational action was executed`), render an amber callout box.
  - **Output Body**: Formatted markdown with copy-to-clipboard button.
- **Special Flow — Approval Required Modal**:
  - If `result.policy_decision === "require_approval"`, pop up an interactive banner:
    > **⚠️ Operation Requires Approval**  
    > This task was flagged as **HIGH/CRITICAL risk**. An approval request has been generated.  
    > **Approval ID**: `3f8a1...`  
    > *Action required by Manager or Administrator before system will process this task.*
    > `[View in Approvals Queue]` button.

---

### 6.3 Approvals Management Center (`/approvals`)
Enforces separation of duties and administrative control over risky actions.
- **Header**: Tab switch between:
  1. `My Requests` (`scope=mine`): Approvals requested by the currently logged-in user.
  2. `Review Queue` (`scope=review`): Requests from *other* users waiting for a decision (requires `approval.approve` permission; hidden or disabled for `general_employee`).
- **Table / Card List**:
  - Request ID & Timestamp.
  - Requester Name & Role.
  - Operation Summary.
  - Risk Level & Contributing Factors list.
  - Operation Fingerprint: Deterministic SHA-256 hash. Shows first 8 chars + copy button.
  - Status Badge: `PENDING` (Pulse amber), `APPROVED` (Green), `REJECTED` (Red), `EXPIRED` (Gray), `CANCELLED` (Slate).
- **Actions**:
  - **Approve**: Opens modal with optional reviewer notes. *Separation of duties guard*: You cannot approve your own request.
  - **Reject**: Opens modal with required rejection notes.
  - **Cancel**: Only available to the original requester on `PENDING` items.

---

### 6.4 Tamper-Evident Audit Ledger Explorer (`/audit`)
Inspects the cryptographic hash chain of system activity.
- **Integrity Status Banner (Top)**:
  - Calls `GET /api/v1/audit/verify`.
  - If `status === "verified"`: Green banner with shield icon:  
    `[✓ LEDGER INTEGRITY VERIFIED] — 142 events checked in hash-chain sequence. Zero anomalies detected.`
  - If `status === "broken"`: High-contrast red flashing alert:  
    `[🚨 TAMPER DETECTED] — Hash mismatch at sequence #34. Previous hash continuity severed.`
- **Filter Bar**:
  - Filter by Event Type (`login_success`, `policy_denied`, `approval_created`, `llm_request`, etc.).
  - Filter by Decision (`allow`, `deny`, `require_approval`).
  - Filter by Risk Level (`low`, `medium`, `high`, `critical`).
  - Search by User ID or Request ID.
- **Event Log Table**:
  - `# Seq` (Sequence number)
  - Timestamp (UTC)
  - Event Type & Action
  - User & Role
  - Decision & Risk Badge
  - Event Hash (monospaced truncated `4f9a...e12d`)
  - Chain Link icon indicating link to `previous_hash`
- **Audit Detail Drawer**:
  - Click any row to slide open a drawer with complete JSON metadata, actor IP/User-Agent, full 64-character SHA-256 hash, and previous hash.

---

### 6.5 System Status & Hardware Telemetry (`/system`)
- **Backend Readiness**: Database connection status (`connected` vs `unavailable`), application environment mode (`development` vs `production`).
- **Model Registry Table**:
  - Lists models from `GET /api/v1/ai/models`.
  - Displays: Model Name, Provider (`ollama`), Context Length, Minimum RAM, Minimum VRAM, GPU requirement badge (`GPU Required` vs `CPU Safe`).
- **Registered Agents Table**:
  - Lists agents from `GET /api/v1/ai/agents`.
  - Displays Agent Name, Capability, Description, Required Permission.

---

## 7. Role-Based Navigation & Permissions Matrix

The UI must adapt dynamically depending on the current user's role:

| Feature / Screen | Administrator | IT Operator | Security Analyst | Manager | General Employee |
|---|:---:|:---:|:---:|:---:|:---:|
| **AI Workbench (`/workbench`)** | Full Access | Full Access | Read-Only / Advisory | Full Access | Full Access (Internal/Public) |
| **Data Sensitivity Selector** | Can select up to `RESTRICTED` | Can select up to `CONFIDENTIAL` | Can select up to `RESTRICTED` | Can select up to `CONFIDENTIAL` | Capped at `INTERNAL` |
| **Review Approvals (`/approvals?scope=review`)** | ✅ Full (incl. Critical) | ❌ | ❌ | ✅ (Up to High risk) | ❌ |
| **View Audit Ledger (`/audit`)** | ✅ Full | ✅ Full | ✅ Full | ❌ | ❌ |
| **Verify Hash Chain** | ✅ Yes | ✅ Yes | ✅ Yes | ❌ | ❌ |
| **System Telemetry (`/system`)** | ✅ Full | ✅ Full | ✅ Full | View Only | ❌ |

---

## 8. Optional & Future-Ready Enhancements (Phase 2 Roadmap)

Give these options to your developer friend to plan ahead:

1. **Streaming Responses (SSE / WebSockets)**:
   - Prepare the UI with a typing effect or prepare a hook for chunk-based streaming when the backend introduces Server-Sent Events (SSE) for Gemma 3 4B.
2. **Module 3 — RAG Knowledge Base Viewer**:
   - Tab for document uploading and viewing chunk citations alongside AI answers.
3. **Module 4 — Operations Agent Safe Terminal**:
   - Read-only simulation terminal showing step-by-step operational guidance for plant/refinery engineers with checkbox validation before execution.
4. **Module 5 — Security Posture Dashboard**:
   - Compliance posture score (CVEs, failed logins graph, unauthorized access attempts heat map).
5. **PDF / CSV Audit Ledger Export**:
   - Export filtered audit ledger logs into signed PDF/CSV reports for regulatory compliance auditors.
6. **Air-Gapped Offline PWA**:
   - Offline service worker caching so the UI shell functions reliably even during internal network disconnects.

---

## 9. Developer Quickstart Instructions

Share these exact steps with the frontend developer:

### Step 1: Scaffold Vite Project
```bash
# In the repository root:
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

### Step 2: Install Core Dependencies
```bash
npm install lucide-react clsx tailwind-merge @tanstack/react-query axios zustand sonner react-router-dom react-markdown remark-gfm
npm install -D tailwindcss @tailwindcss/vite
```

### Step 3: Configure Vite API Proxy (`frontend/vite.config.ts`)
```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
  }
});
```

### Step 4: Environment File (`frontend/.env.development`)
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_NAME="ServerGen AI Workbench"
```

### Step 5: Test Accounts for Development
The backend database seed (`python -m scripts.seed_db`) provides these 5 active accounts ready for immediate testing:
- **Admin**: `admin` / `admin` (or configured `ADMIN_PASSWORD`)
- **IT Operator**: `operator` / `Operator1!`
- **Security Analyst**: `analyst` / `Analyst1!`
- **Manager**: `manager` / `Manager1!`
- **General Employee**: `employee` / `Employee1!`
