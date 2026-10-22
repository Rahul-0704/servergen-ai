"""
ServerGen AI — Model Provider Abstract Base.

Clean interface so the system is not tightly coupled to Ollama.
Future providers (OpenAI-compatible, vLLM, etc.) implement this ABC.

``generate_structured`` returns Pydantic-VALIDATED output. LLM output is never
trusted as-is: malformed or schema-violating output yields ``(None, failed
response)`` instead of an exception, and the orchestrator treats that as a
verification failure.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, Field, ValidationError

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ModelCapability(StrEnum):
    GENERAL = "general"
    CODING = "coding"
    REASONING = "reasoning"
    DOCUMENT = "document"


class ModelMetadata(BaseModel):
    """
    Metadata describing a registered model.

    RAM/VRAM values are STATIC, documented estimates used for routing/eligibility
    metadata only. The system does NOT monitor GPU/VRAM in real time.
    """

    name: str
    provider: str
    capabilities: list[ModelCapability] = Field(default_factory=list)
    context_length: int = 4096
    minimum_ram_gb: float = 4.0
    recommended_ram_gb: float = 8.0
    minimum_vram_gb: float = 0.0
    recommended_vram_gb: float = 0.0
    requires_gpu: bool = False
    enabled: bool = True
    priority: int = 0  # higher = preferred


class LLMRequest(BaseModel):
    """A structured request to an LLM provider."""

    model: str
    prompt: str
    system_prompt: str = ""
    max_tokens: int = 1024
    temperature: float = 0.1  # low for deterministic structured output
    timeout_seconds: float | None = None  # None → provider default from settings


class LLMResponse(BaseModel):
    """A structured response from an LLM provider."""

    model: str
    provider: str
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    success: bool = True
    error: str = ""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def validate_structured(
    response: LLMResponse, schema: type[SchemaT]
) -> tuple[SchemaT | None, LLMResponse]:
    """Parse + validate a response against ``schema``. Never raises."""
    try:
        raw = _FENCE_RE.sub("", response.content.strip())
        return schema.model_validate(json.loads(raw)), response
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        failed = response.model_copy(
            update={"success": False, "error": "Structured output failed schema validation"}
        )
        return None, failed


class ModelProvider(ABC):
    """
    Abstract base for LLM providers.

    Implementations: OllamaProvider, (future) vLLM provider, etc.
    The orchestrator depends on this interface, not on Ollama directly.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier."""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Send a prompt to the model and return a structured response.

        Must handle: unavailable model, timeout, connection error, malformed response.
        Must NEVER raise unhandled exceptions — return LLMResponse(success=False).
        """

    async def generate_structured(
        self, request: LLMRequest, schema: type[SchemaT]
    ) -> tuple[SchemaT | None, LLMResponse]:
        """
        Generate output that must conform to ``schema`` (Pydantic-validated).

        Default implementation instructs the model via the system prompt and
        validates the result; providers with native constrained decoding override it.
        """
        instruction = (
            "Respond with ONLY a single JSON object matching this JSON Schema, no prose:\n"
            + json.dumps(schema.model_json_schema())
        )
        constrained = request.model_copy(
            update={"system_prompt": f"{request.system_prompt}\n\n{instruction}".strip()}
        )
        response = await self.generate(constrained)
        if not response.success:
            return None, response
        return validate_structured(response, schema)

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider/model server is reachable."""

    @abstractmethod
    async def list_models(self) -> list[str]:
        """List available model names from this provider."""
