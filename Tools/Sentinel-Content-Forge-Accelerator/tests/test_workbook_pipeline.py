from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ACCELERATOR_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = ACCELERATOR_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from workbook_pipeline import (
    enhance_workbook,
    inspect_workbook,
    review_visualizations,
    validate_workbook,
)


BASE_WORKBOOK = {
    "version": "Notebook/1.0",
    "items": [
        {
            "type": 1,
            "content": {"json": "# Network overview"},
            "name": "header",
        },
        {
            "type": 3,
            "content": {
                "version": "KqlItem/1.0",
                "query": "Example_CL\n| where TimeGenerated >= {TimeRange:start}\n| summarize count()",
                "queryType": 0,
                "resourceType": "microsoft.operationalinsights/workspaces",
                "visualization": "tiles",
            },
            "name": "event-count",
        },
    ],
    "fromTemplateId": "sentinel-NetworkOverview",
    "$schema": "https://github.com/Microsoft/Application-Insights-Workbooks/blob/master/schema/workbook.json",
}


class WorkbookPipelineTests(unittest.TestCase):
    def test_enhancement_adds_safe_defaults_without_changing_source(self) -> None:
        source = copy.deepcopy(BASE_WORKBOOK)

        enhanced, changes = enhance_workbook(source)

        self.assertNotIn("fallbackResourceIds", source)
        self.assertEqual([], enhanced["fallbackResourceIds"])
        self.assertEqual(["TimeRange"], inspect_workbook(enhanced)["parameterNames"])
        query_content = enhanced["items"][2]["content"]
        self.assertEqual("TimeRange", query_content["timeContextFromParameter"])
        self.assertEqual("info", query_content["noDataMessageStyle"])
        self.assertTrue(any(change["operation"] == "addGlobalTimeRange" for change in changes))
        self.assertEqual("passed", validate_workbook(enhanced)["status"])

    def test_validation_finds_unresolved_parameters_and_hardcoded_resource_ids(self) -> None:
        workbook, _ = enhance_workbook(BASE_WORKBOOK)
        workbook["items"][2]["content"]["query"] += (
            "\n| where Severity == '{Severity}'"
            "\n| extend Resource='/subscriptions/11111111-1111-1111-1111-111111111111/"
            "resourceGroups/example/providers/Microsoft.OperationalInsights/workspaces/example'"
        )

        report = validate_workbook(workbook)
        failed_ids = {
            check["id"] for check in report["checks"] if check["status"] == "failed"
        }

        self.assertEqual("failed", report["status"])
        self.assertIn("parameter.unresolved-references", failed_ids)
        self.assertIn("query.hardcoded-resource-id", failed_ids)

    def test_nested_group_queries_are_inspected_and_enhanced(self) -> None:
        workbook = copy.deepcopy(BASE_WORKBOOK)
        query_item = workbook["items"].pop()
        workbook["items"].append(
            {
                "type": 12,
                "content": {
                    "version": "NotebookGroup/1.0",
                    "items": [query_item],
                },
                "name": "details",
            }
        )

        enhanced, _ = enhance_workbook(workbook)

        self.assertEqual(1, inspect_workbook(enhanced)["queryCount"])
        nested_content = enhanced["items"][2]["content"]["items"][0]["content"]
        self.assertIn("noDataMessage", nested_content)

    def test_visualization_review_detects_render_and_setting_mismatches(self) -> None:
        workbook = copy.deepcopy(BASE_WORKBOOK)
        content = workbook["items"][1]["content"]
        content["title"] = "Event count"
        content["visualization"] = "table"
        content["tileSettings"] = {"showBorder": False}
        content["query"] += "\n| render timechart"

        report = review_visualizations(workbook)
        failed_ids = {
            check["id"] for check in report["checks"] if check["status"] == "failed"
        }

        self.assertEqual("failed", report["status"])
        self.assertIn("visualization.query-render-consistency", failed_ids)
        self.assertIn("visualization.settings-consistency", failed_ids)

    def test_visualization_review_warns_for_unformatted_table_only_workbook(self) -> None:
        workbook = copy.deepcopy(BASE_WORKBOOK)
        first_query = workbook["items"][1]
        first_query["content"]["visualization"] = "table"
        workbook["items"].append(copy.deepcopy(first_query))
        workbook["items"][2]["name"] = "event-details"

        report = review_visualizations(workbook)
        warning_ids = {
            check["id"] for check in report["checks"] if check["status"] == "warning"
        }

        self.assertEqual("passedWithWarnings", report["status"])
        self.assertIn("visualization.table-only-workbook", warning_ids)
        self.assertIn("visualization.formatting", warning_ids)
        self.assertIn("visualization.title", warning_ids)

    def test_visualization_review_accepts_mixed_formatted_visualizations(self) -> None:
        workbook = copy.deepcopy(BASE_WORKBOOK)
        tile_content = workbook["items"][1]["content"]
        tile_content["title"] = "Event count"
        tile_content["tileSettings"] = {"showBorder": False}
        trend_item = copy.deepcopy(workbook["items"][1])
        trend_item["name"] = "event-trend"
        trend_item["content"].update(
            {
                "title": "Events over time",
                "visualization": "timechart",
                "query": "Example_CL\n| summarize count() by bin(TimeGenerated, 1h)",
            }
        )
        trend_item["content"].pop("tileSettings")
        workbook["items"].append(trend_item)

        report = review_visualizations(workbook)

        self.assertEqual("passed", report["status"])

    def test_visualization_review_uses_kql_render_when_visualization_is_omitted(self) -> None:
        workbook = copy.deepcopy(BASE_WORKBOOK)
        content = workbook["items"][1]["content"]
        content.pop("visualization")
        content["title"] = "Events over time"
        content["query"] += "\n| render timechart"

        report = review_visualizations(workbook)
        failed_ids = {
            check["id"] for check in report["checks"] if check["status"] == "failed"
        }

        self.assertEqual("passed", report["status"])
        self.assertNotIn("visualization.query-render-consistency", failed_ids)
        self.assertEqual({"timechart": 1}, report["summary"]["visualizations"])


if __name__ == "__main__":
    unittest.main()