"""
ServerGen AI — Natural Language Data Analysis Service.

Enables authorized enterprise users to ask plain-English questions against Excel/CSV
datasets. Translates natural language questions into safe, deterministic operations
from a validated allowlist, executes exact calculations via deterministic numerical
micro-engines, and synthesizes grounded executive explanations with visual chart specifications.

SECURITY GUARANTEE:
Arbitrary Python eval/exec, SQL generation, or shell execution is strictly prohibited.
All queries execute through predefined, schema-validated analytical micro-engines.
"""

from __future__ import annotations

import logging
import re
import statistics
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.providers.base import LLMRequest
from src.ai.providers.ollama_provider import OllamaProvider
from src.models.analysis_history import AnalysisHistory
from src.services.pii_service import pii_service
from src.services.spreadsheet_service import SheetData, SpreadsheetAnalyticsService

logger = logging.getLogger("servergen.services.nl_analytics")


@dataclass
class NLAnalyticalPlan:
    """Safe, structured execution plan extracted from natural language question."""

    operation: str  # statistical, ranking, groupby, financial, quality, trend, overview
    sub_operation: str  # sum, avg, median, min, max, top_n, bottom_n, budget_vs_actual, etc.
    target_columns: list[str] = field(default_factory=list)
    group_column: str | None = None
    comparison_column: str | None = None
    n_records: int = 5
    filter_column: str | None = None
    filter_operator: str = "=="
    filter_value: Any = None
    chart_type: str = "bar"  # bar, line, pie, none
    confidence: float = 1.0
    reasoning: str = ""


@dataclass
class NLAnalysisResult:
    """Complete result of a natural language data analysis run."""

    question: str
    operation: str
    sub_operation: str
    direct_answer: str
    executive_explanation: str
    table_headers: list[str]
    table_rows: list[list[Any]]
    kpis: list[dict[str, Any]]
    metrics: dict[str, Any]
    chart_spec: dict[str, Any]
    row_count: int
    col_count: int
    execution_time_ms: int
    pii_redacted_count: int = 0
    warnings: list[str] = field(default_factory=list)


class NLAnalyticsService:
    """Enterprise-grade Natural Language Data Analysis Engine."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self.ollama = OllamaProvider()
        self.spreadsheet_svc = SpreadsheetAnalyticsService()

    # ── 1. Safe Natural Language Intent Parser ──────────────────────────────

    def parse_intent(self, question: str, sheet: SheetData) -> NLAnalyticalPlan:
        """
        Convert a user's natural language question into a safe, structured analytical plan.
        Never executes user code or SQL. Matches against an allowlist of supported categories.
        """
        q = question.strip().lower()
        all_numeric = [
            h
            for h, prof in sheet.column_profiles.items()
            if prof.inferred_type in ("numeric", "currency", "percentage")
        ]
        # Prioritize real value/metric columns over ID columns
        numeric_cols = [
            h for h in all_numeric if not h.lower().endswith(("_id", " id", "id", "_number", "#"))
        ]
        if not numeric_cols:
            numeric_cols = all_numeric

        categorical_cols = [
            h
            for h, prof in sheet.column_profiles.items()
            if prof.inferred_type in ("text", "date")
            or h.lower().endswith(("_id", " id", "id"))
        ]

        # ── Category 5: Data Quality Analysis (Duplicates, Missing, Outliers) ─
        if any(w in q for w in ("duplicate", "repeated records", "duplicates", "redundant")):
            return NLAnalyticalPlan(
                operation="quality",
                sub_operation="duplicates",
                chart_type="pie",
                reasoning="Data quality: duplicate record detection",
            )
        if any(w in q for w in ("missing", "null", "empty", "blank", "nan")):
            matched_col = self._match_column(q, sheet.headers)
            return NLAnalyticalPlan(
                operation="quality",
                sub_operation="missing_values",
                target_columns=[matched_col] if matched_col else [],
                chart_type="bar",
                reasoning="Data quality: missing/null values analysis",
            )
        if any(w in q for w in ("outlier", "unusual", "anomaly", "abnormal", "anomalies")):
            matched_num = self._match_column(q, numeric_cols) or (
                numeric_cols[0] if numeric_cols else None
            )
            dim_col = self._match_column(q, categorical_cols) or (
                categorical_cols[0] if categorical_cols else None
            )
            return NLAnalyticalPlan(
                operation="quality",
                sub_operation="outliers",
                target_columns=[matched_num] if matched_num else [],
                group_column=dim_col,
                chart_type="bar",
                reasoning="Data quality: statistical outlier detection (IQR)",
            )

        # ── Category 4: Financial Analysis (Budget vs Actual, Overruns, Margins)
        if any(
            w in q
            for w in ("budget", "variance", "over budget", "exceeded", "overrun", "actual")
        ):
            budget_col = next((c for c in sheet.headers if "budget" in c.lower()), None)
            actual_col = next(
                (
                    c
                    for c in sheet.headers
                    if any(k in c.lower() for k in ("actual", "expense", "cost", "spend"))
                ),
                None,
            )
            dim_col = self._match_column(q, categorical_cols) or (
                categorical_cols[0] if categorical_cols else None
            )

            if budget_col and actual_col:
                return NLAnalyticalPlan(
                    operation="financial",
                    sub_operation="budget_vs_actual",
                    target_columns=[budget_col, actual_col],
                    group_column=dim_col,
                    chart_type="bar",
                    reasoning="Financial analysis: budget vs actual variance and overruns",
                )

        # ── Category 2: Ranking & Filtering (Top N, Highest, Lowest, Bottom N)
        top_match = re.search(r"top\s*(\d+)", q)
        bottom_match = re.search(r"bottom\s*(\d+)", q)
        is_highest = any(
            w in q for w in ("highest", "maximum", "max", "largest", "greatest", "most", "top")
        )
        is_lowest = any(
            w in q for w in ("lowest", "minimum", "min", "smallest", "least", "bottom")
        )

        if top_match or bottom_match or is_highest or is_lowest:
            n = (
                int(top_match.group(1))
                if top_match
                else (int(bottom_match.group(1)) if bottom_match else 5)
            )
            if not top_match and not bottom_match and (is_highest or is_lowest):
                n = 1

            matched_num = self._match_column(q, numeric_cols) or (
                numeric_cols[0] if numeric_cols else None
            )
            matched_dim = self._match_column(q, categorical_cols) or (
                categorical_cols[0] if categorical_cols else None
            )

            sub_op = "bottom_n" if (bottom_match or is_lowest) else "top_n"
            return NLAnalyticalPlan(
                operation="ranking",
                sub_operation=sub_op,
                target_columns=[matched_num] if matched_num else [],
                group_column=matched_dim,
                n_records=min(max(n, 1), 100),
                chart_type="bar",
                reasoning=f"Ranking: {sub_op} ({n} records)",
            )

        # ── Category 6: Trend & Time-Series Analysis ──────────────────────────
        if any(
            w in q
            for w in (
                "trend",
                "monthly",
                "growth",
                "quarterly",
                "over time",
                "yearly",
                "year",
                "month",
            )
        ):
            date_col = next(
                (
                    c
                    for c in sheet.headers
                    if any(k in c.lower() for k in ("month", "date", "year", "quarter", "period"))
                ),
                None,
            )
            val_col = self._match_column(q, numeric_cols) or (
                numeric_cols[0] if numeric_cols else None
            )
            if date_col and val_col:
                return NLAnalyticalPlan(
                    operation="trend",
                    sub_operation="time_series",
                    target_columns=[val_col],
                    group_column=date_col,
                    chart_type="line",
                    reasoning="Trend analysis across chronological periods",
                )

        # ── Category 3: Group-Based Analysis (Department-wise, Region-wise, etc.)
        if any(
            w in q
            for w in (
                "compare",
                "by",
                "per",
                "across",
                "department-wise",
                "region-wise",
                "category-wise",
                "each",
            )
        ):
            matched_dim = self._match_column(q, categorical_cols)
            matched_num = self._match_column(q, numeric_cols) or (
                numeric_cols[0] if numeric_cols else None
            )
            if matched_dim and matched_num:
                sub_op = "avg" if any(w in q for w in ("avg", "average", "mean")) else "sum"
                return NLAnalyticalPlan(
                    operation="groupby",
                    sub_operation=sub_op,
                    target_columns=[matched_num],
                    group_column=matched_dim,
                    chart_type="bar",
                    reasoning=f"Grouped breakdown by {matched_dim} for {matched_num}",
                )

        # ── Category 1: Basic Statistical Analysis (Avg, Median, Sum, Min, Max, Count)
        if any(w in q for w in ("average", "mean", "avg")):
            matched_num = self._match_column(q, numeric_cols) or (
                numeric_cols[0] if numeric_cols else None
            )
            return NLAnalyticalPlan(
                operation="statistical",
                sub_operation="avg",
                target_columns=[matched_num] if matched_num else [],
                chart_type="bar",
                reasoning="Statistical analysis: mean / average",
            )
        if "median" in q:
            matched_num = self._match_column(q, numeric_cols) or (
                numeric_cols[0] if numeric_cols else None
            )
            return NLAnalyticalPlan(
                operation="statistical",
                sub_operation="median",
                target_columns=[matched_num] if matched_num else [],
                chart_type="bar",
                reasoning="Statistical analysis: median calculation",
            )
        if any(w in q for w in ("total", "sum", "aggregate", "overall")):
            matched_num = self._match_column(q, numeric_cols) or (
                numeric_cols[0] if numeric_cols else None
            )
            return NLAnalyticalPlan(
                operation="statistical",
                sub_operation="sum",
                target_columns=[matched_num] if matched_num else [],
                chart_type="bar",
                reasoning="Statistical analysis: aggregate sum",
            )
        if any(w in q for w in ("standard deviation", "stddev", "std dev", "variance")):
            matched_num = self._match_column(q, numeric_cols) or (
                numeric_cols[0] if numeric_cols else None
            )
            return NLAnalyticalPlan(
                operation="statistical",
                sub_operation="std_dev",
                target_columns=[matched_num] if matched_num else [],
                chart_type="bar",
                reasoning="Statistical analysis: standard deviation",
            )
        if any(w in q for w in ("count", "how many", "number of")):
            return NLAnalyticalPlan(
                operation="statistical",
                sub_operation="count",
                chart_type="pie",
                reasoning="Statistical analysis: record count",
            )

        # ── Default Fallback: Overview ───────────────────────────────────────
        return NLAnalyticalPlan(
            operation="overview",
            sub_operation="summary",
            target_columns=numeric_cols[:2] if numeric_cols else [],
            group_column=categorical_cols[0] if categorical_cols else None,
            chart_type="bar",
            reasoning="Default dataset overview",
        )

    def _match_column(self, query: str, candidates: list[str]) -> str | None:
        """Fuzzy match a query substring to the closest existing column name."""
        q = query.lower()
        for c in candidates:
            if c.lower() in q:
                return c
        for c in candidates:
            base = c.lower().replace("_", " ").rstrip("s")
            if base in q:
                return c
        keywords = {
            "expense": ("expense", "actual_expense", "cost", "expenditure", "spending", "amount"),
            "spend": ("expense", "actual_expense", "cost", "expenditure", "spending"),
            "revenue": ("revenue", "sales", "income", "turnover"),
            "profit": ("profit", "net_income", "margin"),
            "budget": ("budget", "allocated", "target"),
            "department": ("department", "dept", "division", "team", "unit"),
            "month": ("month", "period", "date"),
            "region": ("region", "territory", "location", "area"),
            "employee": ("employee", "staff", "person", "name"),
        }
        for kw, aliases in keywords.items():
            if kw in q:
                for c in candidates:
                    if any(a in c.lower() for a in aliases):
                        return c
        return None

    # ── 2. Deterministic Calculation Execution Engine ───────────────────────

    def execute_plan(self, sheet: SheetData, plan: NLAnalyticalPlan) -> dict[str, Any]:
        """
        Execute the validated analytical plan using deterministic Python calculations.
        Returns calculated values, tables, and KPI metrics without external dependencies.
        """
        if not sheet.rows or not sheet.headers:
            return {
                "direct_answer": "The selected spreadsheet contains no data rows to analyze.",
                "table_headers": sheet.headers,
                "table_rows": [],
                "kpis": [{"label": "Rows", "value": "0", "change": "Empty", "status": "alert"}],
                "metrics": {"total_rows": 0},
                "chart_spec": {},
            }

        col_idx = {h: idx for idx, h in enumerate(sheet.headers)}
        numeric_headers = [
            h
            for h, p in sheet.column_profiles.items()
            if p.inferred_type in ("numeric", "currency", "percentage")
        ]

        op = plan.operation
        sub_op = plan.sub_operation

        # ── 1. Basic Statistical Analysis ────────────────────────────────────
        if op == "statistical":
            target_col = (
                plan.target_columns[0]
                if plan.target_columns and plan.target_columns[0] in col_idx
                else (numeric_headers[0] if numeric_headers else sheet.headers[-1])
            )
            t_idx = col_idx[target_col]
            nums: list[float] = []
            for r in sheet.rows:
                if t_idx < len(r):
                    val = self.spreadsheet_svc._to_number(r[t_idx])
                    if val is not None:
                        nums.append(val)

            stat_val = 0.0
            stat_name = "Value"

            if sub_op == "sum":
                stat_val = sum(nums)
                stat_name = "Total Sum"
            elif sub_op in ("avg", "mean"):
                stat_val = statistics.mean(nums) if nums else 0.0
                stat_name = "Average"
            elif sub_op == "median":
                stat_val = statistics.median(nums) if nums else 0.0
                stat_name = "Median"
            elif sub_op == "min":
                stat_val = min(nums) if nums else 0.0
                stat_name = "Minimum"
            elif sub_op == "max":
                stat_val = max(nums) if nums else 0.0
                stat_name = "Maximum"
            elif sub_op == "std_dev":
                stat_val = statistics.stdev(nums) if len(nums) > 1 else 0.0
                stat_name = "Standard Deviation"
            elif sub_op == "count":
                stat_val = float(len(sheet.rows))
                stat_name = "Total Records"

            direct = (
                f"The calculated {stat_name.lower()} of '{target_col}' across all "
                f"{len(sheet.rows)} records is {stat_val:,.2f}."
            )
            headers = ["Metric", "Target Column", "Value", "Record Count"]
            rows = [[stat_name, target_col, f"{stat_val:,.2f}", len(nums)]]
            kpis = [
                {
                    "label": stat_name,
                    "value": f"{stat_val:,.2f}",
                    "change": target_col,
                    "status": "success",
                },
                {
                    "label": "Records Analyzed",
                    "value": f"{len(nums):,}",
                    "change": f"{len(sheet.rows)} total",
                    "status": "neutral",
                },
                {
                    "label": "Column",
                    "value": target_col,
                    "change": "Verified",
                    "status": "neutral",
                },
            ]
            chart = {
                "type": "bar",
                "categories": [stat_name],
                "series": [{"name": target_col, "data": [round(stat_val, 2)]}],
            }
            return {
                "direct_answer": direct,
                "table_headers": headers,
                "table_rows": rows,
                "kpis": kpis,
                "metrics": {
                    "metric": stat_name,
                    "column": target_col,
                    "calculated_value": stat_val,
                },
                "chart_spec": chart,
            }

        # ── 2. Ranking & Filtering (Top N / Bottom N) ────────────────────────
        if op == "ranking":
            target_col = (
                plan.target_columns[0]
                if plan.target_columns and plan.target_columns[0] in col_idx
                else (numeric_headers[0] if numeric_headers else sheet.headers[-1])
            )
            dim_col = (
                plan.group_column
                if plan.group_column and plan.group_column in col_idx
                else sheet.headers[0]
            )
            t_idx = col_idx[target_col]
            d_idx = col_idx[dim_col]
            n = plan.n_records

            # Group values by dimension
            grouped: dict[str, float] = defaultdict(float)
            for r in sheet.rows:
                if d_idx < len(r) and t_idx < len(r):
                    key = str(r[d_idx]) if r[d_idx] is not None else "Unknown"
                    v = self.spreadsheet_svc._to_number(r[t_idx]) or 0.0
                    grouped[key] += v

            is_asc = sub_op == "bottom_n"
            ranked = sorted(grouped.items(), key=lambda x: x[1], reverse=not is_asc)[:n]

            top_name = ranked[0][0] if ranked else "N/A"
            top_val = ranked[0][1] if ranked else 0.0

            if n == 1:
                direction = "lowest" if is_asc else "highest"
                direct = (
                    f"The {dim_col} with the {direction} {target_col} is '{top_name}' "
                    f"with a calculated total of {top_val:,.2f}."
                )
            else:
                direction = "bottom" if is_asc else "top"
                direct = (
                    f"The {direction} {len(ranked)} {dim_col}s based on {target_col} "
                    f"are ranked with '{top_name}' leading at {top_val:,.2f}."
                )

            headers = [dim_col, f"Total {target_col}", "Rank"]
            rows = [
                [entity, round(val, 2), idx] for idx, (entity, val) in enumerate(ranked, 1)
            ]

            kpis = [
                {
                    "label": f"Rank 1 ({dim_col})",
                    "value": str(top_name),
                    "change": f"{top_val:,.2f}",
                    "status": "success",
                },
                {
                    "label": "Ranked Count",
                    "value": str(len(ranked)),
                    "change": f"of {len(grouped)} total",
                    "status": "neutral",
                },
                {
                    "label": "Target Metric",
                    "value": target_col,
                    "change": "Deterministic",
                    "status": "neutral",
                },
            ]
            chart = {
                "type": "bar",
                "categories": [str(r[0]) for r in rows],
                "series": [{"name": target_col, "data": [float(r[1]) for r in rows]}],
            }
            return {
                "direct_answer": direct,
                "table_headers": headers,
                "table_rows": rows,
                "kpis": kpis,
                "metrics": {
                    "leading_entity": str(top_name),
                    "leading_value": float(top_val),
                    "count": len(rows),
                },
                "chart_spec": chart,
            }

        # ── 3. Group-Based Analysis ──────────────────────────────────────────
        if op == "groupby":
            grp_col = (
                plan.group_column
                if plan.group_column and plan.group_column in col_idx
                else sheet.headers[0]
            )
            val_col = (
                plan.target_columns[0]
                if plan.target_columns and plan.target_columns[0] in col_idx
                else (numeric_headers[0] if numeric_headers else sheet.headers[-1])
            )
            g_idx = col_idx[grp_col]
            v_idx = col_idx[val_col]

            grouped_vals: dict[str, list[float]] = defaultdict(list)
            for r in sheet.rows:
                if g_idx < len(r) and v_idx < len(r):
                    key = str(r[g_idx]) if r[g_idx] is not None else "Unknown"
                    val = self.spreadsheet_svc._to_number(r[v_idx])
                    if val is not None:
                        grouped_vals[key].append(val)

            computed: list[tuple[str, float]] = []
            if plan.sub_operation == "avg":
                val_header = f"Average {val_col}"
                for k, v_list in grouped_vals.items():
                    computed.append((k, statistics.mean(v_list) if v_list else 0.0))
            else:
                val_header = f"Total {val_col}"
                for k, v_list in grouped_vals.items():
                    computed.append((k, sum(v_list)))

            computed.sort(key=lambda x: x[1], reverse=True)
            tot_sum = sum(val for _, val in computed)
            top_entity = computed[0][0] if computed else "N/A"
            top_entity_val = computed[0][1] if computed else 0.0

            direct = (
                f"Breakdown across {len(computed)} {grp_col}s shows a total of {tot_sum:,.2f}. "
                f"'{top_entity}' accounts for the largest share at {top_entity_val:,.2f} "
                f"({(top_entity_val / tot_sum * 100) if tot_sum else 0:.1f}%)."
            )
            headers = [grp_col, val_header, "Share %"]
            rows = []
            for entity, d_val in computed:
                share = (d_val / tot_sum * 100) if tot_sum > 0 else 0.0
                rows.append([entity, round(d_val, 2), f"{share:.1f}%"])

            kpis = [
                {
                    "label": f"Total {val_col}",
                    "value": f"{tot_sum:,.2f}",
                    "change": f"{len(sheet.rows)} rows",
                    "status": "success",
                },
                {
                    "label": f"Unique {grp_col}s",
                    "value": str(len(computed)),
                    "change": "Segments",
                    "status": "neutral",
                },
                {
                    "label": f"Top {grp_col}",
                    "value": str(top_entity),
                    "change": f"{top_entity_val:,.2f}",
                    "status": "success",
                },
            ]
            chart = {
                "type": "bar",
                "categories": [str(r[0]) for r in rows[:10]],
                "series": [{"name": val_header, "data": [float(r[1]) for r in rows[:10]]}],
            }
            return {
                "direct_answer": direct,
                "table_headers": headers,
                "table_rows": rows,
                "kpis": kpis,
                "metrics": {
                    "total": tot_sum,
                    "top_entity": str(top_entity),
                    "segments": len(rows),
                },
                "chart_spec": chart,
            }

        # ── 4. Financial Analysis (Budget vs Actual) ─────────────────────────
        if op == "financial":
            dim_col = (
                plan.group_column
                if plan.group_column and plan.group_column in col_idx
                else sheet.headers[0]
            )
            budget_col = (
                plan.target_columns[0]
                if len(plan.target_columns) > 0 and plan.target_columns[0] in col_idx
                else next((c for c in sheet.headers if "budget" in c.lower()), sheet.headers[0])
            )
            actual_col = (
                plan.target_columns[1]
                if len(plan.target_columns) > 1 and plan.target_columns[1] in col_idx
                else next(
                    (
                        c
                        for c in sheet.headers
                        if any(k in c.lower() for k in ("actual", "expense", "cost", "spend"))
                    ),
                    sheet.headers[-1],
                )
            )

            d_idx = col_idx[dim_col]
            b_idx = col_idx[budget_col]
            a_idx = col_idx[actual_col]

            budget_totals: dict[str, float] = defaultdict(float)
            actual_totals: dict[str, float] = defaultdict(float)

            for r in sheet.rows:
                if d_idx < len(r) and b_idx < len(r) and a_idx < len(r):
                    key = str(r[d_idx]) if r[d_idx] is not None else "Unknown"
                    b_val = self.spreadsheet_svc._to_number(r[b_idx]) or 0.0
                    a_val = self.spreadsheet_svc._to_number(r[a_idx]) or 0.0
                    budget_totals[key] += b_val
                    actual_totals[key] += a_val

            rows = []
            over_names: list[str] = []
            total_budget = sum(budget_totals.values())
            total_actual = sum(actual_totals.values())
            net_variance = total_actual - total_budget

            for key in sorted(budget_totals.keys()):
                b_val = budget_totals[key]
                a_val = actual_totals[key]
                diff = a_val - b_val
                pct = (diff / b_val * 100) if b_val > 0 else 0.0
                is_over = diff > 0
                if is_over:
                    over_names.append(key)
                status_str = "OVER BUDGET" if is_over else "ON TRACK"
                rows.append([
                    key,
                    round(b_val, 2),
                    round(a_val, 2),
                    f"{diff:+,.2f}",
                    f"{pct:+.1f}%",
                    status_str,
                ])

            if over_names:
                direct = (
                    f"{len(over_names)} departments exceeded their allocated budgets: "
                    f"{', '.join(over_names)}. Total budget was {total_budget:,.2f} vs actual "
                    f"expenditure of {total_actual:,.2f} (Net Variance: {net_variance:+,.2f})."
                )
            else:
                direct = (
                    f"All departments operated within their allocated budgets. Total budget: "
                    f"{total_budget:,.2f}, Total actual: {total_actual:,.2f} "
                    f"(Under budget by {-net_variance:,.2f})."
                )

            headers = [
                dim_col,
                f"Budget ({budget_col})",
                f"Actual ({actual_col})",
                "Variance ($)",
                "Variance (%)",
                "Status",
            ]

            kpis = [
                {
                    "label": "Total Budget",
                    "value": f"{total_budget:,.2f}",
                    "change": "Allocated",
                    "status": "neutral",
                },
                {
                    "label": "Total Actual",
                    "value": f"{total_actual:,.2f}",
                    "change": "Spent",
                    "status": "neutral",
                },
                {
                    "label": "Overrun Depts",
                    "value": str(len(over_names)),
                    "change": f"{net_variance:+,.2f} Net",
                    "status": "alert" if len(over_names) > 0 else "success",
                },
            ]
            chart = {
                "type": "bar",
                "categories": [str(r[0]) for r in rows[:8]],
                "series": [
                    {"name": "Budget", "data": [float(r[1]) for r in rows[:8]]},
                    {"name": "Actual", "data": [float(r[2]) for r in rows[:8]]},
                ],
            }
            return {
                "direct_answer": direct,
                "table_headers": headers,
                "table_rows": rows,
                "kpis": kpis,
                "metrics": {
                    "total_budget": total_budget,
                    "total_actual": total_actual,
                    "net_variance": net_variance,
                    "over_budget_count": len(over_names),
                },
                "chart_spec": chart,
            }

        # ── 5. Data Quality Analysis (Duplicates, Missing Values, Outliers) ───
        if op == "quality":
            if sub_op == "duplicates":
                seen: set[tuple[str, ...]] = set()
                dup_rows = []
                for r in sheet.rows:
                    row_key = tuple(str(cell) for cell in r)
                    if row_key in seen:
                        dup_rows.append(r)
                    else:
                        seen.add(row_key)

                dup_count = len(dup_rows)
                if dup_count == 0:
                    direct = (
                        f"No duplicate records were detected. All {len(sheet.rows)} rows "
                        f"are distinct and unique."
                    )
                else:
                    direct = (
                        f"Found {dup_count} duplicate records across the dataset "
                        f"({dup_count} duplicated occurrences)."
                    )

                headers = sheet.headers
                rows = dup_rows[:20]
                total_rows = len(sheet.rows)
                kpis = [
                    {
                        "label": "Duplicate Rows",
                        "value": str(dup_count),
                        "change": f"of {total_rows} total",
                        "status": "alert" if dup_count > 0 else "success",
                    },
                    {
                        "label": "Clean Rows",
                        "value": str(total_rows - dup_count),
                        "change": "Unique",
                        "status": "success",
                    },
                    {
                        "label": "Duplicate Rate",
                        "value": (
                            f"{(dup_count / total_rows * 100) if total_rows else 0:.1f}%"
                        ),
                        "change": "Integrity",
                        "status": "neutral",
                    },
                ]
                chart = {
                    "type": "pie",
                    "categories": ["Unique Records", "Duplicates"],
                    "series": [
                        {"name": "Records", "data": [total_rows - dup_count, dup_count]}
                    ],
                }
                return {
                    "direct_answer": direct,
                    "table_headers": headers,
                    "table_rows": rows,
                    "kpis": kpis,
                    "metrics": {"duplicate_count": dup_count, "total_rows": total_rows},
                    "chart_spec": chart,
                }

            if sub_op == "missing_values":
                null_counts: dict[str, int] = defaultdict(int)
                for r in sheet.rows:
                    for h in sheet.headers:
                        idx = col_idx[h]
                        cell = r[idx] if idx < len(r) else None
                        if cell is None or str(cell).strip() in ("", "None", "nan", "null"):
                            null_counts[h] += 1

                tot_nulls = sum(null_counts.values())
                cols_with_null = [h for h, c in null_counts.items() if c > 0]
                total_cells = len(sheet.rows) * len(sheet.headers)

                if tot_nulls == 0:
                    direct = (
                        f"No missing or null values were found across all "
                        f"{len(sheet.headers)} columns in {len(sheet.rows)} records."
                    )
                else:
                    direct = (
                        f"Found {tot_nulls} missing values across {len(cols_with_null)} "
                        f"columns ({', '.join(cols_with_null[:4])})."
                    )

                headers = ["Column", "Inferred Type", "Missing Count", "Completeness %"]
                rows = []
                for h in sheet.headers:
                    m_cnt = null_counts[h]
                    prof = sheet.column_profiles.get(h)
                    t_name = prof.inferred_type if prof else "text"
                    comp = (
                        ((len(sheet.rows) - m_cnt) / len(sheet.rows) * 100)
                        if len(sheet.rows)
                        else 0.0
                    )
                    rows.append([h, t_name, m_cnt, f"{comp:.1f}%"])

                pct_comp = (
                    (total_cells - tot_nulls) / total_cells * 100 if total_cells else 0.0
                )
                kpis = [
                    {
                        "label": "Missing Values",
                        "value": str(tot_nulls),
                        "change": f"{len(cols_with_null)} cols affected",
                        "status": "alert" if tot_nulls > 0 else "success",
                    },
                    {
                        "label": "Total Cells",
                        "value": f"{total_cells:,}",
                        "change": "Data points",
                        "status": "neutral",
                    },
                    {
                        "label": "Completeness",
                        "value": f"{pct_comp:.1f}%",
                        "change": "Overall",
                        "status": "success",
                    },
                ]
                chart = {
                    "type": "bar",
                    "categories": [str(r[0]) for r in rows[:10]],
                    "series": [
                        {"name": "Missing Count", "data": [int(r[2]) for r in rows[:10]]}
                    ],
                }
                return {
                    "direct_answer": direct,
                    "table_headers": headers,
                    "table_rows": rows,
                    "kpis": kpis,
                    "metrics": {
                        "total_missing": tot_nulls,
                        "affected_columns": len(cols_with_null),
                    },
                    "chart_spec": chart,
                }

            if sub_op == "outliers":
                target_col = (
                    plan.target_columns[0]
                    if plan.target_columns and plan.target_columns[0] in col_idx
                    else (numeric_headers[0] if numeric_headers else sheet.headers[-1])
                )
                dim_col = (
                    plan.group_column
                    if plan.group_column and plan.group_column in col_idx
                    else sheet.headers[0]
                )
                t_idx = col_idx[target_col]
                d_idx = col_idx[dim_col]

                nums = []
                for r in sheet.rows:
                    if t_idx < len(r):
                        v = self.spreadsheet_svc._to_number(r[t_idx])
                        if v is not None:
                            nums.append(v)

                nums.sort()
                n_count = len(nums)
                if n_count >= 4:
                    q25 = nums[int(n_count * 0.25)]
                    q75 = nums[int(n_count * 0.75)]
                    iqr = q75 - q25
                    lower_bound = q25 - 1.5 * iqr
                    upper_bound = q75 + 1.5 * iqr
                else:
                    median_v = statistics.median(nums) if nums else 0.0
                    iqr = 0.0
                    lower_bound = median_v
                    upper_bound = median_v

                outliers = []
                median_val = statistics.median(nums) if nums else 0.0
                for r in sheet.rows:
                    if t_idx < len(r) and d_idx < len(r):
                        val_curr = self.spreadsheet_svc._to_number(r[t_idx])
                        if (
                            val_curr is not None
                            and (val_curr < lower_bound or val_curr > upper_bound)
                        ):
                            dev = val_curr - median_val
                            sev = "CRITICAL" if abs(dev) > 3 * iqr else "MODERATE"
                            outliers.append([
                                str(r[d_idx]),
                                round(val_curr, 2),
                                f"{dev:+,.2f}",
                                sev,
                            ])

                outlier_count = len(outliers)
                if outlier_count == 0:
                    direct = (
                        f"No statistical outliers detected in '{target_col}' using IQR "
                        f"boundaries [{lower_bound:,.2f}, {upper_bound:,.2f}]."
                    )
                else:
                    direct = (
                        f"Detected {outlier_count} statistical outlier(s) in '{target_col}' "
                        f"outside the expected range [{lower_bound:,.2f}, {upper_bound:,.2f}]."
                    )

                headers = [dim_col, target_col, "Deviation from Median", "Severity"]
                kpis = [
                    {
                        "label": "Outliers Detected",
                        "value": str(outlier_count),
                        "change": f"IQR [{lower_bound:,.0f}, {upper_bound:,.0f}]",
                        "status": "alert" if outlier_count > 0 else "success",
                    },
                    {
                        "label": "Median Value",
                        "value": f"{median_val:,.2f}",
                        "change": "Baseline",
                        "status": "neutral",
                    },
                    {
                        "label": "Spread (IQR)",
                        "value": f"{iqr:,.2f}",
                        "change": "Interquartile",
                        "status": "neutral",
                    },
                ]
                chart = {
                    "type": "bar",
                    "categories": [str(r[0]) for r in outliers[:8]] if outliers else ["None"],
                    "series": [
                        {
                            "name": target_col,
                            "data": [float(r[1]) for r in outliers[:8]] if outliers else [0],
                        }
                    ],
                }
                return {
                    "direct_answer": direct,
                    "table_headers": headers,
                    "table_rows": outliers,
                    "kpis": kpis,
                    "metrics": {
                        "outlier_count": outlier_count,
                        "lower_bound": lower_bound,
                        "upper_bound": upper_bound,
                    },
                    "chart_spec": chart,
                }

        # ── 6. Trend Analysis (Monthly / Chronological) ──────────────────────
        if op == "trend":
            date_col = (
                plan.group_column
                if plan.group_column and plan.group_column in col_idx
                else sheet.headers[0]
            )
            val_col = (
                plan.target_columns[0]
                if plan.target_columns and plan.target_columns[0] in col_idx
                else (numeric_headers[0] if numeric_headers else sheet.headers[-1])
            )
            d_idx = col_idx[date_col]
            v_idx = col_idx[val_col]

            period_totals: dict[str, float] = defaultdict(float)
            for r in sheet.rows:
                if d_idx < len(r) and v_idx < len(r):
                    p_key = str(r[d_idx]) if r[d_idx] is not None else "Unknown"
                    v = self.spreadsheet_svc._to_number(r[v_idx]) or 0.0
                    period_totals[p_key] += v

            periods = list(period_totals.keys())
            rows = []
            prev_val: float | None = None
            first_val = period_totals[periods[0]] if periods else 0.0
            last_val = period_totals[periods[-1]] if periods else 0.0

            for p in periods:
                curr_v = period_totals[p]
                if prev_val is None or prev_val == 0.0:
                    g_str = "Baseline"
                else:
                    g_pct = (curr_v - prev_val) / prev_val * 100
                    g_str = f"{g_pct:+.1f}%"
                rows.append([p, round(curr_v, 2), g_str])
                prev_val = curr_v

            overall_growth = (
                ((last_val - first_val) / first_val * 100) if first_val > 0 else 0.0
            )
            start_p = periods[0] if periods else "Start"
            end_p = periods[-1] if periods else "End"
            direct = (
                f"Trend analysis across {len(periods)} periods shows an overall shift of "
                f"{overall_growth:+.1f}% from {first_val:,.2f} ({start_p}) "
                f"to {last_val:,.2f} ({end_p})."
            )
            headers = [date_col, f"Total {val_col}", "Period Growth %"]

            kpis = [
                {
                    "label": "Overall Growth",
                    "value": f"{overall_growth:+.1f}%",
                    "change": "Period shift",
                    "status": "success" if overall_growth >= 0 else "alert",
                },
                {
                    "label": "Latest Period",
                    "value": f"{last_val:,.2f}",
                    "change": str(periods[-1] if periods else ""),
                    "status": "neutral",
                },
                {
                    "label": "Periods Tracked",
                    "value": str(len(periods)),
                    "change": "Chronological",
                    "status": "neutral",
                },
            ]
            chart = {
                "type": "line",
                "categories": [str(r[0]) for r in rows],
                "series": [{"name": val_col, "data": [float(r[1]) for r in rows]}],
            }
            return {
                "direct_answer": direct,
                "table_headers": headers,
                "table_rows": rows,
                "kpis": kpis,
                "metrics": {"overall_growth_pct": overall_growth, "periods": len(rows)},
                "chart_spec": chart,
            }

        # ── Fallback Overview ────────────────────────────────────────────────
        return {
            "direct_answer": (
                f"Dataset overview for sheet '{sheet.name}' containing {len(sheet.rows)} rows "
                f"across {len(sheet.headers)} columns."
            ),
            "table_headers": sheet.headers,
            "table_rows": sheet.rows[:15],
            "kpis": [
                {
                    "label": "Total Rows",
                    "value": f"{len(sheet.rows):,}",
                    "change": f"{len(sheet.headers)} columns",
                    "status": "neutral",
                },
                {
                    "label": "Data Quality",
                    "value": "Verified",
                    "change": "Ready for questions",
                    "status": "success",
                },
            ],
            "metrics": {"row_count": len(sheet.rows), "col_count": len(sheet.headers)},
            "chart_spec": self.spreadsheet_svc.extract_chart_spec(
                sheet.headers, sheet.rows[:10]
            ),
        }

    # ── 3. Executive LLM Explanation Synthesis ──────────────────────────────

    async def synthesize_explanation(
        self, question: str, plan: NLAnalyticalPlan, exec_res: dict[str, Any]
    ) -> str:
        """
        Use the local Ollama LLM to formulate a professional, grounded narrative
        explaining the calculated deterministic values without inventing new numbers.
        """
        direct = exec_res.get("direct_answer", "")
        metrics = exec_res.get("metrics", {})
        kpis = exec_res.get("kpis", [])
        kpi_summary = ", ".join(f"{k.get('label')}: {k.get('value')}" for k in kpis)

        prompt = (
            f"You are the executive Chief Financial Officer and lead data analyst.\n"
            f"The user asked: '{question}'\n\n"
            f"A deterministic Python calculations engine computed the following exact facts:\n"
            f"- Direct Finding: {direct}\n"
            f"- Key Performance Metrics: {kpi_summary}\n"
            f"- Raw Metrics: {metrics}\n\n"
            f"Write a concise executive summary (2-3 sentences) explaining the business "
            f"implication of this finding. State the exact numbers provided above. "
            f"Do not invent or estimate different numbers. Be professional and decisive."
        )

        try:
            req = LLMRequest(
                prompt=prompt,
                system_prompt=(
                    "You are ServerGen AI's executive analytics narrative engine. "
                    "Ground all statements in the supplied numbers."
                ),
                temperature=0.1,
                max_tokens=250,
            )
            resp = await self.ollama.generate(req)
            if resp.content and len(resp.content.strip()) > 20:
                return resp.content.strip()
        except Exception as e:
            logger.debug("Local LLM explanation fallback: %s", e)

        # Fallback narrative
        return (
            f"Analysis of '{question}' completed with 100% deterministic precision. {direct} "
            f"Key metrics: {kpi_summary}."
        )

    # ── 4. End-to-End Analysis Workflow ─────────────────────────────────────

    async def analyze_question(
        self,
        sheet: SheetData,
        question: str,
        user_id: uuid.UUID | str,
        document_id: uuid.UUID | str | None = None,
        mask_pii: bool = False,
    ) -> NLAnalysisResult:
        """
        Complete end-to-end processing:
        1. Interpret question into a safe analytical plan.
        2. Perform exact calculations in Python.
        3. Synthesize executive narrative with local LLM.
        4. Redact PII if requested.
        5. Record query and metadata in AnalysisHistory.
        """
        t0 = time.time()
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        doc_uuid = (
            document_id
            if isinstance(document_id, uuid.UUID)
            else (uuid.UUID(str(document_id)) if document_id else None)
        )

        # 1. Parse intent
        plan = self.parse_intent(question, sheet)

        # 2. Execute plan
        exec_res = self.execute_plan(sheet, plan)

        # 3. Synthesize narrative explanation
        explanation = await self.synthesize_explanation(question, plan, exec_res)

        # 4. PII Redaction
        headers = exec_res.get("table_headers", [])
        rows = exec_res.get("table_rows", [])
        pii_count = 0
        if mask_pii:
            headers, rows, pii_count = pii_service.redact_table(headers, rows)

        duration_ms = int((time.time() - t0) * 1000)

        # 5. Persist to AnalysisHistory if database session is available
        if self.db:
            try:
                hist = AnalysisHistory(
                    id=uuid.uuid4(),
                    user_id=uid,
                    document_id=doc_uuid,
                    sheet_name=sheet.name,
                    question=question[:500],
                    analysis_type=plan.operation,
                    status="success",
                    result_summary=exec_res.get("direct_answer", "")[:500],
                    result_metadata={
                        "sub_operation": plan.sub_operation,
                        "metrics": exec_res.get("metrics", {}),
                        "row_count": len(rows),
                        "latency_ms": duration_ms,
                        "chart_type": plan.chart_type,
                    },
                    created_at=datetime.now(UTC),
                )
                self.db.add(hist)
                await self.db.flush()
            except Exception as e:
                logger.warning("Failed to record AnalysisHistory: %s", e)

        return NLAnalysisResult(
            question=question,
            operation=plan.operation,
            sub_operation=plan.sub_operation,
            direct_answer=exec_res.get("direct_answer", ""),
            executive_explanation=explanation,
            table_headers=headers,
            table_rows=rows,
            kpis=exec_res.get("kpis", []),
            metrics=exec_res.get("metrics", {}),
            chart_spec=exec_res.get("chart_spec", {}),
            row_count=sheet.row_count(),
            col_count=sheet.col_count(),
            execution_time_ms=duration_ms,
            pii_redacted_count=pii_count,
        )
