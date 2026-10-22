"""
ServerGen AI — Verifier.

Performs deterministic checks on orchestrator outputs.
Does NOT use LLM self-confidence as verification.

Checks:
- Schema validation (Pydantic)
- Required fields present
- Tool execution status
- Execution errors

Returns: VERIFIED / PARTIALLY_VERIFIED / UNVERIFIED / FAILED
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    FAILED = "failed"


class VerificationReport(BaseModel):
    status: VerificationStatus
    checks_passed: list[str] = []
    checks_failed: list[str] = []
    notes: str = ""


class Verifier:
    """
    Deterministic output verifier.

    Checks structure, required fields, and execution status.
    Never uses LLM confidence scores as verification.
    """

    def verify_llm_response(self, content: str, success: bool, error: str) -> VerificationReport:
        """Verify an LLM response is structurally valid."""
        passed, failed = [], []

        if success:
            passed.append("provider_success")
            if content and len(content.strip()) > 0:
                passed.append("non_empty_content")
                if not any(marker in content for marker in ("<|start_header_id|>", "<|im_start|>", "[INST]")):
                    passed.append("no_raw_tokens_leaked")
                else:
                    failed.append("raw_system_tokens_detected")
            else:
                failed.append("empty_content")
        else:
            failed.append(f"provider_error: {error or 'unknown'}")

        status = self._compute_status(passed, failed)
        return VerificationReport(status=status, checks_passed=passed, checks_failed=failed)

    def verify_tool_result(
        self, tool: str, success: bool, output: str, error: str
    ) -> VerificationReport:
        """Verify a tool execution result."""
        passed, failed = [], []

        if tool:
            passed.append("tool_name_present")
        else:
            failed.append("missing_tool_name")

        if success:
            passed.append("tool_execution_success")
        else:
            failed.append(f"tool_execution_failed: {error}")

        if output:
            passed.append("output_present")
        else:
            failed.append("empty_output")

        status = self._compute_status(passed, failed)
        return VerificationReport(status=status, checks_passed=passed, checks_failed=failed)

    def verify_structured_output(
        self, data: dict, required_fields: list[str]
    ) -> VerificationReport:
        """Verify a structured dict has all required fields."""
        passed, failed = [], []

        for field in required_fields:
            if field in data and data[field] is not None:
                passed.append(f"field_present:{field}")
            else:
                failed.append(f"missing_field:{field}")

        status = self._compute_status(passed, failed)
        return VerificationReport(status=status, checks_passed=passed, checks_failed=failed)

    @staticmethod
    def _compute_status(passed: list[str], failed: list[str]) -> VerificationStatus:
        if not failed:
            return VerificationStatus.VERIFIED
        if not passed:
            return VerificationStatus.FAILED
        return VerificationStatus.PARTIALLY_VERIFIED
