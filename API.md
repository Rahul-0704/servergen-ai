# ServerGen AI — REST API Reference Manual

> **Base URL**: `http://localhost:8000` (or reverse proxy upstream)  
> **API Version**: `v1`  
> **Authentication**: OAuth2 Bearer Token (`Authorization: Bearer <access_token>`)  
> **Content-Type**: `application/json`

---

## Standard Error Response Format

All API errors return a standard JSON payload:

```json
{
  "detail": "Error message description",
  "error_type": "AuthorizationError",
  "request_id": "c1f7a0b5-7429-4b68-b715-9c98ef2b810f"
}
```

### Common HTTP Status Codes
- `200 OK`: Request succeeded.
- `201 Created`: Resource successfully created.
- `400 Bad Request`: Schema validation failure or invalid request parameters.
- `401 Unauthorized`: Missing, invalid, or expired access token.
- `403 Forbidden`: Insufficient permissions or operation denied by deterministic policy.
- `404 Not Found`: Target resource does not exist.
- `409 Conflict`: Resource already exists (e.g. duplicate username or email).
- `423 Locked`: Account locked out due to failed attempts OR operation requires human approval (`ApprovalRequiredError`).
- `429 Too Many Requests`: Rate limit threshold exceeded.
- `500 Internal Server Error`: Unhandled server exception.

---

## 1. System & Health Endpoints

### 1.1 Basic Health Check
Returns basic application status without database dependencies.

- **Method**: `GET`
- **Path**: `/health`
- **Auth**: None

#### Response (200 OK)
```json
{
  "status": "healthy",
  "service": "ServerGen AI",
  "environment": "development"
}
```

---

### 1.2 API Readiness Probe
Checks API version and verifies live database connectivity.

- **Method**: `GET`
- **Path**: `/api/v1/health`
- **Auth**: None

#### Response (200 OK)
```json
{
  "status": "healthy",
  "service": "ServerGen AI",
  "version": "0.1.0",
  "database": "connected"
}
```

---

## 2. Authentication API (`/api/v1/auth`)

### 2.1 User Login
Authenticates credentials using Argon2id and issues a short-lived access token and a refresh token.

- **Method**: `POST`
- **Path**: `/api/v1/auth/login`
- **Auth**: None
- **Rate Limit**: 10 attempts per 5 minutes

#### Request Body
```json
{
  "username": "admin",
  "password": "CorrectPassword123!"
}
```

#### Response (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### Error Responses
- `401 Unauthorized`: Invalid username or password (`"Invalid username or password"`).
- `423 Locked`: Account is temporarily locked due to repeated failed logins.

---

### 2.2 Rotate Refresh Token
Rotates a refresh token under family tracking and issues a new access token and refresh token.

- **Method**: `POST`
- **Path**: `/api/v1/auth/refresh`
- **Auth**: None

#### Request Body
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Response (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### Error Responses
- `401 Unauthorized`: Token invalid, expired, or previously revoked (triggers family revocation).

---

### 2.3 User Logout
Revokes the presented refresh token and terminates the session.

- **Method**: `POST`
- **Path**: `/api/v1/auth/logout`
- **Auth**: None

#### Request Body
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Response (200 OK)
```json
{
  "message": "Successfully logged out"
}
```

---

### 2.4 Current User Profile
Retrieves authenticated user identity and live assigned role.

- **Method**: `GET`
- **Path**: `/api/v1/auth/me`
- **Auth**: Bearer `<access_token>`

#### Response (200 OK)
```json
{
  "id": "e9b25f1c-d38a-49f3-8f6a-49c8d0a514d2",
  "username": "admin",
  "email": "admin@servergen.local",
  "full_name": "System Administrator",
  "role": "administrator",
  "is_active": true,
  "created_at": "2026-10-21T10:00:00Z"
}
```

---

## 3. User Management API (`/api/v1/users`)

All endpoints in this section require administrative permissions (`user.read` or `user.write`).

### 3.1 List Users
Paginated list of user accounts with optional filtering.

- **Method**: `GET`
- **Path**: `/api/v1/users`
- **Auth**: Bearer `<access_token>` (Requires `user.read`)
- **Query Parameters**:
  - `skip` (integer, default: 0): Records to skip.
  - `limit` (integer, default: 50, max: 100): Page size.
  - `active_only` (boolean, default: false): Filter active accounts.
  - `role_id` (UUID, optional): Filter by assigned role.

#### Response (200 OK)
```json
{
  "items": [
    {
      "id": "e9b25f1c-d38a-49f3-8f6a-49c8d0a514d2",
      "username": "admin",
      "email": "admin@servergen.local",
      "full_name": "System Administrator",
      "role": "administrator",
      "role_id": "3c7a0d4e-128a-4f5a-8b89-a1b2c3d4e5f6",
      "is_active": true,
      "failed_login_attempts": 0,
      "locked_until": null,
      "created_at": "2026-10-21T10:00:00Z",
      "updated_at": "2026-10-21T10:00:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 50
}
```

---

### 3.2 Create User
Provisions a new user account with Argon2id password hashing and audit logging.

- **Method**: `POST`
- **Path**: `/api/v1/users`
- **Auth**: Bearer `<access_token>` (Requires `user.write`)

#### Request Body
```json
{
  "username": "jdoe",
  "email": "jdoe@servergen.local",
  "password": "SecurePassword123!",
  "full_name": "John Doe",
  "role_id": "3c7a0d4e-128a-4f5a-8b89-a1b2c3d4e5f6"
}
```

#### Response (201 Created)
Returns the created `UserResponse` object.

#### Error Responses
- `409 Conflict`: Username or email already registered.
- `404 Not Found`: Specified `role_id` does not exist.

---

### 3.3 Get User by ID
- **Method**: `GET`
- **Path**: `/api/v1/users/{user_id}`
- **Auth**: Bearer `<access_token>` (Requires `user.read`)

#### Response (200 OK)
Returns `UserResponse` object.

---

### 3.4 Update User
Updates email, full name, role, or password. Changing password or role invalidates existing refresh sessions.

- **Method**: `PATCH`
- **Path**: `/api/v1/users/{user_id}`
- **Auth**: Bearer `<access_token>` (Requires `user.write`)

#### Request Body
```json
{
  "email": "newemail@servergen.local",
  "full_name": "Johnathan Doe",
  "role_id": "3c7a0d4e-128a-4f5a-8b89-a1b2c3d4e5f6",
  "password": "NewStrongPassword123!"
}
```

#### Response (200 OK)
Returns updated `UserResponse`.

---

### 3.5 Toggle User Status (Enable / Disable)
Activates or deactivates a user. Disabling immediately terminates all active sessions.

- **Method**: `POST`
- **Path**: `/api/v1/users/{user_id}/status`
- **Auth**: Bearer `<access_token>` (Requires `user.write`)

#### Request Body
```json
{
  "is_active": false
}
```

#### Response (200 OK)
Returns updated `UserResponse`.

---

## 4. AI Orchestration API (`/api/v1/ai`)

### 4.1 Execute AI Task
Processes an AI request through the 13-step deterministic security pipeline.

- **Method**: `POST`
- **Path**: `/api/v1/ai/execute`
- **Auth**: Bearer `<access_token>` (Requires `ai.execute`)
- **Rate Limit**: 20 requests per minute

#### Request Body
```json
{
  "task": "Summarize the plant safety incident log from yesterday.",
  "data_sensitivity": "INTERNAL",
  "tool_request": {
    "tool": "calculator",
    "parameters": {
      "expression": "450 * 1.15"
    }
  }
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `task` | `string` | The user instruction or query prompt. |
| `data_sensitivity` | `string` | Optional client-declared sensitivity (`PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`). Server inspection may escalate this value. |
| `tool_request` | `object` | Optional sandboxed tool execution (`calculator`, `system_info`). |

#### Response (200 OK)
```json
{
  "success": true,
  "output": "Incident log summary: Pressure relief valve PRV-102 operated within nominal tolerance...",
  "agent": "general_agent",
  "model": "gemma3:4b",
  "risk_level": "LOW",
  "data_sensitivity": "INTERNAL",
  "evidence": [
    "tool_output_included",
    "model=gemma3:4b",
    "provider=ollama"
  ],
  "warnings": [
    "llm_output_is_unverified_text"
  ],
  "verification": "VERIFIED",
  "execution_metadata": {
    "agent": "general_agent",
    "model": "gemma3:4b",
    "provider": "ollama",
    "prompt_tokens": 128,
    "completion_tokens": 64,
    "latency_ms": 384.2
  }
}
```

#### Error Responses
- `403 Forbidden`: `PolicyDeniedError` — operation denied by deterministic policy (e.g. general employee requesting restricted resource).
- `423 Locked`: `ApprovalRequiredError` — operation requires supervisor authorization. Returns `{ "detail": "Operation requires approval...", "approval_request_id": "<uuid>" }`.

---

### 4.2 List Registered Models
Lists registered models and hardware requirements.

- **Method**: `GET`
- **Path**: `/api/v1/ai/models`
- **Auth**: Bearer `<access_token>` (Requires `ai.execute`)

#### Response (200 OK)
```json
[
  {
    "name": "gemma3:4b",
    "provider": "ollama",
    "capabilities": ["general", "reasoning"],
    "context_length": 4096,
    "minimum_ram_gb": 4.0,
    "recommended_ram_gb": 8.0,
    "minimum_vram_gb": 0.0,
    "recommended_vram_gb": 0.0,
    "requires_gpu": false,
    "enabled": true,
    "priority": 10
  }
]
```

---

### 4.3 List Registered Agents
Lists available system agents, capabilities, and required permissions.

- **Method**: `GET`
- **Path**: `/api/v1/ai/agents`
- **Auth**: Bearer `<access_token>` (Requires `ai.execute`)

#### Response (200 OK)
```json
[
  {
    "name": "general_agent",
    "capability": "general",
    "description": "Handles general queries using the local LLM",
    "required_permission": "ai.execute"
  },
  {
    "name": "knowledge_agent",
    "capability": "knowledge",
    "description": "Document analysis (interface for Module 3 — RAG)",
    "required_permission": "document.read"
  },
  {
    "name": "operations_agent",
    "capability": "operations",
    "description": "Operational guidance (interface for Module 4 — Operations)",
    "required_permission": "operations.execute"
  },
  {
    "name": "security_agent",
    "capability": "security",
    "description": "Security posture evaluation (interface for Module 5 — Security)",
    "required_permission": "security.execute"
  },
  {
    "name": "reporting_agent",
    "capability": "reporting",
    "description": "Executive reporting (interface for Module 6 — Reporting)",
    "required_permission": "reporting.execute"
  }
]
```

---

## 5. Approval Management API (`/api/v1/approvals`)

### 5.1 List Approvals
Lists approval requests with scoping options.

- **Method**: `GET`
- **Path**: `/api/v1/approvals`
- **Auth**: Bearer `<access_token>`
- **Query Parameters**:
  - `scope` (string, default: `"mine"`):
    - `"mine"`: Requests submitted by the caller.
    - `"review"`: Requests requiring the caller's review (Requires `approval.review`).
  - `status_filter` (string, optional): `"PENDING"`, `"APPROVED"`, `"REJECTED"`, `"CANCELLED"`.
  - `skip` (integer, default: 0).
  - `limit` (integer, default: 20).

#### Response (200 OK)
```json
{
  "items": [
    {
      "id": "7f8b9c1d-2345-6789-abcd-ef0123456789",
      "request_id": "c1f7a0b5-7429-4b68-b715-9c98ef2b810f",
      "requester_id": "e9b25f1c-d38a-49f3-8f6a-49c8d0a514d2",
      "operation_type": "EXECUTE",
      "resource": "database",
      "action": "execute",
      "risk_level": "HIGH",
      "data_sensitivity": "CONFIDENTIAL",
      "operation_summary": "AI task: Restart database replication node",
      "operation_fingerprint": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
      "status": "PENDING",
      "reviewer_id": null,
      "review_notes": "",
      "reviewed_at": null,
      "consumed_at": null,
      "expires_at": "2026-10-22T10:00:00Z",
      "created_at": "2026-10-21T10:00:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

---

### 5.2 Approve Request
Approves a pending operation request under Separation of Duties.

- **Method**: `POST`
- **Path**: `/api/v1/approvals/{approval_id}/approve`
- **Auth**: Bearer `<access_token>` (Requires `approval.review`)

#### Request Body
```json
{
  "notes": "Verified maintenance window. Approved."
}
```

#### Response (200 OK)
Returns updated `ApprovalResponse` (`status: "APPROVED"`).

#### Error Responses
- `403 Forbidden`: Requester attempting to approve their own request.
- `400 Bad Request`: Request is not in `PENDING` state or has expired.

---

### 5.3 Reject Request
Rejects a pending request. Rejection notes are mandatory.

- **Method**: `POST`
- **Path**: `/api/v1/approvals/{approval_id}/reject`
- **Auth**: Bearer `<access_token>` (Requires `approval.review`)

#### Request Body
```json
{
  "notes": "Denied: Maintenance window closed."
}
```

#### Response (200 OK)
Returns updated `ApprovalResponse` (`status: "REJECTED"`).

---

### 5.4 Cancel Request
Cancels a pending request initiated by the caller.

- **Method**: `POST`
- **Path**: `/api/v1/approvals/{approval_id}/cancel`
- **Auth**: Bearer `<access_token>` (Requester only)

#### Response (200 OK)
Returns updated `ApprovalResponse` (`status: "CANCELLED"`).

---

## 6. Audit Ledger API (`/api/v1/audit`)

Guarded by `audit.read` permission.

### 6.1 List Audit Events
Returns paginated, filterable events from the tamper-evident ledger.

- **Method**: `GET`
- **Path**: `/api/v1/audit/events`
- **Auth**: Bearer `<access_token>` (Requires `audit.read`)
- **Query Parameters**:
  - `event_type` (string, optional): e.g. `LOGIN_SUCCESS`, `LLM_REQUEST`, `POLICY_DENIED`.
  - `user_id` (UUID, optional).
  - `risk_level` (string, optional): `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
  - `start_time` (ISO 8601 UTC, optional).
  - `end_time` (ISO 8601 UTC, optional).
  - `limit` (integer, default: 50).
  - `offset` (integer, default: 0).

#### Response (200 OK)
```json
{
  "items": [
    {
      "id": "9a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
      "sequence_number": 42,
      "timestamp": "2026-10-21T10:15:30Z",
      "user_id": "e9b25f1c-d38a-49f3-8f6a-49c8d0a514d2",
      "role": "administrator",
      "request_id": "c1f7a0b5-7429-4b68-b715-9c98ef2b810f",
      "event_type": "EXECUTION_COMPLETED",
      "action": "execution_completed",
      "resource": "llm",
      "decision": "allow",
      "risk_level": "LOW",
      "agent": "general_agent",
      "model": "gemma3:4b",
      "tool": "",
      "metadata": {
        "verification": "VERIFIED",
        "sensitivity": "INTERNAL"
      },
      "previous_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "event_hash": "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069"
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

---

### 6.2 Verify Audit Ledger Continuity
Verifies the cryptographic continuity of the entire audit chain from the genesis record.

- **Method**: `GET`
- **Path**: `/api/v1/audit/verify`
- **Auth**: Bearer `<access_token>` (Requires `audit.read`)

#### Response (200 OK - Valid Ledger)
```json
{
  "is_valid": true,
  "total_events": 42,
  "broken_at_sequence": null,
  "broken_event_id": null,
  "details": "Hash chain verified: 42 events, zero broken links"
}
```

#### Response (200 OK - Tampered Ledger Detected)
```json
{
  "is_valid": false,
  "total_events": 42,
  "broken_at_sequence": 28,
  "broken_event_id": "9a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "details": "Hash mismatch at sequence 28: expected 7f83b..., found a1b2c..."
}
```
