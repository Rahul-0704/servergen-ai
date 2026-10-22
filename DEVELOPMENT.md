# ServerGen AI — Developer & Operations Guide

> **Target Audience**: Backend Engineers, DevOps / Infrastructure Teams, and Security Auditors.  
> **Repository Root**: `d:\projects\servergen-ai`

---

## 1. System Requirements & Prerequisites

- **Operating System**: Linux (Ubuntu 22.04+ / RHEL 9+) or Windows 10/11 / Windows Server 2022.
- **Python**: 3.11, 3.12, 3.13, or 3.14.
- **Database**: PostgreSQL 16+ (Docker or local service).
- **Local AI Runtime**: Ollama (listening on `http://127.0.0.1:11434`).
- **Default General Model**: `gemma3:4b` (`ollama pull gemma3:4b`).

---

## 2. Quickstart: Local Environment Setup

### 2.1 Virtual Environment & Dependencies

From the repository root:

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Upgrade pip and install all runtime + dev dependencies
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

---

## 3. Database Configuration (PostgreSQL)

ServerGen AI is built for PostgreSQL 16+ using asyncpg and SQLAlchemy 2.x async ORM.

### 3.1 Option A: Docker Compose (Recommended for Containerized Dev)
```bash
docker compose up -d postgres
```
This starts PostgreSQL 16 listening on port 5432 with default credentials:
- User: `servergen`
- Password: `changeme`
- Database: `servergen`

### 3.2 Option B: Local PostgreSQL Binaries (Air-Gapped / Portable)
The project includes a portable PostgreSQL 16 cluster pre-configured in `.pgdata/`:
```powershell
# Start PostgreSQL daemon in the background
.\.pgdist\pgsql\bin\postgres.exe -D d:\projects\servergen-ai\.pgdata
```

### 3.3 Apply Database Migrations (Alembic)
Ensure your `.env` has `DATABASE_URL` configured, then execute:

```bash
alembic upgrade head
```

This applies transactional DDL creating all 7 core tables:
- `roles`, `permissions`, `role_permissions`
- `users`, `refresh_sessions`
- `approval_requests`
- `audit_events`

### 3.4 Seed Initial Data
Seed system roles, all 15 permission mappings, and the initial administrator account:

```bash
python -m scripts.seed_db
```

Default credentials provisioned by the seed script:
- **Admin**: `username: admin`, `password: admin` (change immediately in non-dev)
- **IT Operator**: `username: operator`, `password: Operator1!`
- **Security Analyst**: `username: analyst`, `password: Analyst1!`
- **Manager**: `username: manager`, `password: Manager1!`
- **General Employee**: `username: employee`, `password: Employee1!`

---

## 4. Environment Variables (`.env`)

Create or update `.env` in the root directory:

```ini
# Application
APP_NAME="ServerGen AI"
APP_ENV=development
LOG_LEVEL=INFO
DEBUG=true

# Database: PostgreSQL (Supported production target)
DATABASE_URL=postgresql+asyncpg://servergen:changeme@127.0.0.1:5432/servergen

# CORS: Allowed origins for frontend clients (JSON list or comma-separated)
CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]

# JWT Security
# Must be at least 32 characters in staging/production
JWT_SECRET_KEY=eWHrDSCiZ4zbcqwMAgC1503Ei1SVBsSLAXioV6PNTjN2qpB2mqNAGKZyHaxuJKsJOLvotCt2fJUQgmG7O8Hinw
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_MINUTES=10080

# Account Lockout
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=30

# Ollama Local Runtime
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=gemma3:4b
```

---

## 5. Testing & Verification

### 5.1 Unit Tests (Fast, In-Memory SQLite)
Run all 115 unit tests:
```bash
pytest tests/unit -v
```

### 5.2 PostgreSQL Integration Tests (Live Database)
Verify schema compatibility, advisory locks, hash-chain generation, and user lifecycle against real PostgreSQL 16:
```bash
pytest tests/integration -v
```

### 5.3 Complete Test Suite (121 Tests)
```bash
pytest tests -v
```

### 5.4 End-to-End Live Smoke Test
Ensure the server is running on `http://127.0.0.1:8000`, then run:
```bash
python scripts/smoke_test.py
```
This script exercises all 5 system roles, checks authentication, profile lookup, authorization denials, user management, and verifies the tamper-evident hash chain continuity.

---

## 6. Code Formatting & Linting

ServerGen AI enforces strict zero-warning Python standards using Ruff:

```bash
# Check for lint errors
ruff check src tests

# Auto-fix fixable issues
ruff check --fix src tests

# Check code formatting
ruff format --check src tests

# Format all code
ruff format src tests
```

---

## 7. Running the Application

### 7.1 Start Local LLM Runtime (Ollama)
Ensure Ollama is running and pull the default model:
```bash
ollama serve
ollama pull gemma3:4b
```

### 7.2 Start FastAPI Backend Server
```bash
uvicorn src.app:app --reload --host 127.0.0.1 --port 8000
```

- **Interactive Swagger UI**: `http://127.0.0.1:8000/docs` (available in `development` mode)
- **Interactive ReDoc**: `http://127.0.0.1:8000/redoc`
- **System Health Probe**: `http://127.0.0.1:8000/api/v1/health`
- **Interactive Test Interface**: `http://127.0.0.1:8000/test`

---

## 8. Frontend Development Integration

The backend is configured to accept requests from standard Vite dev server origins (`http://localhost:5173`).

Refer to [`FRONTEND_SPECIFICATION.md`](file:///d:/projects/servergen-ai/FRONTEND_SPECIFICATION.md) for the complete React 19 + Vite + TypeScript blueprint, design tokens, route structure, and API integration hooks.
