"""
ServerGen AI — Role Vault Physical & Cryptographic Segregation Test Suite.

Verifies:
1. Physical directory isolation: `storage/vaults/{vault_scope}/{doc_id}/...`
2. Database-level role vault filtering and boundary enforcement
3. Vector RAG retriever anti-leakage: employee queries cannot retrieve manager vault chunks
4. DocumentService vault scope permissions (employee cannot upload to manager vault)
5. Executive Manager Suite API (/api/v1/manager/cockpit, /documents, /approvals, /analytics, /ai/query)
6. 403 Forbidden enforcement on non-manager roles attempting manager suite access
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext
from src.core.exceptions import AuthorizationError
from src.core.security import create_access_token, hash_password
from src.models.role import Role
from src.models.user import User
from src.rag.retriever import RoleFilteredRetriever
from src.rag.service import DocumentService
from src.rag.storage import DocumentStorage


async def _create_test_user(db: AsyncSession, role_name: str) -> tuple[str, str, AuthContext]:
    """Helper to create a user and token for testing."""
    res = await db.execute(select(Role).where(Role.name == role_name))
    role_entity = res.scalar_one_or_none()
    if not role_entity:
        role_entity = Role(
            id=uuid.uuid4(),
            name=role_name,
            description=f"Test {role_name} role",
            permissions=[],
        )
        db.add(role_entity)
        await db.flush()

    user = User(
        id=uuid.uuid4(),
        username=f"{role_name}_{uuid.uuid4().hex[:6]}",
        email=f"{role_name}_{uuid.uuid4().hex[:6]}@enterprise.local",
        hashed_password=hash_password("Pass12345!Secure"),
        role_id=role_entity.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()

    token = create_access_token(user_id=str(user.id), role=role_name)
    auth = AuthContext(
        user_id=str(user.id),
        username=user.username,
        role=role_name,
        permissions={PermissionCode.DOCUMENT_READ, PermissionCode.DOCUMENT_WRITE, PermissionCode.APPROVAL_APPROVE}
        if role_name in ("manager", "administrator")
        else {PermissionCode.DOCUMENT_READ},
    )
    return token, str(user.id), auth


def test_physical_vault_storage_paths(tmp_path):
    """Verify durable physical storage writes to storage/vaults/{vault_scope}/."""
    storage = DocumentStorage(base_dir=tmp_path)
    doc_id = uuid.uuid4()

    # 1. Save in manager vault
    info_mgr = storage.save_file(
        document_id=doc_id,
        version_number=1,
        filename="executive_budget.xlsx",
        content=b"sample-manager-vault-data",
        vault_scope="manager",
    )
    assert "vaults" in info_mgr.relative_path
    assert "manager" in info_mgr.relative_path
    full_path_mgr = tmp_path / info_mgr.relative_path
    assert full_path_mgr.exists()
    assert full_path_mgr.read_bytes() == b"sample-manager-vault-data"

    # 2. Save in company-wide 'all' vault
    doc_id_all = uuid.uuid4()
    info_all = storage.save_file(
        document_id=doc_id_all,
        version_number=1,
        filename="employee_handbook.pdf",
        content=b"%PDF-1.4 sample-all-vault-data",
        vault_scope="all",
    )
    assert "vaults" in info_all.relative_path
    assert "all" in info_all.relative_path
    full_path_all = tmp_path / info_all.relative_path
    assert full_path_all.exists()
    assert full_path_all.read_bytes() == b"%PDF-1.4 sample-all-vault-data"

    # 3. Safe deletion purges vault
    storage.delete_document_tree(doc_id, vault_scope="manager")
    assert not full_path_mgr.exists()


@pytest.mark.asyncio
async def test_role_vault_document_service_isolation(db_session: AsyncSession, tmp_path):
    """Verify DocumentService enforces strict role-vault isolation across roles."""
    storage = DocumentStorage(base_dir=tmp_path)
    service = DocumentService(db_session, storage=storage)

    _mgr_token, _mgr_id, mgr_auth = await _create_test_user(db_session, "manager")
    _emp_token, _emp_id, emp_auth = await _create_test_user(db_session, "general_employee")
    _admin_token, _admin_id, admin_auth = await _create_test_user(db_session, "administrator")

    # 1. Manager creates a restricted document in the Manager Vault
    mgr_doc, _, _ = await service.create_document_with_file(
        auth=mgr_auth,
        filename="q3_confidential_payroll.txt",
        content=b"Confidential Executive Salaries and Compensation Table",
        title="Q3 Executive Payroll",
        classification="restricted",
        vault_scope="manager",
        auto_index=False,
    )
    assert mgr_doc.vault_scope == "manager"

    # 2. Manager creates a company-wide document in 'all' vault
    all_doc, _, _ = await service.create_document_with_file(
        auth=mgr_auth,
        filename="company_travel_policy.txt",
        content=b"All employees may expense up to $50 for business meals.",
        title="Company Travel Policy",
        classification="internal",
        vault_scope="all",
        auto_index=False,
    )
    assert all_doc.vault_scope == "all"

    # 3. Employee Access Checks:
    # Employee can access 'all' doc
    assert service.check_user_can_access_doc(all_doc, emp_auth) is True
    # Employee CANNOT access 'manager' vault doc
    assert service.check_user_can_access_doc(mgr_doc, emp_auth) is False

    # 4. Employee listing documents only returns 'all' doc, never 'manager' doc
    emp_docs = await service.list_documents(auth=emp_auth)
    emp_doc_ids = [d.id for d in emp_docs]
    assert all_doc.id in emp_doc_ids
    assert mgr_doc.id not in emp_doc_ids

    # 5. Employee attempting to read manager doc directly raises AuthorizationError
    with pytest.raises(AuthorizationError):
        await service.get_document(mgr_doc.id, emp_auth)

    # 6. Employee attempting to upload into 'manager' vault raises AuthorizationError
    with pytest.raises(AuthorizationError):
        await service.create_document_with_file(
            auth=emp_auth,
            filename="unauthorized_file.txt",
            content=b"Attempt to bypass vault",
            vault_scope="manager",
        )

    # 7. Manager can access both 'manager' doc and 'all' doc
    assert service.check_user_can_access_doc(mgr_doc, mgr_auth) is True
    assert service.check_user_can_access_doc(all_doc, mgr_auth) is True
    mgr_docs = await service.list_documents(auth=mgr_auth)
    mgr_doc_ids = [d.id for d in mgr_docs]
    assert mgr_doc.id in mgr_doc_ids
    assert all_doc.id in mgr_doc_ids

    # 8. Admin can access all vaults
    admin_docs = await service.list_documents(auth=admin_auth)
    admin_doc_ids = [d.id for d in admin_docs]
    assert mgr_doc.id in admin_doc_ids
    assert all_doc.id in admin_doc_ids


@pytest.mark.asyncio
async def test_role_vault_retriever_vector_isolation(db_session: AsyncSession):
    """Verify RoleFilteredRetriever blocks confidential manager chunks when queried by an employee."""
    retriever = RoleFilteredRetriever()

    _emp_token, _emp_id, emp_auth = await _create_test_user(db_session, "general_employee")
    _mgr_token, _mgr_id, mgr_auth = await _create_test_user(db_session, "manager")

    # Employee searches for manager confidential financial audit (TC-05 in seed store)
    emp_res = await retriever.retrieve(
        query="What was the Q3 expenditure for enterprise automation under Policy HR-702?",
        auth=emp_auth,
        top_k=4,
    )
    # Employee cannot retrieve manager vault documents
    assert emp_res.denied_chunks_count > 0
    retrieved_titles = [c.doc_title for c in emp_res.chunks]
    assert "Executive Policy & Q3 Enterprise Financial Audit" not in retrieved_titles

    # Manager searches for the exact same query
    mgr_res = await retriever.retrieve(
        query="What was the Q3 expenditure for enterprise automation under Policy HR-702?",
        auth=mgr_auth,
        top_k=4,
    )
    # Manager CAN retrieve manager vault document
    mgr_titles = [c.doc_title for c in mgr_res.chunks]
    assert "Executive Policy & Q3 Enterprise Financial Audit" in mgr_titles
    assert any(c.vault_scope == "manager" for c in mgr_res.chunks)


@pytest.mark.asyncio
async def test_manager_cockpit_api(client: AsyncClient, db_session: AsyncSession):
    """Verify GET /api/v1/manager/cockpit works for managers and denies employees with 403."""
    mgr_token, _, _ = await _create_test_user(db_session, "manager")
    emp_token, _, _ = await _create_test_user(db_session, "general_employee")

    # 1. Non-manager receives 403 Forbidden
    res_emp = await client.get(
        "/api/v1/manager/cockpit",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_emp.status_code == 403

    # 2. Manager receives 200 with cockpit KPIs
    res_mgr = await client.get(
        "/api/v1/manager/cockpit",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_mgr.status_code == 200
    data = res_mgr.json()
    assert data["status"] == "ready"
    assert "kpis" in data
    assert len(data["kpis"]) == 4
    assert data["system_health"]["zero_cloud_data_sovereignty"] is True


@pytest.mark.asyncio
async def test_manager_dual_vault_document_upload_and_listing(
    client: AsyncClient, db_session: AsyncSession
):
    """Verify manager can upload directly into Manager Vault and filter documents."""
    mgr_token, _, _ = await _create_test_user(db_session, "manager")
    headers = {"Authorization": f"Bearer {mgr_token}"}

    # 1. Upload to Manager Confidential Vault
    files = {
        "file": ("q4_strategy.txt", io.BytesIO(b"Strictly confidential executive strategy 2027"), "text/plain")
    }
    data = {
        "title": "Q4 Executive Strategy",
        "target_vault": "manager",
        "classification": "restricted",
    }
    res_up = await client.post("/api/v1/manager/documents/upload", data=data, files=files, headers=headers)
    assert res_up.status_code == 200
    doc_info = res_up.json()
    assert doc_info["status"] == "success"
    assert doc_info["vault_scope"] == "manager"

    # 2. Upload to Company-Wide Library
    files_all = {
        "file": ("holiday_calendar.txt", io.BytesIO(b"Company official holidays for 2027"), "text/plain")
    }
    data_all = {
        "title": "2027 Company Holidays",
        "target_vault": "all",
        "classification": "internal",
    }
    res_all = await client.post("/api/v1/manager/documents/upload", data=data_all, files=files_all, headers=headers)
    assert res_all.status_code == 200
    assert res_all.json()["vault_scope"] == "all"

    # 3. Filter by manager vault
    res_list_mgr = await client.get("/api/v1/manager/documents?vault=manager", headers=headers)
    assert res_list_mgr.status_code == 200
    mgr_items = res_list_mgr.json()
    assert all(item["vault_scope"] == "manager" for item in mgr_items)
    assert any(item["title"] == "Q4 Executive Strategy" for item in mgr_items)

    # 4. Filter by company vault
    res_list_all = await client.get("/api/v1/manager/documents?vault=all", headers=headers)
    assert res_list_all.status_code == 200
    all_items = res_list_all.json()
    assert all(item["vault_scope"] == "all" for item in all_items)
    assert any(item["title"] == "2027 Company Holidays" for item in all_items)


@pytest.mark.asyncio
async def test_manager_analytics_and_ai_query(client: AsyncClient, db_session: AsyncSession):
    """Verify 1-Click Executive Analytics and Grounded Executive AI Query."""
    mgr_token, _, _ = await _create_test_user(db_session, "manager")
    headers = {"Authorization": f"Bearer {mgr_token}"}

    # 1. Test 1-Click Analytics (Spreadsheet -> Board Deliverables)
    wb = Workbook()
    ws = wb.active
    ws.title = "Executive_Budget"
    ws.append(["Department", "Allocated", "Spent"])
    ws.append(["Engineering", 100000.0, 115000.0])
    ws.append(["Marketing", 50000.0, 48000.0])
    ws.append(["Security", 60000.0, 240000.0])  # outlier
    ws.append(["Sales", 80000.0, 79000.0])
    ws.append(["Legal", 40000.0, 39000.0])
    ws.append(["Ops", 70000.0, 71000.0])
    buf = io.BytesIO()
    wb.save(buf)

    files = {
        "file": ("exec_budget.xlsx", io.BytesIO(buf.getvalue()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    res_an = await client.post(
        "/api/v1/manager/analytics/run",
        data={"goal_prompt": "Detect cost outliers and budget variances for board meeting"},
        files=files,
        headers=headers,
    )
    assert res_an.status_code == 200
    an_data = res_an.json()
    assert an_data["status"] == "success"
    assert "deliverables" in an_data
    assert "pptx" in an_data["deliverables"]
    assert "pdf" in an_data["deliverables"]
    assert "xlsx" in an_data["deliverables"]
    assert len(an_data["kpi_metrics"]) >= 1

    # 2. Test Grounded Executive AI Query
    ai_payload = {
        "query": "What is the policy regarding Q3 expenditures and automation?",
        "target_vault": "both",
        "top_k": 3,
    }
    res_ai = await client.post("/api/v1/manager/ai/query", json=ai_payload, headers=headers)
    assert res_ai.status_code == 200
    ai_data = res_ai.json()
    assert "answer" in ai_data
    assert "citations" in ai_data
    assert ai_data["is_grounded"] is True
