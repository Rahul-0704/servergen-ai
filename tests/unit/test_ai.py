"""
Phase H/I Tests — AI Provider, Model Routing, Task Classifier, Tools, Verifier.

Tests:
 1. Ollama unavailable → controlled LLMResponse(success=False)
 2. Malformed Ollama response → controlled failure
 3. ModelRegistry registers and lists models
 4. ModelRouter selects correct model for task category
 5. ModelRouter raises ModelNotAvailableError when no models registered
 6. TaskClassifier: security keywords → SECURITY
 7. TaskClassifier: operations keywords → OPERATIONS
 8. TaskClassifier: coding keywords → CODING
 9. TaskClassifier: no keywords → GENERAL
10. TaskClassifier output is valid Pydantic model
11. Unknown tool → ToolNotFoundError (DENY)
12. LLM cannot execute shell via tool (no shell tool registered)
13. LLM cannot execute SQL via tool (no SQL tool registered)
14. LLM cannot execute filesystem via tool (no filesystem tool registered)
15. Calculator tool: valid expression
16. Calculator tool: invalid expression blocked
17. Verifier: valid LLM response → VERIFIED
18. Verifier: failed LLM response → FAILED
19. Verifier: missing required fields → PARTIALLY_VERIFIED or FAILED
"""

from __future__ import annotations

import pytest
from src.ai.model_registry import ModelRegistry, ModelRouter, build_default_registry
from src.ai.providers.base import LLMRequest, ModelCapability, ModelMetadata
from src.ai.schemas import TaskCategory
from src.core.exceptions import ModelNotAvailableError, ToolNotFoundError
from src.orchestrator.task_classifier import TaskClassifier
from src.orchestrator.verifier import VerificationStatus, Verifier
from src.tools.base import (
    CalculatorTool,
    ToolSelector,
    build_default_tool_registry,
)

# ── Test 1: Ollama unavailable → controlled failure ─────────────────────


@pytest.mark.asyncio
async def test_ollama_unavailable_controlled_failure() -> None:
    """When Ollama is not running, generate() returns success=False, no exception."""
    import os

    from src.ai.providers.ollama_provider import OllamaProvider

    # Point to a port that is definitely not listening
    os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:19999"
    from src.core.config import get_settings

    get_settings.cache_clear()

    provider = OllamaProvider()
    request = LLMRequest(model="gemma3:4b", prompt="Hello", timeout_seconds=2.0)
    response = await provider.generate(request)

    assert response.success is False
    assert response.error != ""
    assert response.content == ""

    # Restore
    os.environ.pop("OLLAMA_BASE_URL", None)
    get_settings.cache_clear()


# ── Test 2: Malformed response → controlled failure ─────────────────────


@pytest.mark.asyncio
async def test_ollama_malformed_response_controlled() -> None:
    """A malformed Ollama response returns success=False without crashing."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"response": 12345})  # not a string

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    from src.ai.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider()
    request = LLMRequest(model="gemma3:4b", prompt="test")

    with patch("httpx.AsyncClient", return_value=mock_client):
        response = await provider.generate(request)

    assert response.success is False
    assert "Malformed" in response.error


# ── Test 3: ModelRegistry registers and lists models ───────────────────


def test_model_registry_register_and_list() -> None:
    """ModelRegistry stores and retrieves model metadata."""
    registry = ModelRegistry()
    meta = ModelMetadata(
        name="test-model",
        provider="ollama",
        capabilities=[ModelCapability.GENERAL],
        enabled=True,
        priority=5,
    )
    registry.register_model(meta)
    models = registry.list_models()
    assert len(models) == 1
    assert models[0].name == "test-model"


# ── Test 4: ModelRouter selects correct model ───────────────────────────


def test_model_router_selects_by_capability() -> None:
    """ModelRouter picks the highest-priority capable model."""
    registry = build_default_registry()
    router = ModelRouter(registry)

    model = router.select_model(TaskCategory.GENERAL)
    assert model.provider == "ollama"
    assert ModelCapability.GENERAL in model.capabilities


def test_model_router_fallback_to_general() -> None:
    """ModelRouter falls back to GENERAL capability when no specific match."""
    registry = ModelRegistry()
    from src.ai.providers.ollama_provider import OllamaProvider

    registry.register_provider(OllamaProvider())
    registry.register_model(
        ModelMetadata(
            name="general-only",
            provider="ollama",
            capabilities=[ModelCapability.GENERAL],
            enabled=True,
            priority=1,
        )
    )
    router = ModelRouter(registry)
    # CODING has no coding-capable model, should fall back to GENERAL
    model = router.select_model(TaskCategory.CODING)
    assert model.name == "general-only"


# ── Test 5: ModelRouter raises when no models ──────────────────────────


def test_model_router_no_models_raises() -> None:
    """ModelRouter raises ModelNotAvailableError when registry is empty."""
    registry = ModelRegistry()
    router = ModelRouter(registry)
    with pytest.raises(ModelNotAvailableError):
        router.select_model(TaskCategory.GENERAL)


# ── Tests 6-10: TaskClassifier ─────────────────────────────────────────


def test_classifier_security_keywords() -> None:
    clf = TaskClassifier()
    result = clf.classify("Check for security vulnerabilities in the firewall")
    assert result.category == TaskCategory.SECURITY
    assert result.rule_match_score > 0.5


def test_classifier_operations_keywords() -> None:
    clf = TaskClassifier()
    result = clf.classify("Deploy the new docker container to the server")
    assert result.category == TaskCategory.OPERATIONS


def test_classifier_coding_keywords() -> None:
    clf = TaskClassifier()
    result = clf.classify("Debug this Python function and refactor the code")
    assert result.category == TaskCategory.CODING


def test_classifier_general_fallback() -> None:
    clf = TaskClassifier()
    result = clf.classify("Hello, how are you?")
    assert result.category == TaskCategory.GENERAL
    assert result.rule_match_score == 0.5


def test_classifier_output_is_valid_pydantic() -> None:
    """TaskClassifier always returns a valid TaskClassification."""
    from src.ai.schemas import TaskClassification

    clf = TaskClassifier()
    result = clf.classify("some random input")
    assert isinstance(result, TaskClassification)
    assert 0.0 <= result.rule_match_score <= 1.0


# ── Tests 11-14: Tool security boundary ────────────────────────────────


def test_unknown_tool_denied() -> None:
    """Requesting an unregistered tool raises ToolNotFoundError."""
    registry = build_default_tool_registry()
    selector = ToolSelector(registry)
    with pytest.raises(ToolNotFoundError):
        selector.select("shell_execute")


def test_no_shell_tool_registered() -> None:
    """No shell execution tool is registered in the default registry."""
    registry = build_default_tool_registry()
    tool_names = {t.name for t in registry.list_tools()}
    shell_names = {"shell", "shell_execute", "bash", "cmd", "exec"}
    assert tool_names.isdisjoint(shell_names), f"Shell tool found: {tool_names & shell_names}"


def test_no_sql_tool_registered() -> None:
    """No SQL execution tool is registered in the default registry."""
    registry = build_default_tool_registry()
    tool_names = {t.name for t in registry.list_tools()}
    sql_names = {"sql", "sql_execute", "query", "database_exec"}
    assert tool_names.isdisjoint(sql_names)


def test_no_filesystem_tool_registered() -> None:
    """No filesystem write tool is registered in the default registry."""
    registry = build_default_tool_registry()
    for tool in registry.list_tools():
        assert not tool.allows_filesystem, f"{tool.name} claims filesystem access"
        assert not tool.allows_shell, f"{tool.name} claims shell access"
        assert not tool.allows_sql, f"{tool.name} claims SQL access"


# ── Tests 15-16: Calculator tool ───────────────────────────────────────


@pytest.mark.asyncio
async def test_calculator_valid_expression() -> None:
    """Calculator evaluates valid arithmetic expressions."""
    tool = CalculatorTool()
    result = await tool.execute({"expression": "2 + 2 * 3"})
    assert result.success is True
    assert result.output == "8"


@pytest.mark.asyncio
async def test_calculator_blocks_invalid_expression() -> None:
    """Calculator rejects non-arithmetic input (no code execution)."""
    tool = CalculatorTool()
    result = await tool.execute({"expression": "__import__('os').system('ls')"})
    assert result.success is False
    assert "arithmetic" in result.error.lower() or "invalid" in result.error.lower()


# ── Tests 17-19: Verifier ──────────────────────────────────────────────


def test_verifier_valid_llm_response() -> None:
    """Valid LLM response → VERIFIED."""
    v = Verifier()
    report = v.verify_llm_response(content="Hello world", success=True, error="")
    assert report.status == VerificationStatus.VERIFIED


def test_verifier_failed_llm_response() -> None:
    """Failed LLM response with empty content → FAILED."""
    v = Verifier()
    report = v.verify_llm_response(content="", success=False, error="timeout")
    assert report.status == VerificationStatus.FAILED


def test_verifier_missing_required_fields() -> None:
    """Missing required fields → PARTIALLY_VERIFIED or FAILED."""
    v = Verifier()
    report = v.verify_structured_output(
        data={"tool": "calculator"},
        required_fields=["tool", "output", "success"],
    )
    assert report.status in (VerificationStatus.PARTIALLY_VERIFIED, VerificationStatus.FAILED)
    assert any("missing_field" in f for f in report.checks_failed)


# ── Tests 20-21: Structured execution & Offline diagnostics ─────────────


@pytest.mark.asyncio
async def test_agent_structured_execution() -> None:
    """Agent parses structured output when structured=True."""
    from src.agents.base import AgentRequest, GeneralAgent
    from src.ai.providers.base import LLMResponse, ModelProvider

    class MockStructuredProvider(ModelProvider):
        @property
        def provider_name(self) -> str:
            return "mock"

        async def generate(self, request: LLMRequest) -> LLMResponse:
            json_text = (
                '{"summary": "Test Summary", "details": ["Item 1", "Item 2"], '
                '"action_items": ["Action 1"]}'
            )
            return LLMResponse(
                model=request.model, provider="mock", content=json_text, success=True
            )

        async def is_available(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["mock-model"]

    agent = GeneralAgent()
    req = AgentRequest(task="Perform audit", model="mock-model", structured=True)
    res = await agent.execute(req, MockStructuredProvider())

    assert res.success is True
    assert "structured_schema_validated" in res.evidence
    assert len(res.artifacts) == 1
    assert res.artifacts[0]["summary"] == "Test Summary"
    assert res.artifacts[0]["details"] == ["Item 1", "Item 2"]


@pytest.mark.asyncio
async def test_agent_offline_diagnostic_message() -> None:
    """Agent returns a helpful diagnostic message when provider fails."""
    from src.agents.base import AgentRequest, GeneralAgent
    from src.ai.providers.base import LLMResponse, ModelProvider

    class MockOfflineProvider(ModelProvider):
        @property
        def provider_name(self) -> str:
            return "mock"

        async def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                model=request.model,
                provider="mock",
                content="",
                success=False,
                error="Ollama server is not available",
            )

        async def is_available(self) -> bool:
            return False

        async def list_models(self) -> list[str]:
            return []

    agent = GeneralAgent()
    req = AgentRequest(task="Help me", model="gemma3:4b")
    res = await agent.execute(req, MockOfflineProvider())

    assert res.success is False
    assert "Model execution failed (Ollama server is not available)" in res.output
    assert "Ensure the Ollama service is active" in res.output
