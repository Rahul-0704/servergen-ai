"""
ServerGen AI — Model Registry and Capability-Aware Model Router.

ModelRegistry: stores registered models and their metadata.
ModelRouter: deterministic routing based on task capability requirements.

Initial routing:
  general task  → gemma3:4b (Ollama)
  coding task   → gemma3:4b (fallback until a coding model is registered)
  document task → gemma3:4b (fallback)

Do NOT implement fake real-time GPU/VRAM management.
Routing is deterministic based on capability metadata.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.ai.providers.base import ModelCapability, ModelMetadata, ModelProvider
from src.ai.providers.ollama_provider import OllamaProvider
from src.ai.schemas import TaskCategory
from src.core.config import get_settings
from src.core.exceptions import ModelNotAvailableError

logger = logging.getLogger("servergen.model_router")


class ModelRegistry:
    """Registry of available models and their providers."""

    def __init__(self) -> None:
        self._models: dict[str, ModelMetadata] = {}
        self._providers: dict[str, ModelProvider] = {}

    def register_provider(self, provider: ModelProvider) -> None:
        self._providers[provider.provider_name] = provider

    def register_model(self, metadata: ModelMetadata) -> None:
        self._models[metadata.name] = metadata

    def get_model(self, name: str) -> ModelMetadata | None:
        return self._models.get(name)

    def get_provider(self, provider_name: str) -> ModelProvider | None:
        return self._providers.get(provider_name)

    def list_models(self) -> list[ModelMetadata]:
        return [m for m in self._models.values() if m.enabled]


class ModelRouter:
    """
    Deterministic capability-aware model router.

    Selects the best available model for a given task category.
    Falls back to the default model if no capability-specific model is found.
    """

    # Maps task categories to required capabilities
    _CAPABILITY_MAP: ClassVar[dict[TaskCategory, ModelCapability]] = {
        TaskCategory.CODING: ModelCapability.CODING,
        TaskCategory.DOCUMENT: ModelCapability.DOCUMENT,
        TaskCategory.SECURITY: ModelCapability.REASONING,
        TaskCategory.REPORTING: ModelCapability.REASONING,
        TaskCategory.OPERATIONS: ModelCapability.GENERAL,
        TaskCategory.GENERAL: ModelCapability.GENERAL,
    }

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def select_model(self, task_category: TaskCategory) -> ModelMetadata:
        """
        Select the best model for the given task category.

        Priority: capability match > priority score > default model.
        Raises ModelNotAvailableError if no enabled model is found.
        """
        required_capability = self._CAPABILITY_MAP.get(task_category, ModelCapability.GENERAL)
        enabled = self.registry.list_models()

        if not enabled:
            raise ModelNotAvailableError("No models registered")

        # Filter by capability, fall back to GENERAL if none match
        capable = [m for m in enabled if required_capability in m.capabilities]
        if not capable:
            capable = [m for m in enabled if ModelCapability.GENERAL in m.capabilities]
        if not capable:
            capable = enabled  # last resort: any enabled model

        # Sort by priority descending, pick highest
        capable.sort(key=lambda m: m.priority, reverse=True)
        selected = capable[0]

        logger.info(
            "Model selected: %s (provider=%s) for task=%s",
            selected.name,
            selected.provider,
            task_category,
        )
        return selected

    def get_provider_for_model(self, model: ModelMetadata) -> ModelProvider:
        """Get the provider instance for a model."""
        provider = self.registry.get_provider(model.provider)
        if provider is None:
            raise ModelNotAvailableError(f"Provider '{model.provider}' not registered")
        return provider


def build_default_registry() -> ModelRegistry:
    """Build the default registry with Ollama + gemma3:4b."""
    settings = get_settings()
    registry = ModelRegistry()

    # Register Ollama provider
    registry.register_provider(OllamaProvider())

    # Register default model
    registered_names = {settings.DEFAULT_MODEL}
    registry.register_model(
        ModelMetadata(
            name=settings.DEFAULT_MODEL,
            provider="ollama",
            capabilities=[
                ModelCapability.GENERAL,
                ModelCapability.DOCUMENT,
                ModelCapability.REASONING,
                ModelCapability.CODING,
            ],
            context_length=8192,
            minimum_ram_gb=4.0,
            recommended_ram_gb=8.0,
            minimum_vram_gb=2.0,
            recommended_vram_gb=4.0,
            requires_gpu=False,
            enabled=True,
            priority=10,
        )
    )

    # Also register secondary standard models if distinct
    for alt_model in ("llama3.2:3b", "gemma3:4b"):
        if alt_model not in registered_names:
            registered_names.add(alt_model)
            registry.register_model(
                ModelMetadata(
                    name=alt_model,
                    provider="ollama",
                    capabilities=[
                        ModelCapability.GENERAL,
                        ModelCapability.DOCUMENT,
                        ModelCapability.REASONING,
                        ModelCapability.CODING,
                    ],
                    context_length=8192,
                    minimum_ram_gb=4.0,
                    recommended_ram_gb=8.0,
                    minimum_vram_gb=2.0,
                    recommended_vram_gb=4.0,
                    requires_gpu=False,
                    enabled=True,
                    priority=5,
                )
            )

    return registry
