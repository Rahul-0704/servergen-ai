"""
ServerGen AI — FastAPI Application Factory.

Creates and configures the FastAPI application with middleware,
exception handlers, and API routes.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import get_settings
from src.core.database import check_database, dispose_engine
from src.core.middleware import (
    RequestIDMiddleware,
    StructuredLoggingMiddleware,
    register_exception_handlers,
)

logger = logging.getLogger("servergen")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    logger.info("Application starting up")
    yield
    logger.info("Application shutting down — disposing database engine")
    await dispose_engine()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns a fully configured app with middleware, exception handlers,
    and all API routes mounted.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Secure prototype foundation for controlled on-premise enterprise AI automation "
            "using local LLM inference, policy-controlled orchestration, RBAC, "
            "human approval, and tamper-evident auditing."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── CORS Middleware ──────────────────────────────────────────────
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ── Custom Middleware (order matters: outermost first) ────────────
    app.add_middleware(StructuredLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # ── Exception handlers ───────────────────────────────────────────
    register_exception_handlers(app)

    # ── API Routers ──────────────────────────────────────────────────
    from src.api.v1.approvals import router as approvals_router
    from src.api.v1.audit import router as audit_router
    from src.api.v1.auth import router as auth_router
    from src.api.v1.orchestrator import (
        orchestrator_alias_router,
        router as orchestrator_router,
    )
    from src.api.v1.rag import router as rag_router
    from src.api.v1.users import router as users_router

    app.include_router(auth_router)
    app.include_router(approvals_router)
    app.include_router(audit_router)
    app.include_router(orchestrator_router)
    app.include_router(orchestrator_alias_router)
    app.include_router(rag_router)
    app.include_router(users_router)

    # ── Static files for test interface ──────────────────────────────
    test_interface_path = Path(__file__).parent.parent / "test-interface.html"
    if test_interface_path.exists():

        @app.get("/test", tags=["system"])
        async def test_interface():
            return FileResponse(test_interface_path)

    # ── Serve frontend dist if present ───────────────────────────────
    frontend_path = Path(settings.FRONTEND_DIST_DIR)
    if frontend_path.is_dir():
        app.mount("/static", StaticFiles(directory=str(frontend_path)), name="frontend")

    # ── Logging ──────────────────────────────────────────────────────
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Health check ─────────────────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        """Basic health check endpoint. Returns application status."""
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "environment": settings.APP_ENV,
        }

    @app.get("/api/v1/health", tags=["system"])
    async def api_health_check() -> dict:
        """API-versioned health check with database readiness probe and local LLM runtime status."""
        import httpx

        db_ok = await check_database()

        ollama_status = "unavailable"
        ollama_models: list[str] = []
        try:
            async with httpx.AsyncClient(base_url=settings.OLLAMA_BASE_URL, timeout=3.0) as client:
                res = await client.get("/api/tags")
                if res.status_code == 200:
                    ollama_status = "connected"
                    data = res.json()
                    ollama_models = [
                        m.get("name")
                        for m in data.get("models", [])
                        if isinstance(m, dict) and m.get("name")
                    ]
        except Exception:
            ollama_status = "unavailable"

        return {
            "status": "healthy" if db_ok else "degraded",
            "service": settings.APP_NAME,
            "version": "0.1.0",
            "database": "connected" if db_ok else "unavailable",
            "ollama": {
                "status": ollama_status,
                "url": settings.OLLAMA_BASE_URL,
                "default_model": settings.DEFAULT_MODEL,
                "available_models": ollama_models,
            },
        }

    logger.info(
        "Application started",
        extra={"app_name": settings.APP_NAME, "environment": settings.APP_ENV},
    )

    return app


# Application instance for uvicorn
app = create_app()
