# ServerGen AI — Secure Enterprise Automation

> A secure prototype foundation for controlled on-premise enterprise AI automation
> using local LLM inference, policy-controlled orchestration, RBAC, human approval,
> and tamper-evident auditing.

⚠️ **This is a secure prototype foundation — not a production-ready platform.**

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for PostgreSQL)
- Ollama (for local LLM inference, optional for Phase A)

### 1. Clone and Set Up Environment

```bash
cd d:\projects\servergen-ai

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/macOS)
# source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 2. Configure Environment

```bash
# Copy example environment file
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS

# Generate a strong JWT secret
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Edit .env and set:
# - JWT_SECRET_KEY (paste the generated secret)
# - ADMIN_PASSWORD (set a strong password)
# - DATABASE_URL (if not using default Docker setup)
```

### 3. Start PostgreSQL

```bash
docker compose up -d postgres
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start the Application

```bash
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

### 6. Verify

- Health check: http://localhost:8000/health
- API docs: http://localhost:8000/docs (development only)

## Testing

```bash
# Run unit tests
pytest tests/unit/ -v

# Run with coverage (once installed)
pytest tests/unit/ -v --tb=short

# Run linting
ruff check src/ tests/
ruff format --check src/ tests/
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_ENV` | Environment mode | `development` |
| `DATABASE_URL` | PostgreSQL async connection string | (see .env.example) |
| `JWT_SECRET_KEY` | **Required.** JWT signing secret | (must be set) |
| `JWT_ALGORITHM` | JWT signing algorithm (fixed) | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | Refresh token lifetime | `10080` (7 days) |
| `MAX_LOGIN_ATTEMPTS` | Failed logins before lockout | `5` |
| `LOCKOUT_DURATION_MINUTES` | Account lockout duration | `30` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `DEFAULT_MODEL` | Default LLM model | `gemma3:4b` |

## Project Structure

```
servergen-ai/
├── src/
│   ├── app.py              # FastAPI application factory
│   ├── core/               # Configuration, database, security, middleware
│   ├── models/             # SQLAlchemy ORM models
│   ├── repositories/       # Data access layer
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic
│   ├── auth/               # RBAC, policy engine, permissions
│   ├── ai/                 # Model registry, providers, router
│   ├── agents/             # AI agent interfaces
│   ├── tools/              # Controlled tool interfaces
│   ├── orchestrator/       # Orchestration engine
│   └── api/v1/             # API route handlers
├── alembic/                # Database migrations
├── tests/
│   ├── unit/               # SQLite-backed unit tests
│   └── integration/        # PostgreSQL-backed integration tests
├── docker-compose.yml      # PostgreSQL containers
└── pyproject.toml          # Project configuration
```

## Security Architecture

- **Authentication**: OAuth2 Bearer + JWT (HS256, fixed algorithm)
- **Password Storage**: Argon2id (OWASP-recommended parameters)
- **Access Tokens**: Short-lived (15 min default)
- **Refresh Tokens**: Rotated on use, stored as hashes, family-based reuse detection
- **RBAC**: Centralized permission-based authorization
- **Policy Engine**: Deterministic ALLOW/DENY/REQUIRE_APPROVAL
- **Audit**: Tamper-Evident AI Activity Ledger (SHA-256 hash chain)
- **LLM Security**: Structured output only, no direct shell/SQL/filesystem execution

## Known Limitations

This is a secure prototype foundation suitable for further enterprise hardening.
See ARCHITECTURE.md (upcoming) for full limitations list.
