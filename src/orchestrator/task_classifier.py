"""
ServerGen AI — Task Classifier (deterministic rules).

Converts a natural-language request into a validated ``TaskClassification``.

TRUST MODEL
- Everything security-relevant here (category, operation type, production impact)
  is derived from explicit, auditable rules. The LLM never decides these values
  (an optional LLM refinement may only re-label a plain GENERAL/QUERY request
  among low-risk categories — see ``llm_task_classifier``).
- The rule set is intentionally biased toward the SAFE side: an action verb
  combined with a system target is escalated to OPERATIONS even if the text
  otherwise looks harmless.
"""

from __future__ import annotations

import re

from src.ai.schemas import OperationType, TaskCategory, TaskClassification

# Keyword sets per category (order matters — earlier categories win ties).
_CATEGORY_KEYWORDS: list[tuple[TaskCategory, frozenset[str]]] = [
    (
        TaskCategory.SECURITY,
        frozenset(
            {
                "security",
                "vulnerability",
                "vulnerabilities",
                "cve",
                "exploit",
                "firewall",
                "intrusion",
                "malware",
                "threat",
                "audit",
                "compliance",
                "penetration",
                "pentest",
                "siem",
                "incident",
                "credential",
                "credentials",
                "permission",
                "permissions",
            }
        ),
    ),
    (
        TaskCategory.OPERATIONS,
        frozenset(
            {
                "deploy",
                "restart",
                "server",
                "servers",
                "service",
                "services",
                "infrastructure",
                "kubernetes",
                "docker",
                "container",
                "pipeline",
                "ci/cd",
                "monitor",
                "alert",
                "uptime",
                "backup",
                "restore",
                "plant",
                "scada",
                "plc",
            }
        ),
    ),
    (
        TaskCategory.CODING,
        frozenset(
            {
                "code",
                "function",
                "class",
                "bug",
                "debug",
                "refactor",
                "implement",
                "algorithm",
                "script",
                "python",
                "javascript",
                "typescript",
                "sql",
                "api",
                "test",
                "unittest",
            }
        ),
    ),
    (
        TaskCategory.DOCUMENT,
        frozenset(
            {
                "document",
                "documents",
                "summarize",
                "summary",
                "analyze",
                "analyse",
                "review",
                "read",
                "extract",
                "pdf",
                "file",
                "text",
                "content",
                "knowledge",
                "search",
            }
        ),
    ),
    (
        TaskCategory.REPORTING,
        frozenset(
            {
                "report",
                "dashboard",
                "metric",
                "kpi",
                "chart",
                "graph",
                "statistics",
                "analytics",
                "trend",
                "forecast",
            }
        ),
    ),
]

# Action verbs (prefix-matched so inflections are covered: "restarting", "disabled" ...).
_EXECUTE_RE = re.compile(
    r"\b(restart|reboot|shutdown|deploy|execut|launch|trigger|rollback|terminat|kill|"
    r"run|runs|running|start|starts|stop|stops|restor)\w*",
    re.IGNORECASE,
)
_MODIFY_RE = re.compile(
    r"\b(delet|remov|modif|chang|updat|disabl|enabl|configur|reconfigur|grant|revok|"
    r"rotat|patch|upgrad|install|uninstall|overwrit|wip|format|reset|bypass)\w*",
    re.IGNORECASE,
)
# Things that, if acted upon, affect systems rather than just text.
_SYSTEM_TARGET_RE = re.compile(
    r"\b(server|servers|service|services|config|configuration|settings|firewall|policy|"
    r"policies|database|db|network|system|systems|permission|permissions|access|rule|rules|"
    r"pipeline|container|cluster|kubernetes|docker|credential|credentials|password|passwords|"
    r"account|accounts|role|roles|vpn|router|switch|plc|scada|plant|infrastructure|backup|"
    r"certificate|production|prod)\b",
    re.IGNORECASE,
)
_PRODUCTION_RE = re.compile(
    r"\b(production|prod|live|plant|refinery|scada|plc|dcs|control system|"
    r"critical infrastructure|all users|every server|entire)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[\w/]+")


class TaskClassifier:
    """Deterministic, rule-based classifier producing a validated TaskClassification."""

    def classify(self, user_input: str) -> TaskClassification:
        """Classify a request. Pure function of the input text."""
        text = user_input.lower()
        tokens = set(_TOKEN_RE.findall(text))

        best_category = TaskCategory.GENERAL
        best_score = 0
        for category, keywords in _CATEGORY_KEYWORDS:
            score = len(tokens & keywords)
            if score > best_score:
                best_score = score
                best_category = category
        match_score = 0.0 if best_score == 0 else min(0.5 + best_score * 0.1, 0.95)
        if best_score == 0:
            match_score = 0.5

        has_execute = bool(_EXECUTE_RE.search(text))
        has_modify = bool(_MODIFY_RE.search(text))
        has_target = bool(_SYSTEM_TARGET_RE.search(text))
        has_production = bool(_PRODUCTION_RE.search(text))

        # Safe-side escalation: acting on a system target is an operations/security matter.
        action_on_system = (has_execute or has_modify) and has_target
        if action_on_system and best_category in (
            TaskCategory.GENERAL,
            TaskCategory.DOCUMENT,
            TaskCategory.REPORTING,
        ):
            best_category = TaskCategory.OPERATIONS
        if action_on_system and best_category is TaskCategory.CODING and has_production:
            best_category = TaskCategory.OPERATIONS

        operation_type = self._operation_type(
            best_category, tokens, action_on_system, has_execute, has_modify
        )
        production_affecting = has_production and operation_type in (
            OperationType.MODIFY,
            OperationType.EXECUTE,
        )

        return TaskClassification(
            category=best_category,
            operation_type=operation_type,
            production_affecting=production_affecting,
            rule_match_score=match_score,
            reasoning=(
                f"Keyword match: {best_score} term(s) matched '{best_category}'; "
                f"operation={operation_type}; production_affecting={production_affecting}"
            ),
        )

    @staticmethod
    def _operation_type(
        category: TaskCategory,
        tokens: set[str],
        action_on_system: bool,
        has_execute: bool,
        has_modify: bool,
    ) -> OperationType:
        if action_on_system and category in (TaskCategory.OPERATIONS, TaskCategory.SECURITY):
            # Execution outranks modification when both verbs are present.
            return OperationType.EXECUTE if has_execute and not has_modify else OperationType.MODIFY
        if category is TaskCategory.REPORTING or "report" in tokens:
            return OperationType.REPORT
        if category is TaskCategory.DOCUMENT:
            return OperationType.ANALYSIS
        return OperationType.QUERY
