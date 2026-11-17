"""
ServerGen AI — Tool Abstractions.

Tools are controlled interfaces that the LLM may REQUEST (never directly invoke).
Flow: LLM structured output → Pydantic validation → ToolSelector → PolicyEngine → Tool.execute()

CRITICAL: No tool may execute arbitrary shell, SQL, Python, or filesystem commands.
Unknown tools are DENIED.
"""

from __future__ import annotations

import ast
import operator
from abc import ABC, abstractmethod
from collections.abc import Callable

from pydantic import BaseModel, Field

from src.core.exceptions import ToolNotFoundError


class ToolRequest(BaseModel):
    """Validated structured request from LLM output."""

    requested_action: str
    tool: str
    parameters: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result of a controlled tool execution."""

    tool: str
    success: bool
    output: str = ""
    error: str = ""


class ToolMetadata(BaseModel):
    name: str
    description: str
    required_permission: str
    potential_impact: str = "low"
    # Explicitly forbidden capabilities — enforced at registration
    allows_shell: bool = False
    allows_sql: bool = False
    allows_filesystem: bool = False


class Tool(ABC):
    """Abstract base for all controlled tools."""

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Tool metadata including required permission and impact."""

    @abstractmethod
    async def execute(self, parameters: dict) -> ToolResult:
        """
        Execute the tool with validated parameters.
        Must NOT run arbitrary shell/SQL/filesystem commands.
        """


# ── Safe built-in tools ─────────────────────────────────────────────────


_MAX_EXPRESSION_LENGTH = 200
_MAX_ABS_VALUE = 10**15
_MAX_EXPONENT = 64
_BIN_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class _ArithmeticError(ValueError):
    """Raised for any expression outside the supported arithmetic subset."""


def _eval_node(node: ast.AST, depth: int = 0) -> float:
    """Evaluate a parsed arithmetic expression using an explicit allow-list of node types."""
    if depth > 20:
        raise _ArithmeticError("Expression too deeply nested")
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if isinstance(node.value, bool) or abs(node.value) > _MAX_ABS_VALUE:
            raise _ArithmeticError("Number out of range")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left, depth + 1)
        right = _eval_node(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise _ArithmeticError("Exponent too large")
        result = _BIN_OPS[type(node.op)](left, right)
        if isinstance(result, complex) or abs(result) > _MAX_ABS_VALUE:
            raise _ArithmeticError("Result out of range")
        return result
    raise _ArithmeticError("Only basic arithmetic is allowed")


class CalculatorTool(Tool):
    """Safe arithmetic calculator — parses with ``ast``; never calls eval()/exec()."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="calculator",
            description="Evaluate simple arithmetic expressions",
            required_permission="ai.execute",
            potential_impact="low",
        )

    async def execute(self, parameters: dict) -> ToolResult:
        expression = str(parameters.get("expression", "")).strip()
        name = self.metadata.name
        if not expression or len(expression) > _MAX_EXPRESSION_LENGTH:
            return ToolResult(tool=name, success=False, error="Invalid expression length")
        try:
            value = _eval_node(ast.parse(expression, mode="eval"))
        except ZeroDivisionError:
            return ToolResult(tool=name, success=False, error="Division by zero")
        except (SyntaxError, _ArithmeticError, OverflowError, RecursionError) as exc:
            reason = str(exc) if isinstance(exc, _ArithmeticError) else "Invalid expression"
            return ToolResult(tool=name, success=False, error=f"Invalid expression — {reason}")
        return ToolResult(tool=name, success=True, output=str(value))


class SystemInfoTool(Tool):
    """Returns static system information — read-only, no execution."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="system_info",
            description="Return static system information (read-only)",
            required_permission="system.read",
            potential_impact="low",
        )

    async def execute(self, parameters: dict) -> ToolResult:
        import platform

        info = {
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "machine": platform.machine(),
        }
        return ToolResult(
            tool=self.metadata.name,
            success=True,
            output=str(info),
        )


# ── Tool Registry & Selector ────────────────────────────────────────────


class ToolRegistry:
    """Registry of all registered controlled tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        meta = tool.metadata
        # Safety assertion: no tool may claim shell/SQL/filesystem access
        for forbidden, label in (
            (meta.allows_shell, "shell"),
            (meta.allows_sql, "SQL"),
            (meta.allows_filesystem, "filesystem"),
        ):
            if forbidden:
                msg = f"Tool {meta.name} claims {label} access — forbidden"
                raise ValueError(msg)
        self._tools[meta.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolMetadata]:
        return [t.metadata for t in self._tools.values()]


class ToolSelector:
    """
    Selects and validates tool requests from LLM output.

    If the requested tool is not registered → DENY (raise ToolNotFoundError).
    LLM output is validated with Pydantic before reaching this selector.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def select(self, tool_name: str) -> Tool:
        """
        Look up a tool by name.
        Raises ToolNotFoundError if not registered — unknown tools are DENIED.
        """
        tool = self.registry.get(tool_name)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{tool_name}' is not registered — request denied")
        return tool


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(SystemInfoTool())
    from src.tools.docgen import PDFGeneratorTool, PresentationGeneratorTool

    registry.register(PDFGeneratorTool())
    registry.register(PresentationGeneratorTool())
    return registry
