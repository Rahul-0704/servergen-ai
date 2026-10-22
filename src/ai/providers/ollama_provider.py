"""
ServerGen AI — Ollama Model Provider.

Integrates with Ollama for local LLM inference over HTTP (httpx).
Handles: unavailable server, model not found, timeout, malformed response.
Never crashes the API — returns controlled LLMResponse(success=False).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from src.ai.providers.base import (
    LLMRequest,
    LLMResponse,
    ModelProvider,
    SchemaT,
    validate_structured,
)
from src.core.config import get_settings

logger = logging.getLogger("servergen.ollama")


class OllamaProvider(ModelProvider):
    """
    Ollama local LLM provider.

    All errors are caught and returned as LLMResponse(success=False, error=...)
    — never propagated as exceptions. Error strings are generic on purpose so
    internals (hosts, stack traces) never reach API clients.
    """

    @property
    def provider_name(self) -> str:
        return "ollama"

    @staticmethod
    def _base_url() -> str:
        return get_settings().OLLAMA_BASE_URL

    def _failure(self, request: LLMRequest, error: str) -> LLMResponse:
        return LLMResponse(
            model=request.model,
            provider=self.provider_name,
            content="",
            success=False,
            error=error,
        )

    async def _call(
        self, request: LLMRequest, response_format: dict[str, Any] | None = None
    ) -> LLMResponse:
        """POST to /api/generate, optionally constraining output to a JSON schema."""
        start = time.monotonic()
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "system": request.system_prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "num_gpu": 99,  # Force complete layer offloading to NVIDIA GPU via CUDA
            },
        }
        if response_format is not None:
            payload["format"] = response_format

        timeout = request.timeout_seconds or get_settings().OLLAMA_TIMEOUT_SECONDS
        try:
            async with httpx.AsyncClient(base_url=self._base_url(), timeout=timeout) as client:
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            logger.warning("Ollama unavailable: %s", exc)
            return self._failure(request, "Ollama server is not available")
        except httpx.TimeoutException:
            logger.warning("Ollama request timed out for model %s", request.model)
            return self._failure(request, "Request timed out")
        except httpx.HTTPStatusError as exc:
            error_detail = ""
            try:
                err_data = exc.response.json()
                error_detail = err_data.get("error", "")
            except Exception:
                error_detail = exc.response.text

            # Gracefully handle model not found/pulled by falling back to DEFAULT_MODEL
            default_model = get_settings().DEFAULT_MODEL
            if exc.response.status_code == 404 and request.model != default_model:
                logger.warning(
                    "Model '%s' not found in Ollama (%s). Gracefully falling back to default model '%s'.",
                    request.model,
                    error_detail or "not found",
                    default_model,
                )
                fallback_req = LLMRequest(
                    model=default_model,
                    prompt=request.prompt,
                    system_prompt=request.system_prompt,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    timeout_seconds=request.timeout_seconds,
                )
                fallback_resp = await self._call(fallback_req, response_format=response_format)
                if fallback_resp.success:
                    return fallback_resp

            logger.warning("Ollama HTTP error %s: %s", exc.response.status_code, error_detail or exc)
            err_msg = error_detail or f"HTTP {exc.response.status_code}"
            if "not found" in err_msg.lower():
                err_msg = (
                    f"Model '{request.model}' is not pulled in local Ollama runtime. "
                    f"Run 'ollama pull {request.model}' in terminal or switch to an installed model (e.g. {default_model})."
                )
            return self._failure(request, err_msg)
        except Exception as exc:
            logger.error("Unexpected Ollama error: %s", exc)
            return self._failure(request, "Unexpected provider error")

        content = data.get("response", "") if isinstance(data, dict) else None
        if not isinstance(content, str):
            return self._failure(request, "Malformed response from provider")

        return LLMResponse(
            model=request.model,
            provider=self.provider_name,
            content=content,
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(data.get("eval_count", 0) or 0),
            latency_ms=(time.monotonic() - start) * 1000,
            success=True,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a free-text generation request to Ollama."""
        return await self._call(request)

    async def generate_structured(
        self, request: LLMRequest, schema: type[SchemaT]
    ) -> tuple[SchemaT | None, LLMResponse]:
        """Use Ollama's native JSON-schema constrained decoding, then validate with Pydantic."""
        response = await self._call(request, response_format=schema.model_json_schema())
        if not response.success:
            return None, response
        return validate_structured(response, schema)

    async def is_available(self) -> bool:
        """Check if the Ollama server is reachable."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url(), timeout=5.0) as client:
                resp = await client.get("/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List models available in Ollama."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url(), timeout=5.0) as client:
                resp = await client.get("/api/tags")
                resp.raise_for_status()
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []
