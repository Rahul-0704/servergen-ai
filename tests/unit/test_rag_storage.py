"""
Unit Tests — Document Storage & Security Controls.

Verifies:
1. Filename sanitization and path traversal prevention.
2. Atomic persistence to storage directory.
3. SHA-256 checksum computation.
4. Maximum file size enforcement.
5. Header signature validation.
6. Safe deletion of files and document directories.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
from src.core.exceptions import ValidationError
from src.rag.storage import DocumentStorage


def test_sanitize_filename() -> None:
    """Dangerous path traversal characters are stripped."""
    assert DocumentStorage.sanitize_filename("../../../etc/passwd") == "passwd"
    assert DocumentStorage.sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
    assert DocumentStorage.sanitize_filename("valid_document.pdf") == "valid_document.pdf"
    assert DocumentStorage.sanitize_filename("doc with spaces (1).docx") == "doc_with_spaces__1_.docx"


def test_file_size_limit_enforced() -> None:
    """Files exceeding size limit raise ValidationError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir, max_size_bytes=1024)  # 1 KB limit
        large_content = b"A" * 2048

        with pytest.raises(ValidationError, match="exceeds maximum permitted limit"):
            storage.validate_upload("large.txt", large_content)


def test_empty_file_rejected() -> None:
    """Empty files (0 bytes) raise ValidationError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir)
        with pytest.raises(ValidationError, match="empty"):
            storage.validate_upload("empty.txt", b"")


def test_unsupported_format_rejected() -> None:
    """Unsupported extensions are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir)
        with pytest.raises(ValidationError, match="Unsupported file format"):
            storage.validate_upload("malicious.exe", b"MZ\x90\x00")


def test_invalid_header_signature_rejected() -> None:
    """Files with mismatched extensions and binary magic headers are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir)
        # Pretend to be a PDF without %PDF- magic signature
        with pytest.raises(ValidationError, match="Corrupt or invalid header signature"):
            storage.validate_upload("fake.pdf", b"This is not a real PDF header")


def test_atomic_file_persistence() -> None:
    """Files are durably and atomically written with verified SHA-256 checksums."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir)
        doc_id = uuid.uuid4()
        content = b"ServerGen AI Enterprise Architecture Specification\nVersion 1.0"

        info = storage.save_file(
            document_id=doc_id,
            version_number=1,
            filename="architecture.txt",
            content=content,
        )

        assert info.file_size == len(content)
        assert len(info.checksum_sha256) == 64
        assert Path(info.absolute_path).exists()
        assert storage.read_file(info.relative_path) == content

        # Verify deletion
        assert storage.delete_file(info.relative_path) is True
        assert not Path(info.absolute_path).exists()
        assert storage.delete_document_tree(doc_id) is True
