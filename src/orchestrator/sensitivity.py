"""
ServerGen AI — Data Sensitivity Resolver.

Data sensitivity must come from TRUSTED metadata/policy — never from the LLM and
never from an unverified client claim that could LOWER it.

Resolution rules (deterministic):
1. Baseline for free-text requests is INTERNAL (this is an internal enterprise
   system; "unknown" always resolves to the safer INTERNAL, never PUBLIC).
2. Task category can raise the floor (e.g. SECURITY work is at least CONFIDENTIAL).
3. Content markers in the request can only ESCALATE (e.g. "classified" → RESTRICTED).
4. A client-declared level can only RAISE the result, never lower it.
5. PUBLIC is reachable only through trusted resource metadata registered by the
   knowledge layer (Module 3 plugs into ``ResourceSensitivityProvider``).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.ai.schemas import (
    DEFAULT_SENSITIVITY,
    DataSensitivity,
    TaskCategory,
    sensitivity_at_least,
)

_RESTRICTED_RE = re.compile(
    r"\b(top[- ]secret|classified|restricted|defen[cs]e (?:contract|programme|program)|"
    r"clearance|national security)\b",
    re.IGNORECASE,
)
_CONFIDENTIAL_RE = re.compile(
    r"\b(confidential|proprietary|trade secret|internal only|personnel|salary|payroll|"
    r"hr record|credentials?|passwords?|private key)\b",
    re.IGNORECASE,
)

_CATEGORY_FLOOR: dict[TaskCategory, DataSensitivity] = {
    TaskCategory.SECURITY: DataSensitivity.CONFIDENTIAL,
}


class ResourceSensitivityProvider(ABC):
    """
    Extension point for trusted resource metadata (documents, datasets, systems).

    Module 3 (RAG) will implement this so retrieved documents carry authoritative
    sensitivity labels. Not implemented in the current prototype.
    """

    @abstractmethod
    def sensitivity_of(self, resource_id: str) -> DataSensitivity | None:
        """Return the trusted sensitivity for a resource, or None if unknown."""


@dataclass(frozen=True)
class SensitivityResolution:
    """Resolved sensitivity and the reasons that produced it."""

    level: DataSensitivity
    reasons: list[str] = field(default_factory=list)


def _max_level(a: DataSensitivity, b: DataSensitivity) -> DataSensitivity:
    return a if sensitivity_at_least(a, b) else b


class SensitivityResolver:
    """Deterministic sensitivity resolution (see module docstring)."""

    def __init__(self, resource_provider: ResourceSensitivityProvider | None = None) -> None:
        self._resource_provider = resource_provider

    def resolve(
        self,
        *,
        text: str,
        category: TaskCategory,
        declared: DataSensitivity | None = None,
        resource_id: str | None = None,
    ) -> SensitivityResolution:
        """Resolve the effective sensitivity for a request."""
        reasons: list[str] = []
        level = DEFAULT_SENSITIVITY
        reasons.append(f"baseline={level.value}")

        # Trusted resource metadata (future knowledge layer) may set the floor.
        if resource_id and self._resource_provider is not None:
            trusted = self._resource_provider.sensitivity_of(resource_id)
            if trusted is not None:
                level = trusted
                reasons.append(f"trusted_resource_metadata={trusted.value}")

        floor = _CATEGORY_FLOOR.get(category)
        if floor is not None and not sensitivity_at_least(level, floor):
            level = floor
            reasons.append(f"category_floor:{category.value}={floor.value}")

        if _RESTRICTED_RE.search(text):
            level = _max_level(level, DataSensitivity.RESTRICTED)
            reasons.append("content_marker=restricted")
        elif _CONFIDENTIAL_RE.search(text):
            level = _max_level(level, DataSensitivity.CONFIDENTIAL)
            reasons.append("content_marker=confidential")

        if declared is not None and not sensitivity_at_least(level, declared):
            level = declared
            reasons.append(f"client_declared_higher={declared.value}")

        return SensitivityResolution(level=level, reasons=reasons)
