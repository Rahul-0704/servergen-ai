"""
Unit Tests — RAG & Document Management API Endpoints.

Verifies:
1. POST /api/v1/rag/upload (multipart file upload).
2. GET /api/v1/rag/documents (authorized listing).
3. POST /api/v1/rag/test/retrieval (RAG Lab retrieval-only testing).
4. POST /api/v1/rag/test/evaluation (RAG evaluation benchmark suite).
5. GET /api/v1/rag/health (Subsystem health probe).
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.security import create_access_token, hash_password
from src.models.role import Role
from src.models.user import User


async def _setup_users(db: AsyncSession) -> tuple[str, str]:
    """Create test admin and employee, returning their JWT access tokens."""
    roles = {}
    for name in ("administrator", "general_employee"):
        res = await db.execute(select(Role).where(Role.name == name))
        existing = res.scalar_one_or_none()
        if existing is not None:
            roles[name] = existing
        else:
            r = Role(id=uuid.uuid4(), name=name, description=f"{name} role")
            db.add(r)
            roles[name] = r
    await db.flush()

    admin = User(
        id=uuid.uuid4(),
        username=f"admin_rag_{uuid.uuid4().hex[:6]}",
        email=f"admin_rag_{uuid.uuid4().hex[:6]}@test.local",
        hashed_password=hash_password("AdminPass123!"),
        role_id=roles["administrator"].id,
        is_active=True,
    )
    emp = User(
        id=uuid.uuid4(),
        username=f"emp_rag_{uuid.uuid4().hex[:6]}",
        email=f"emp_rag_{uuid.uuid4().hex[:6]}@test.local",
        hashed_password=hash_password("EmpPass123!"),
        role_id=roles["general_employee"].id,
        is_active=True,
    )
    db.add(admin)
    db.add(emp)
    await db.commit()

    admin_token = create_access_token(user_id=str(admin.id), role="administrator")
    emp_token = create_access_token(user_id=str(emp.id), role="general_employee")
    return admin_token, emp_token


@pytest.mark.asyncio
async def test_rag_health_check_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    """GET /api/v1/rag/health returns subsystem status, dimensions, and storage paths."""
    res = await client.get("/api/v1/rag/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "embedding_provider" in data
    assert "storage" in data
    assert "catalog" in data
    assert data["embedding_provider"]["dimensions"] == 768


@pytest.mark.asyncio
async def test_rag_upload_and_list_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    """Upload document file via multipart/form-data and verify authorized list."""
    admin_token, emp_token = await _setup_users(db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    file_content = b"# Enterprise Security Policy\nArgon2id and JWT rotation are mandatory standards."
    files = {"file": ("sec_policy.md", io.BytesIO(file_content), "text/markdown")}
    form_data = {
        "title": "Enterprise Security Policy",
        "category": "security",
        "classification": "internal",
        "allowed_roles": '["administrator", "general_employee"]',
    }

    # Upload document
    upload_res = await client.post(
        "/api/v1/rag/upload",
        headers=admin_headers,
        data=form_data,
        files=files,
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["status"] == "success"
    doc_id = data["document_id"]
    assert doc_id

    # List documents as General Employee (should see it because allowed_roles includes general_employee)
    list_res = await client.get("/api/v1/rag/documents", headers=emp_headers)
    assert list_res.status_code == 200
    docs = list_res.json()
    assert any(d["title"] == "Enterprise Security Policy" for d in docs)


@pytest.mark.asyncio
async def test_rag_lab_retrieval_only(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/v1/rag/test/retrieval inspects candidate chunks and RRF scores."""
    admin_token, _ = await _setup_users(db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    payload = {
        "query": "What local LLM stack does ServerGen AI use?",
        "top_k": 3,
        "min_relevance": 0.20,
    }
    res = await client.post(
        "/api/v1/rag/test/retrieval",
        headers=admin_headers,
        json=payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == payload["query"]
    assert "chunks" in data
    assert "citations" in data
    assert data["retrieval_strategy"] == "hybrid_rrf"


@pytest.mark.asyncio
async def test_rag_evaluation_benchmark_suite(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/v1/rag/test/evaluation executes automated benchmark questions."""
    admin_token, _ = await _setup_users(db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.post(
        "/api/v1/rag/test/evaluation",
        headers=admin_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_test_cases"] > 0
    assert "recall_at_4_percentage" in data
    assert "average_latency_ms" in data
    assert len(data["test_cases"]) > 0
