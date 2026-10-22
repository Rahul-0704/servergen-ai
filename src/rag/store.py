"""
ServerGen AI — Organizational Knowledge Base Store.

Stores enterprise documents with data sensitivity and role access controls.
Includes pre-seeded canonical organizational records for ServerGen AI.
"""

from __future__ import annotations

import logging
import uuid
from typing import ClassVar

from src.ai.schemas import DataSensitivity
from src.rag.schemas import DocumentCategory, KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger("servergen.rag.store")


class KnowledgeStore:
    """In-memory & persistent knowledge repository with role clearance indexing."""

    _instance: ClassVar[KnowledgeStore | None] = None

    def __init__(self) -> None:
        self._documents: dict[uuid.UUID, KnowledgeDocument] = {}
        self._chunks: list[KnowledgeChunk] = []
        self._seed_default_knowledge()

    @classmethod
    def get_instance(cls) -> KnowledgeStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_document(self, doc: KnowledgeDocument) -> None:
        """Add a document and chunk it for retrieval."""
        self._documents[doc.id] = doc
        self._index_document(doc)
        logger.info("Indexed knowledge document: '%s' [%s]", doc.title, doc.classification.value)

    def _index_document(self, doc: KnowledgeDocument) -> None:
        """Split document into paragraphs/chunks with RBAC headers."""
        paragraphs = [p.strip() for p in doc.content.split("\n\n") if p.strip()]
        for idx, para in enumerate(paragraphs):
            chunk = KnowledgeChunk(
                chunk_id=f"{doc.id}_{idx}",
                doc_id=doc.id,
                doc_title=doc.title,
                content=para,
                category=doc.category,
                classification=doc.classification,
                allowed_roles=doc.allowed_roles,
            )
            self._chunks.append(chunk)

    def list_chunks(self) -> list[KnowledgeChunk]:
        return list(self._chunks)

    def list_documents(self) -> list[KnowledgeDocument]:
        return list(self._documents.values())

    def _seed_default_knowledge(self) -> None:
        """Seed official enterprise knowledge base for ServerGen AI."""
        seeds = [
            KnowledgeDocument(
                title="ServerGen AI System Overview & Core Capabilities",
                category=DocumentCategory.ARCHITECTURE,
                classification=DataSensitivity.INTERNAL,
                allowed_roles=["administrator", "it_operator", "security_analyst", "manager", "general_employee"],
                content="""ServerGen AI is a secure prototype foundation for controlled on-premise enterprise AI automation using local LLM inference, policy-controlled orchestration, RBAC, human approval, and tamper-evident auditing.

The system is organized into modular subsystems: Module 1 covers Secure Access & Audit Management (Argon2id password hashing, JWT authentication, refresh token rotation with family breach detection, and centralized RBAC). Module 2 provides the AI Orchestrator & Local LLM Engine (running local Ollama models like llama3.2:3b on dedicated hardware, risk assessment, human approval interception, and deterministic tool execution).

The primary stack consists of Python 3.11+, FastAPI, SQLAlchemy 2.x async, PostgreSQL with asyncpg, and Ollama for local private inference."""
            ),
            KnowledgeDocument(
                title="Enterprise Role Permissions & Clearance Standards",
                category=DocumentCategory.POLICY,
                classification=DataSensitivity.INTERNAL,
                allowed_roles=["administrator", "it_operator", "security_analyst", "manager", "general_employee"],
                content="""The organization enforces strict Role-Based Access Control (RBAC) across five system roles:
1. Administrator: Full system administration, user provisioning, audit read, and AI execution.
2. IT Operator: Manages system infrastructure, read/execute access on server diagnostic tools, AI execution.
3. Security Analyst: Reviews audit logs, analyzes security postures, assesses threats, but cannot execute mutating server scripts.
4. Department Manager: Reviews operational metrics, has approval.approve permission for high-risk operations, and executes AI tasks.
5. General Employee: Document read and low-risk AI task execution on PUBLIC and INTERNAL data only."""
            ),
            KnowledgeDocument(
                title="IT Operations & Server Diagnostic Runbook",
                category=DocumentCategory.OPERATIONS,
                classification=DataSensitivity.CONFIDENTIAL,
                allowed_roles=["administrator", "it_operator"],
                content="""Server maintenance operations require verification of system health via the /health and /api/v1/health readiness probes.
When server degradation is detected, IT Operators should inspect database connection pools and verify PostgreSQL service status on port 5432.
For local LLM inference, verify that Ollama daemon is active on port 11434 and has the llama3.2:3b model allocated in GPU memory. Mutating operations like service restarts or configuration overwrites are classified as HIGH risk and require Manager approval."""
            ),
            KnowledgeDocument(
                title="Defensive Security & Audit Integrity Verification Playbook",
                category=DocumentCategory.SECURITY,
                classification=DataSensitivity.CONFIDENTIAL,
                allowed_roles=["administrator", "security_analyst"],
                content="""The ServerGen AI audit ledger utilizes a SHA-256 cryptographic hash chain where each event hash is computed over the previous event's hash, sequence number, timestamp, user ID, action, decision, and risk level.
Security Analysts must execute periodic chain integrity verifications via the /api/v1/audit/verify endpoint.
If a sequence gap, altered hash, or mismatched token family is detected, the system flags a breach incident and alerts administrators.
All failed authentication attempts and permission denials are automatically recorded in the ledger."""
            ),
            KnowledgeDocument(
                title="Executive Policy & Q3 Enterprise Financial Audit",
                category=DocumentCategory.EXECUTIVE,
                classification=DataSensitivity.RESTRICTED,
                allowed_roles=["administrator", "manager"],
                content="""RESTRICTED EXECUTIVE RECORD:
The Q3 enterprise automation expenditure totaled $145,000, achieving a 65% reduction in manual server maintenance overhead.
Executive compensation and confidential bonus structures are governed under Policy HR-702 and require dual-manager sign-off before dispersal.
Any automated query requesting this data requires elevated clearance and triggers an automatic Human-in-the-Loop approval request."""
            )
        ]

        for s in seeds:
            self.add_document(s)
