# Inspects, safely enhances, and statically reviews Microsoft Sentinel workbooks.
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


WORKBOOK_SCHEMA = (
    "https://github.com/Microsoft/Application-Insights-Workbooks/blob/master/schema/workbook.json"
)
WORKSPACE_RESOURCE_TYPE = "microsoft.operationalinsights/workspaces"
PARAMETER_REFERENCE_PATTERN = re.compile(r"\{([A-Za-z][A-Za-z0-9_-]*)(?::[^{}]+)?\}")
RESOURCE_ID_PATTERN = re.compile(
    r"/subscriptions/[0-9a-f-]{36}/resourceGroups/[^/]+/providers/",
    re.IGNORECASE,
)
RENDER_PATTERN = re.compile(r"\|\s*render\s+([A-Za-z][A-Za-z0-9]*)", re.IGNORECASE)
VALID_VISUALIZATIONS = {
    "areachart",
    "barchart",
    "bar",
    "categoricalbar",
    "columnchart",
    "grid",
    "linechart",
    "map",
    "piechart",
    "scatterchart",
    "table",
    "tiles",
    "timechart",
    "unstackedbar",
}
VISUALIZATION_SETTING_KEYS = {
    "table": {"gridSettings"},
    "grid": {"gridSettings"},
    "tiles": {"tileSettings"},
    "map": {"mapSettings"},
}
ALL_VISUALIZATION_SETTING_KEYS = set().union(*VISUALIZATION_SETTING_KEYS.values())


def load_workbook(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source_file:
        workbook = json.load(source_file)
    if not isinstance(workbook, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return workbook


def iter_items(items: object) -> Iterable[Mapping[str, Any]]:
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, Mapping):
            continue
        yield item
        content = item.get("content")
        if isinstance(content, Mapping):
            yield from iter_items(content.get("items"))


def query_items(workbook: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in iter_items(workbook.get("items")) if item.get("type") == 3]


def parameters(workbook: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for item in iter_items(workbook.get("items")):
        content = item.get("content")
        if item.get("type") != 9 or not isinstance(content, Mapping):
            continue
        item_parameters = content.get("parameters")
        if isinstance(item_parameters, list):
            result.extend(
                parameter for parameter in item_parameters if isinstance(parameter, Mapping)
            )
    return result


def effective_visualization(content: Mapping[str, Any]) -> str:
    visualization = content.get("visualization")
    if isinstance(visualization, str):
        return visualization.lower()
    if visualization is not None:
        return "invalid"
    query = content.get("query")
    render_match = RENDER_PATTERN.search(query) if isinstance(query, str) else None
    return render_match.group(1).lower() if render_match else "table"


def inspect_workbook(workbook: Mapping[str, Any]) -> dict[str, Any]:
    workbook_queries = query_items(workbook)
    workbook_parameters = parameters(workbook)
    visualizations: dict[str, int] = {}
    for item in workbook_queries:
        content = item.get("content")
        if not isinstance(content, Mapping):
            continue
        visualization = effective_visualization(content)
        visualizations[visualization] = visualizations.get(visualization, 0) + 1
    return {
        "itemCount": sum(1 for _ in iter_items(workbook.get("items"))),
        "queryCount": len(workbook_queries),
        "parameterNames": sorted(
            parameter["name"]
            for parameter in workbook_parameters
            if isinstance(parameter.get("name"), str)
        ),
        "visualizations": visualizations,
        "queriesWithoutNoDataMessage": sum(
            1
            for item in workbook_queries
            if isinstance(item.get("content"), Mapping)
            and not item["content"].get("noDataMessage")
        ),
    }


def make_check(
    check_id: str, status: str, message: str, item: str | None = None
) -> dict[str, str]:
    check = {"id": check_id, "status": status, "message": message}
    if item:
        check["item"] = item
    return check


def report_status(checks: Iterable[Mapping[str, str]]) -> str:
    statuses = {check.get("status") for check in checks}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "passedWithWarnings"
    return "passed"


def review_visualizations(workbook: Mapping[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    workbook_queries = query_items(workbook)
    visualizations: list[str] = []

    for index, item in enumerate(workbook_queries, start=1):
        item_name = item.get("name") if isinstance(item.get("name"), str) else f"query-{index}"
        content = item.get("content")
        if not isinstance(content, Mapping):
            checks.append(
                make_check(
                    "visualization.content",
                    "failed",
                    "Visualization content must be an object.",
                    item_name,
                )
            )
            continue

        visualization_value = content.get("visualization")
        visualization = effective_visualization(content)
        visualizations.append(visualization)
        checks.append(
            make_check(
                "visualization.supported-type",
                "passed" if visualization in VALID_VISUALIZATIONS else "failed",
                f"Visualization '{visualization}' must be a supported workbook visualization.",
                item_name,
            )
        )

        title = content.get("title")
        checks.append(
            make_check(
                "visualization.title",
                "passed" if isinstance(title, str) and bool(title.strip()) else "warning",
                "Query visualizations should have a descriptive title.",
                item_name,
            )
        )

        query = content.get("query")
        render_match = RENDER_PATTERN.search(query) if isinstance(query, str) else None
        if render_match and isinstance(visualization_value, str):
            rendered_visualization = render_match.group(1).lower()
            checks.append(
                make_check(
                    "visualization.query-render-consistency",
                    "passed" if rendered_visualization == visualization else "failed",
                    "The KQL render operator and workbook visualization must agree."
                    f" KQL renders '{rendered_visualization}', workbook uses '{visualization}'.",
                    item_name,
                )
            )

        expected_settings = VISUALIZATION_SETTING_KEYS.get(visualization)
        if expected_settings:
            has_expected_settings = any(key in content for key in expected_settings)
            has_table_export = visualization in {"table", "grid"} and (
                content.get("showExportToExcel") is True
                or content.get("exportToExcelOptions") == "visible"
            )
            checks.append(
                make_check(
                    "visualization.formatting",
                    "passed" if has_expected_settings or has_table_export else "warning",
                    f"The {visualization} visualization should define formatting or export settings.",
                    item_name,
                )
            )

        compatible_keys = VISUALIZATION_SETTING_KEYS.get(visualization, set())
        incompatible_keys = {
            key
            for key in ALL_VISUALIZATION_SETTING_KEYS - compatible_keys
            if key in content
        }
        checks.append(
            make_check(
                "visualization.settings-consistency",
                "failed" if incompatible_keys else "passed",
                "Visualization-specific settings must match the selected visualization."
                + (
                    f" Incompatible settings: {', '.join(sorted(incompatible_keys))}."
                    if incompatible_keys
                    else ""
                ),
                item_name,
            )
        )

    if not workbook_queries:
        checks.append(
            make_check(
                "visualization.present",
                "failed",
                "The workbook must contain at least one query visualization.",
            )
        )
    else:
        table_visualizations = {"table", "grid"}
        checks.append(
            make_check(
                "visualization.table-only-workbook",
                "warning"
                if len(workbook_queries) > 1
                and all(value in table_visualizations for value in visualizations)
                else "passed",
                "Workbooks with multiple query items should not rely entirely on tables.",
            )
        )

    return {
        "status": report_status(checks),
        "summary": {
            "queryCount": len(workbook_queries),
            "visualizations": inspect_workbook(workbook)["visualizations"],
            "distinctVisualizationCount": len(set(visualizations)),
        },
        "checks": checks,
        "manualReview": [
            "Confirm chart axes, legends, colors, labels, and density in a rendered workbook.",
            "Confirm each visualization communicates the intended analyst question.",
        ],
    }


def validate_workbook(workbook: Mapping[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    required_values = {
        "version": "Notebook/1.0",
        "$schema": WORKBOOK_SCHEMA,
    }
    for field, expected_value in required_values.items():
        status = "passed" if workbook.get(field) == expected_value else "failed"
        checks.append(
            make_check(
                f"structure.{field.lstrip('$')}",
                status,
                f"{field} must equal {expected_value}.",
            )
        )

    items = workbook.get("items")
    checks.append(
        make_check(
            "structure.items",
            "passed" if isinstance(items, list) and bool(items) else "failed",
            "The workbook must contain at least one item.",
        )
    )
    template_id = workbook.get("fromTemplateId")
    checks.append(
        make_check(
            "structure.template-id",
            "passed"
            if isinstance(template_id, str) and template_id.startswith("sentinel-")
            else "failed",
            "fromTemplateId must begin with sentinel-.",
        )
    )
    checks.append(
        make_check(
            "structure.fallback-resource-ids",
            "passed" if workbook.get("fallbackResourceIds") == [] else "failed",
            "fallbackResourceIds must be an empty array.",
        )
    )

    workbook_parameters = parameters(workbook)
    parameter_names = [
        parameter.get("name")
        for parameter in workbook_parameters
        if isinstance(parameter.get("name"), str)
    ]
    duplicate_parameters = sorted(
        {name for name in parameter_names if parameter_names.count(name) > 1}
    )
    checks.append(
        make_check(
            "parameter.duplicate-names",
            "failed" if duplicate_parameters else "passed",
            "Parameter names must be unique."
            + (f" Duplicates: {', '.join(duplicate_parameters)}." if duplicate_parameters else ""),
        )
    )
    time_ranges = [parameter for parameter in workbook_parameters if parameter.get("name") == "TimeRange"]
    checks.append(
        make_check(
            "parameter.time-range",
            "passed"
            if len(time_ranges) == 1
            and time_ranges[0].get("type") == 4
            and time_ranges[0].get("isRequired") is True
            else "failed",
            "A required type-4 TimeRange parameter must be defined exactly once.",
        )
    )

    workbook_queries = query_items(workbook)
    if not workbook_queries:
        checks.append(make_check("query.present", "failed", "The workbook must contain a query item."))
    referenced_parameters: set[str] = set()
    for index, item in enumerate(workbook_queries, start=1):
        item_name = item.get("name") if isinstance(item.get("name"), str) else f"query-{index}"
        content = item.get("content")
        if not isinstance(content, Mapping):
            checks.append(make_check("query.content", "failed", "Query content must be an object.", item_name))
            continue
        query = content.get("query")
        valid_shape = (
            content.get("version") == "KqlItem/1.0"
            and isinstance(query, str)
            and bool(query.strip())
            and content.get("queryType") == 0
            and content.get("resourceType") == WORKSPACE_RESOURCE_TYPE
        )
        checks.append(
            make_check(
                "query.shape",
                "passed" if valid_shape else "failed",
                "Query items require KqlItem/1.0, nonempty KQL, queryType 0, and the workspace resource type.",
                item_name,
            )
        )
        if isinstance(query, str):
            referenced_parameters.update(PARAMETER_REFERENCE_PATTERN.findall(query))
            if RESOURCE_ID_PATTERN.search(query):
                checks.append(
                    make_check(
                        "query.hardcoded-resource-id",
                        "failed",
                        "Query contains a hard-coded Azure resource ID.",
                        item_name,
                    )
                )
        checks.append(
            make_check(
                "query.no-data-message",
                "passed" if content.get("noDataMessage") else "warning",
                "Query should provide a useful no-data message.",
                item_name,
            )
        )

    unresolved = sorted(referenced_parameters - set(parameter_names))
    checks.append(
        make_check(
            "parameter.unresolved-references",
            "failed" if unresolved else "passed",
            "Every query parameter reference must resolve."
            + (f" Missing: {', '.join(unresolved)}." if unresolved else ""),
        )
    )
    return {
        "status": report_status(checks),
        "summary": inspect_workbook(workbook),
        "checks": checks,
    }


def make_time_range_item() -> dict[str, Any]:
    return {
        "type": 9,
        "content": {
            "version": "KqlParameterItem/1.0",
            "parameters": [
                {
                    "id": str(uuid.uuid4()),
                    "version": "KqlParameterItem/1.0",
                    "name": "TimeRange",
                    "label": "Time range",
                    "type": 4,
                    "isRequired": True,
                    "value": {"durationMs": 604800000},
                    "typeSettings": {
                        "selectableValues": [
                            {"durationMs": 86400000},
                            {"durationMs": 604800000},
                            {"durationMs": 2592000000},
                        ],
                        "allowCustom": True,
                    },
                }
            ],
            "style": "pills",
            "queryType": 0,
            "resourceType": WORKSPACE_RESOURCE_TYPE,
        },
        "name": "parameters",
    }


def enhance_workbook(workbook: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    enhanced = copy.deepcopy(dict(workbook))
    changes: list[dict[str, str]] = []
    if enhanced.get("fallbackResourceIds") is None:
        enhanced["fallbackResourceIds"] = []
        changes.append({"operation": "addFallbackResourceIds", "message": "Added empty fallbackResourceIds."})

    if not any(parameter.get("name") == "TimeRange" for parameter in parameters(enhanced)):
        items = enhanced.setdefault("items", [])
        if not isinstance(items, list):
            raise ValueError("The workbook items field must be an array before enhancement.")
        insertion_index = 1 if items and isinstance(items[0], Mapping) and items[0].get("type") == 1 else 0
        items.insert(insertion_index, make_time_range_item())
        changes.append({"operation": "addGlobalTimeRange", "message": "Added a required seven-day TimeRange parameter."})

    for index, item in enumerate(query_items(enhanced), start=1):
        content = item.get("content")
        if not isinstance(content, dict):
            continue
        item_name = item.get("name") if isinstance(item.get("name"), str) else f"query-{index}"
        if not content.get("noDataMessage"):
            content["noDataMessage"] = (
                "No data found for the selected time range and filters. Verify that data is flowing."
            )
            content["noDataMessageStyle"] = "info"
            changes.append({"operation": "addNoDataMessage", "item": item_name})
        if not content.get("timeContextFromParameter"):
            content["timeContextFromParameter"] = "TimeRange"
            changes.append({"operation": "linkTimeRange", "item": item_name})
    return enhanced, changes


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect, enhance, and validate Sentinel workbooks.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "review-visualizations", "validate"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--workbook", type=Path, required=True)
        command_parser.add_argument("--report", type=Path)
    enhance_parser = subparsers.add_parser("enhance")
    enhance_parser.add_argument("--workbook", type=Path, required=True)
    enhance_parser.add_argument("--output", type=Path, required=True)
    enhance_parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        workbook = load_workbook(arguments.workbook)
        if arguments.command == "inspect":
            result: dict[str, Any] = inspect_workbook(workbook)
        elif arguments.command == "review-visualizations":
            result = review_visualizations(workbook)
        elif arguments.command == "validate":
            result = validate_workbook(workbook)
        else:
            enhanced, changes = enhance_workbook(workbook)
            write_json(arguments.output, enhanced)
            result = {
                "status": validate_workbook(enhanced)["status"],
                "source": str(arguments.workbook),
                "output": str(arguments.output),
                "changes": changes,
                "validation": validate_workbook(enhanced),
            }
        if arguments.report:
            write_json(arguments.report, result)
        print(json.dumps(result, indent=2))
        return 1 if result.get("status") == "failed" else 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())