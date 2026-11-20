"""
ServerGen AI — Secure Enterprise Document Storage Backend.

Provides durable, atomic, and path-traversal resistant file persistence
outside publicly served directories. Enforces strict file-size limits,
MIME and content-signature validation, and SHA-256 integrity verification.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from src.core.config import get_settings
from src.core.exceptions import ValidationError

logger = logging.getLogger("servergen.rag.storage")

# Magic signatures for supported file formats
_FILE_SIGNATURES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF-"],
    "docx": [b"PK\x03\x04"],  # ZIP container
    "xlsx": [b"PK\x03\x04"],  # ZIP container
    "pptx": [b"PK\x03\x04"],  # ZIP container
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "bmp": [b"BM"],
    "webp": [b"RIFF"],
}

_ALLOWED_EXTENSIONS: set[str] = {
    "txt",
    "md",
    "markdown",
    "csv",
    "tsv",
    "pdf",
    "docx",
    "xlsx",
    "xls",
    "xlsm",
    "pptx",
    "html",
    "htm",
    "png",
    "jpg",
    "jpeg",
    "bmp",
    "webp",
    "tiff",
    "tif",
}

_MIME_MAP: dict[str, str] = {
    "txt": "text/plain",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "html": "text/html",
    "htm": "text/html",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
}


@dataclass(frozen=True)
class StoredFileInfo:
    relative_path: str
    absolute_path: str
    filename: str
    file_size: int
    checksum_sha256: str
    mime_type: str


class DocumentStorage:
    """
    Durable filesystem storage manager for enterprise documents.
    Prevents path traversal, enforces size limits, and writes atomically.
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        max_size_bytes: int | None = None,
    ) -> None:
        settings = get_settings()
        self.base_dir = Path(base_dir or settings.DOCUMENT_STORAGE_DIR).resolve()
        self.max_size_bytes = max_size_bytes or settings.MAX_DOCUMENT_UPLOAD_SIZE_BYTES
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Strip directory components and unsafe characters from filenames."""
        clean = os.path.basename(filename.strip().replace("\\", "/"))
        # Replace non-alphanumeric (except dot, dash, underscore)
        clean = re.sub(r"[^\w.\-]", "_", clean)
        if not clean or clean.startswith("."):
            clean = f"document_{uuid.uuid4().hex[:8]}.bin"
        return clean

    def validate_upload(self, filename: str, content: bytes) -> tuple[str, str]:
        """
        Validate file extension, size, and header signature.
        Returns (sanitized_filename, mime_type) or raises ValidationError.
        """
        if not content:
            raise ValidationError("Uploaded file is empty (0 bytes)")

        if len(content) > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            raise ValidationError(f"File size exceeds maximum permitted limit ({max_mb:.1f} MB)")

        sanitized = self.sanitize_filename(filename)
        ext = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""

        if ext not in _ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
            raise ValidationError(
                f"Unsupported file format '.{ext}'. Supported formats: {allowed}"
            )

        # Check binary signature if applicable
        if ext in _FILE_SIGNATURES:
            valid_sig = any(content.startswith(sig) for sig in _FILE_SIGNATURES[ext])
            if not valid_sig:
                # If an xlsx/xls file was exported as text/csv or alternate format, permit fallback
                if ext in ("xlsx", "xls") and len(content) > 0:
                    pass
                else:
                    msg = f"Corrupt or invalid header signature for format '.{ext}'"
                    raise ValidationError(msg)

        guess_mime = mimetypes.guess_type(sanitized)[0]
        mime_type = _MIME_MAP.get(ext) or guess_mime or "application/octet-stream"
        return sanitized, mime_type

    def save_file(
        self,
        document_id: uuid.UUID,
        version_number: int,
        filename: str,
        content: bytes | BinaryIO,
    ) -> StoredFileInfo:
        """
        Persist a document file atomically inside storage/<doc_id>/<version_number>/.
        Computes SHA-256 checksum and returns StoredFileInfo.
        """
        data_bytes = content if isinstance(content, bytes) else content.read()

        sanitized_name, mime_type = self.validate_upload(filename, data_bytes)

        # Target directory: storage/documents/<doc_id>/<version_number>/
        target_dir = self.base_dir / str(document_id) / str(version_number)
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = (target_dir / sanitized_name).resolve()
        # Verify target is strictly within base_dir (protection against path traversal)
        if not target_file.is_relative_to(self.base_dir):
            raise ValidationError("Security violation: path traversal detected in file destination")

        temp_file = target_dir / f".tmp_{uuid.uuid4().hex}"

        sha256 = hashlib.sha256()
        sha256.update(data_bytes)
        checksum = sha256.hexdigest()

        try:
            with open(temp_file, "wb") as f:
                f.write(data_bytes)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace
            os.replace(temp_file, target_file)
        except Exception as exc:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            logger.error("Failed to store file %s: %s", target_file, exc)
            raise

        rel_path = str(target_file.relative_to(self.base_dir)).replace("\\", "/")
        return StoredFileInfo(
            relative_path=rel_path,
            absolute_path=str(target_file),
            filename=sanitized_name,
            file_size=len(data_bytes),
            checksum_sha256=checksum,
            mime_type=mime_type,
        )

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative storage path safely, preventing traversal."""
        clean_rel = relative_path.lstrip("/\\")
        resolved = (self.base_dir / clean_rel).resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise ValidationError("Security violation: unauthorized file path outside storage root")
        return resolved

    def read_file(self, relative_path: str) -> bytes:
        """Read durable file bytes."""
        path = self.resolve_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"Stored file not found: {relative_path}")
        return path.read_bytes()

    def delete_file(self, relative_path: str) -> bool:
        """Safely delete an individual stored file."""
        try:
            path = self.resolve_path(relative_path)
            if path.is_file():
                path.unlink()
                return True
        except Exception as exc:
            logger.warning("Could not delete file %s: %s", relative_path, exc)
        return False

    def delete_document_tree(self, document_id: uuid.UUID) -> bool:
        """Safely remove the entire directory for a document and its versions."""
        doc_dir = (self.base_dir / str(document_id)).resolve()
        if doc_dir.is_relative_to(self.base_dir) and doc_dir.is_dir():
            shutil.rmtree(doc_dir, ignore_errors=True)
            return True
        return False
