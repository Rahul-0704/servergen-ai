"""
ServerGen AI — Spreadsheet Analytics Controlled Tool.

Enables the AI Orchestrator to parse, profile, aggregate, filter, and extract
deep insights from enterprise Excel (.xlsx) and CSV spreadsheets.
"""

from __future__ import annotations

import logging
from typing import Any

from src.services.spreadsheet_service import SpreadsheetAnalyticsService
from src.tools.base import Tool, ToolMetadata, ToolResult

logger = logging.getLogger("servergen.tools.spreadsheet")


class SpreadsheetAnalyticsTool(Tool):
    """Controlled analytical tool for spreadsheets and multi-sheet workbooks."""

    def __init__(self, service: SpreadsheetAnalyticsService | None = None) -> None:
        self.service = service or SpreadsheetAnalyticsService()

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="spreadsheet_analytics",
            description="Perform deep tabular statistical analysis, grouped aggregations, and calculations on Excel (.xlsx) and CSV files",
            required_permission="ai.execute",
            potential_impact="low",
            allows_shell=False,
            allows_sql=False,
            allows_filesystem=False,
        )

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        file_path_str = str(parameters.get("file_path") or "").strip()
        raw_content = parameters.get("content")
        filename = str(parameters.get("filename") or "dataset.xlsx").strip()
        operation = str(parameters.get("operation") or "overview").lower()
        sheet_name = parameters.get("sheet_name")

        wb_data = None
        if raw_content and isinstance(raw_content, bytes):
            wb_data = self.service.parse_content(raw_content, filename)
        elif file_path_str:
            target = self.service.storage_dir / file_path_str
            if not target.exists():
                return ToolResult(
                    tool=self.metadata.name,
                    success=False,
                    error=f"Spreadsheet file '{file_path_str}' not found in storage.",
                )
            wb_data = self.service.parse_content(target.read_bytes(), target.name)
        else:
            return ToolResult(
                tool=self.metadata.name,
                success=False,
                error="Must provide either 'file_path' or raw 'content' bytes.",
            )

        target_sheet = (
            wb_data.sheets.get(sheet_name)
            if sheet_name and sheet_name in wb_data.sheets
            else wb_data.sheets[wb_data.sheet_names[0]]
        )

        try:
            if operation == "overview":
                table_md = self.service.generate_overview_markdown(target_sheet)
                insights = await self.service.generate_executive_insights(
                    target_sheet.name,
                    table_md,
                    f"Columns: {', '.join(target_sheet.headers)}",
                    user_prompt=parameters.get("prompt"),
                )
                output = f"{table_md}\n\n{insights}"
                return ToolResult(tool=self.metadata.name, success=True, output=output)

            elif operation == "groupby":
                group_col = str(parameters.get("group_column") or target_sheet.headers[0])
                aggs = parameters.get("aggregations") or [{"column": target_sheet.headers[-1], "op": "sum"}]
                out_headers, out_rows = self.service.group_by_aggregate(target_sheet, group_col, aggs)
                table_md = self.service.format_markdown_table(out_headers, out_rows)
                insights = await self.service.generate_executive_insights(
                    target_sheet.name,
                    f"Grouped by: {group_col}",
                    table_md,
                    user_prompt=parameters.get("prompt"),
                )
                output = f"### 📊 Grouped Aggregation ({group_col})\n\n{table_md}\n\n{insights}"
                return ToolResult(tool=self.metadata.name, success=True, output=output)

            elif operation == "filter":
                f_col = parameters.get("filter_column")
                f_op = parameters.get("operator", "==")
                f_val = parameters.get("filter_value")
                s_col = parameters.get("sort_column")
                asc = bool(parameters.get("ascending", False))
                out_headers, out_rows = self.service.filter_and_sort(
                    target_sheet,
                    filter_col=f_col,
                    operator=f_op,
                    filter_val=f_val,
                    sort_col=s_col,
                    ascending=asc,
                )
                table_md = self.service.format_markdown_table(out_headers, out_rows)
                output = f"### 🔍 Filtered Records ({len(out_rows)} matches)\n\n{table_md}"
                return ToolResult(tool=self.metadata.name, success=True, output=output)

            else:
                return ToolResult(
                    tool=self.metadata.name,
                    success=False,
                    error=f"Unsupported operation '{operation}'. Supported: 'overview', 'groupby', 'filter'.",
                )

        except Exception as exc:
            logger.error("Spreadsheet analytics tool error: %s", exc, exc_info=True)
            return ToolResult(tool=self.metadata.name, success=False, error=str(exc))
