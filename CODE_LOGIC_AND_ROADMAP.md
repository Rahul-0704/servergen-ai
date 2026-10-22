# ServerGen AI — Code Logic Architecture & Future Evolution Guide

This document serves as the comprehensive engineering reference for **ServerGen AI**. It explains the current process, system flows, design invariants of **Module 1 (Secure Access & Audit)** and **Module 2 (AI Orchestrator & Local LLM)**, and provides concrete guidelines and implementation templates for future modules (Modules 3–6 and Frontend integration).

---

## Part 1: Current System Architecture (Modules 1 & 2)

```
                            [ Client / Browser ]
                                     │
                                     ▼
                ┌──────────────────────────────────────────┐
                │        FastAPI HTTP Middleware           │
                │  - RequestIDMiddleware (UUID injection)  │
                │  - StructuredLoggingMiddleware           │
                │  - CORSMiddleware (Configured origins)   │
                └────────────────────┬─────────────────────┘
                                     │
                                     ▼
                        [ API Router Layer (/api/v1) ]
                  auth.py | users.py | orchestrator.py |
                    approvals.py | audit.py | /health
                                     │
                                     ▼
                ┌──────────────────────────────────────────┐
                │          Centralized RBAC Guard          │
                │            (get_auth_context)            │
                │  1. Decode & validate JWT (fixed HS256)  │
                │  2. Live DB User lookup (instant revoke) │
                │  3. Map Role -> DB / Canonical Perms     │
                │  4. AuthorizationService: ALLOW / DENY   │
                └────────────────────┬─────────────────────┘
                                     │
         ┌───────────────────────────┴───────────────────────────┐
         ▼                                                       ▼
┌─────────────────────────────────┐             ┌─────────────────────────────────┐
│     Authentication Service      │             │     AI Orchestration Engine     │
│  - Argon2id Password Hashing    │             │  1. Task Classifier (Rule/LLM)  │
│  - Timing-Safe Verification     │             │  2. Sensitivity (Public->Restr) │
│  - JWT Issuance & Rotation      │             │  3. Risk Engine (Low/Med/High)  │
│  - Refresh Session Families     │             │  4. Policy Gate (Allow/Deny/App)│
│  - Account Lockout Tracking     │             │  5. Tool Execution / Ollama LLM │
└────────────────┬────────────────┘             │  6. Structured Output Verifier  │
                 │                              └────────────────┬────────────────┘
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │      Audit Ledger Service       │
                        │  - Append-only event tracking   │
                        │  - SHA-256 Hash Chaining        │
                        │  - Advisory-lock serialization  │
                        │  - Tamper verification probe   │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │   Repository Layer & Storage    │
                        │  SQLAlchemy 2.x Async ORM       │
                        │  PostgreSQL (asyncpg) / SQLite  │
                        └─────────────────────────────────┘
```

---

## Part 2: Current Code Logic & Data Flow

### 1. Authentication Flow (`src/services/auth_service.py`, `src/core/security.py`)
- **Password Security**: Passwords are hashed using `Argon2id` (OWASP parameters: 64MB memory, 3 iterations, 4 parallelism).
- **Anti-Enumeration**: If an unknown username is supplied, a dummy password hash verification (`verify_password_dummy()`) runs to prevent timing attacks.
- **Tokens**:
  - `access_token`: Short-lived (15 minutes), signed with fixed `HS256`, containing `sub` (User ID), `role`, `iat`, `exp`, `jti`, `iss`, `aud`.
  - `refresh_token`: Long-lived (7 days), signed with fixed `HS256`, assigned a `family_id` (UUID).
- **Session & Breach Detection**: Refresh tokens are stored in the database exclusively as SHA-256 hashes (`refresh_token_hash`). If an already revoked refresh token is submitted, the system flags token reuse, invalidates the **entire token family**, logs an audit event, and denies access.
- **Account Lockout**: After 5 failed password attempts, the account is locked for 30 minutes.

### 2. Centralized RBAC (`src/auth/rbac.py`, `src/auth/permissions.py`)
- All protected endpoints depend on `get_auth_context`.
- **Live Verification**: Authorization does not rely blindly on the JWT role claim; it looks up the live user in the database on every request to instantly catch deactivated accounts or revoked roles.
- **Roles & Permissions**:
  - `ADMIN`: Full system, document, security, report, user, audit, and AI privileges.
  - `IT_OPERATOR`: System read/execute, user read, audit read, AI read/execute.
  - `SECURITY_ANALYST`: Security read/execute, report generate, audit read, AI read.
  - `MANAGER`: Document read/write, system read, approval approve, user read, AI execute.
  - `GENERAL_EMPLOYEE`: Document read, AI read/execute (low-risk only).
- **Centralized Guard**: `require_permission(code)` triggers `AuthorizationService.require_permission()`. If denied, it writes an audit event before returning HTTP 403.

### 3. AI Orchestrator Pipeline (`src/orchestrator/engine.py`)
Every request to `POST /api/v1/ai/execute` follows a deterministic 8-step pipeline:
1. **RBAC Check**: Verifies caller holds `ai.execute`.
2. **Classification**: `TaskClassifier` categorizes the input (query, command, script, general, etc.).
3. **Data Sensitivity**: Classifies data level: `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, or `RESTRICTED`.
4. **Risk Engine**: `RiskEngine.evaluate()` calculates composite risk based on role, sensitivity, tools, and actions (`low`, `medium`, `high`, `critical`).
5. **Security Policy**:
   - `ALLOW`: Proceed directly to execution.
   - `DENY`: Immediately halt and record audit denial.
   - `REQUIRE_APPROVAL`: Suspends task execution, snapshots the operation payload and fingerprint, generates an `ApprovalRequest` record, and returns HTTP 200 with `approval_id`.
6. **Execution**:
   - If a registered tool is requested (`calculator`, `system_info`), executes safely in Python.
   - If a prompt is submitted, passes to `OllamaProvider` (default: `gemma3:4b`). If Ollama is offline, returns a clean error payload rather than crashing.
7. **Verification**: `OutputVerifier` checks output cleanliness and structured constraints.
8. **Audit Logging**: Logs the entire interaction with input metadata, decision, and risk metrics into the tamper-evident ledger.

### 4. Tamper-Evident Audit Ledger (`src/services/audit_service.py`)
- Every critical action (`LOGIN_SUCCESS`, `LOGIN_FAILURE`, `LOGOUT`, `TOKEN_REFRESH`, `AI_EXECUTE`, `TOOL_EXECUTE`, `APPROVAL_*`, `AUTHORIZATION_DENIED`) generates an `AuditEvent`.
- **Hash Chaining**: `event_hash = SHA256(previous_hash + sequence_number + timestamp + event_type + action + user_id + decision + risk_level)`.
- **Integrity Verification**: `GET /api/v1/audit/verify` recalculates the entire hash chain from event #1 to the latest event, flagging any modified, deleted, or out-of-order records.

---

## Part 3: Future Module Evolution Guide

When you begin adding the remaining modules, follow these exact architectural patterns:

```
                      CURRENT PIPELINE (Modules 1 & 2)
                                     │
                ┌────────────────────┴────────────────────┐
                ▼                                         ▼
     [ Module 3: RAG Engine ]                 [ Module 4: Ops Agent ]
     - Vector Store (pgvector)                - Sandboxed Shell Execution
     - RBAC Document Filtering                - Idempotency & Rollback
     - Semantic Chunking                      - Safe Server Diagnostics
                │                                         │
                └────────────────────┬────────────────────┘
                                     │
                ┌────────────────────┴────────────────────┐
                ▼                                         ▼
   [ Module 5: Security Agent ]              [ Module 6: Reporting Agent ]
   - Audit Log Anomaly Detection             - Automated Compliance Reports
   - Prompt Injection Heuristics             - Executive PDF/MD Generation
   - Auto-Quarantine Compromised Sessions    - Scheduled Cron Summaries
```

### 1. Implementing Module 3 — RAG & Knowledge Engine
- **Database Extension**: Add a `documents` and `document_chunks` table. Use PostgreSQL `pgvector` for embedding storage.
- **Code Location**: Create `src/rag/`:
  - `src/rag/chunker.py`: Text chunking logic with overlap.
  - `src/rag/embedder.py`: Local embedding generator (via Ollama embeddings e.g., `nomic-embed-text`).
  - `src/rag/retriever.py`: Vector similarity search.
- **RBAC Rule**: Documents MUST have a `classification` field (`public`, `internal`, `confidential`, `restricted`) and an `owner_role`. The `retriever.py` query MUST inject a WHERE clause filtering by caller permissions:
  ```python
  # Invariant: Never allow vector search to return documents higher than caller's clearance
  query = select(DocumentChunk).where(
      DocumentChunk.classification.in_(auth_context.allowed_sensitivities)
  )
  ```

### 2. Implementing Module 4 — Operations Agent
- **Safe Execution Boundary**: The agent must NEVER execute raw shell commands directly.
- **Code Location**: Create `src/agents/ops_agent.py` and tools under `src/tools/ops/`:
  - `system_metrics.py`: CPU/RAM/Disk stats (read-only, low-risk).
  - `service_restart.py`: High-risk action -> Policy Engine will intercept and force an `ApprovalRequest`.
- **Dry-Run Requirement**: All operational agents must implement a `dry_run=True` mode returning expected impacts before execution.

### 3. Implementing Module 5 — Security Agent
- **Code Location**: Create `src/agents/security_agent.py`:
  - Continually or periodically inspects `audit_events`.
  - Runs heuristic checks:
    - 5+ failed logins from same IP across accounts -> trigger IP rate-limit alert.
    - Multiple `AUTHORIZATION_DENIED` within 5 minutes -> flag session for review.
    - Inconsistent audit hash -> raise `CRITICAL` alert.

### 4. Implementing Module 6 — Reporting Agent
- **Code Location**: Create `src/agents/reporting_agent.py` and `src/api/v1/reports.py`:
  - Generates compliance audit summaries (SOC2 / ISO 27001 style).
  - Uses `AuditService` to aggregate action counts, policy denial percentages, and approval turnaround times.
  - Generates Markdown or PDF exports using existing permission `report.generate`.

---

## Part 4: Frontend Integration Guide

The prototype currently provides an interactive dashboard at `GET /test` (`test-interface.html`). When transitioning to a dedicated production frontend (e.g., React + Vite + Tailwind):

1. **Authentication Token Lifecycle**:
   - Store `access_token` in memory (or a reactive React state / pinia store).
   - Store `refresh_token` in an `HttpOnly`, `SameSite=Strict` cookie or secure storage.
   - Attach an Axios or Fetch interceptor: On HTTP 401, call `POST /api/v1/auth/refresh`. If refresh succeeds, retry the original request. If refresh returns 401/400 (reuse or expired), redirect to `/login`.
2. **Dynamic UI by Role**:
   - Call `GET /api/v1/auth/me` upon app initialization.
   - Conditionally render navigation items based on `user.role` or granted permissions.
3. **Approval Polling**:
   - When a user submits an action requiring approval, display the `approval_id` with a status polling loop (`GET /api/v1/approvals/{id}`) until status transitions from `pending` to `approved` or `rejected`.

---

## Part 5: Checklist for Future Changes

Whenever you modify or expand code logic, ensure:
1. **No Hardcoded Secrets**: Secrets must originate from `.env` via `src/core/config.py`.
2. **All Models Exported**: If a new ORM model is created, import and export it in `src/models/__init__.py`.
3. **Every Protected Route Uses Centralized RBAC**: Use `Depends(require_permission(PermissionCode....))`.
4. **All State-Changing Actions Audited**: Call `await audit_service.record(...)`.
5. **Tests Maintained**:
   - Run unit tests: `python -m pytest tests/unit -q`
   - Run end-to-end smoke tests: `python scripts/e2e_test.py`
   - Both must report 100% pass rate.
