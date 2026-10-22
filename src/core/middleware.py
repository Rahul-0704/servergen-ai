"""
ServerGen AI — Middleware.

Request ID injection, structured logging, and secure error handling.
Never logs tokens, passwords, or internal stack traces to clients.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import ClassVar

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.exceptions import (
    AccountLockedError,
    ApprovalRequiredError,
    AuditIntegrityError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ModelNotAvailableError,
    ModelProviderError,
    NotFoundError,
    PolicyDeniedError,
    RateLimitExceededError,
    ServerGenError,
    ToolExecutionError,
    ToolNotFoundError,
    ValidationError,
)

logger = logging.getLogger("servergen")

# Context variable for request-scoped correlation ID
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a unique request ID to every incoming request for tracing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = str(uuid.uuid4())
        request_id_ctx.set(rid)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Logs request/response metadata. Never logs tokens or passwords."""

    # Paths that should not be logged in detail (health checks, etc.)
    _skip_paths: ClassVar[set[str]] = {"/health", "/api/v1/health"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self._skip_paths:
            return await call_next(request)

        rid = getattr(request.state, "request_id", "unknown")
        start_time = time.monotonic()

        logger.info(
            "request_started",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        response = await call_next(request)
        duration_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "request_completed",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        return response


# ── Exception → HTTP status mapping ─────────────────────────────────────

_EXCEPTION_STATUS_MAP: dict[type[ServerGenError], int] = {
    AuthenticationError: 401,
    AccountLockedError: 423,
    AuthorizationError: 403,
    PolicyDeniedError: 403,
    ApprovalRequiredError: 202,
    RateLimitExceededError: 429,
    ModelNotAvailableError: 503,
    ModelProviderError: 502,
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 400,
    ToolNotFoundError: 404,
    ToolExecutionError: 500,
    AuditIntegrityError: 500,
}


def _get_status_code(exc: ServerGenError) -> int:
    """Resolve HTTP status code for an exception using MRO-based lookup."""
    for exc_type in type(exc).__mro__:
        if exc_type in _EXCEPTION_STATUS_MAP:
            return _EXCEPTION_STATUS_MAP[exc_type]
    return 500


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers that never expose internal details."""

    @app.exception_handler(ServerGenError)
    async def servergen_error_handler(request: Request, exc: ServerGenError) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        status_code = _get_status_code(exc)

        logger.warning(
            "handled_error",
            extra={
                "request_id": rid,
                "error_code": exc.code,
                "error_message": exc.message,
                "status_code": status_code,
            },
        )

        body: dict[str, object] = {
            "error": exc.code,
            "message": exc.message,
            "request_id": rid,
        }

        # Include approval_request_id for approval-required responses
        if isinstance(exc, ApprovalRequiredError) and exc.approval_request_id:
            body["approval_request_id"] = exc.approval_request_id

        # Include retry_after for rate limiting
        if isinstance(exc, RateLimitExceededError) and exc.retry_after_seconds > 0:
            body["retry_after_seconds"] = exc.retry_after_seconds

        return JSONResponse(status_code=status_code, content=body)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")

        # Log full details server-side but NEVER expose to client
        logger.error(
            "unhandled_error",
            extra={"request_id": rid, "error_type": type(exc).__name__},
            exc_info=True,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An internal error occurred",
                "request_id": rid,
            },
        )
