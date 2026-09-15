# Retrieves trusted Microsoft Content Database references by canonical ASIM schema and content type.
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from schema_utils import validate_document


SUPPORTED_CONTENT_TYPES = (
    "analyticRule",
    "huntingQuery",
    "workbook",
    "parser",
    "playbook",
)


def parse_arguments() -> argparse.Namespace:
    accelerator_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Retrieve Microsoft Content Database records by ASIM schema and content type."
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="Path to the JSONL Microsoft Content Database. Defaults to runtime, then the checked-in baseline.",
    )
    parser.add_argument(
        "--asim-schema",
        action="append",
        required=True,
        help="Canonical ASIM schema ID defined in database/taxonomy.yaml. Repeat to match multiple schemas.",
    )
    parser.add_argument(
        "--content-type",
        action="append",
        choices=SUPPORTED_CONTENT_TYPES,
        help="Content type to retrieve. Repeat to retrieve multiple types. Defaults to all types.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum number of records returned. Defaults to 12.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Defaults to standard output.",
    )
    return parser.parse_args()


def load_asim_schema_ids(taxonomy_path: Path) -> set[str]:
    with taxonomy_path.open(encoding="utf-8") as taxonomy_file:
        taxonomy = yaml.safe_load(taxonomy_file)
    if not isinstance(taxonomy, Mapping):
        raise ValueError(f"Expected a YAML mapping in {taxonomy_path}")

    schema_definitions = taxonomy.get("asimSchemas", [])
    if not isinstance(schema_definitions, list):
        raise ValueError("Expected asimSchemas to be a list in taxonomy.yaml")

    schema_ids = {
        schema["id"]
        for schema in schema_definitions
        if isinstance(schema, Mapping) and isinstance(schema.get("id"), str)
    }
    if not schema_ids:
        raise ValueError("No ASIM schema IDs were found in taxonomy.yaml")
    return schema_ids


def resolve_database_path(database_path: Path | None, accelerator_root: Path) -> Path:
    if database_path is not None:
        return database_path

    runtime_path = accelerator_root / "database" / "runtime" / "microsoft-content-database.jsonl"
    if runtime_path.is_file():
        return runtime_path
    return accelerator_root / "database" / "baseline" / "microsoft-content-database.jsonl"


def load_records(database_path: Path, record_schema_path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    invalid_lines = 0
    with database_path.open(encoding="utf-8") as database_file:
        for line_number, line in enumerate(database_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSONL at {database_path}:{line_number}: {error.msg}"
                ) from error
            if not isinstance(record, dict):
                invalid_lines += 1
                continue
            validate_document(record, record_schema_path, f"{database_path}:{line_number}")
            records.append(record)
    return records, invalid_lines


def is_microsoft_supported(record: Mapping[str, Any]) -> bool:
    solution = record.get("solution")
    return isinstance(solution, Mapping) and solution.get("supportTier") == "Microsoft"


def is_asim_schema_match(
    record: Mapping[str, Any], requested_schemas: set[str]
) -> bool:
    classification = record.get("classification")
    if not isinstance(classification, Mapping):
        return False

    record_schemas = classification.get("asimSchemas", [])
    if not isinstance(record_schemas, list):
        return False
    return bool(requested_schemas.intersection(record_schemas))



def record_sort_key(
    record: Mapping[str, Any], requested_schemas: set[str]
) -> tuple[int, int, int, str, str]:
    classification = record.get("classification")
    mapping_status = (
        classification.get("mappingStatus", "unmapped")
        if isinstance(classification, Mapping)
        else "unmapped"
    )
    mapping_status_order = {
        "explicit": 0,
        "inferredFromRepository": 1,
        "inferredFromOfficialProductDocumentation": 2,
        "inferredFromContent": 3,
        "ambiguous": 4,
        "unmapped": 5,
        "notApplicable": 6,
    }
    confidence = (
        classification.get("retrievalConfidence", "none")
        if isinstance(classification, Mapping)
        else "none"
    )
    confidence_order = {
        "exact": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "none": 4,
    }
    record_schemas = (
        classification.get("asimSchemas", [])
        if isinstance(classification, Mapping)
        else []
    )
    match_position = min(
        (
            index
            for index, schema_id in enumerate(record_schemas)
            if schema_id in requested_schemas
        ),
        default=99,
    )
    content = record.get("content")
    content_type = content.get("contentType", "") if isinstance(content, Mapping) else ""
    source_path = record.get("sourcePath", "")
    return (
        mapping_status_order.get(str(mapping_status), 99),
        confidence_order.get(str(confidence), 99),
        match_position,
        str(content_type).casefold(),
        str(source_path).casefold(),
    )


def build_result(
    database_path: Path,
    requested_asim_schemas: list[str],
    requested_content_types: list[str],
    records: list[dict[str, Any]],
    invalid_lines: int,
    limit: int,
) -> dict[str, Any]:
    selected_records: list[dict[str, Any]] = []
    matching_records = 0
    requested_schema_set = set(requested_asim_schemas)

    for record in records:
        if not is_microsoft_supported(record):
            continue
        content = record.get("content")
        if not isinstance(content, Mapping):
            continue
        if requested_content_types and content.get("contentType") not in requested_content_types:
            continue
        if not is_asim_schema_match(record, requested_schema_set):
            continue
        matching_records += 1
        selected_records.append(record)

    selected_records.sort(
        key=lambda record: record_sort_key(record, requested_schema_set)
    )
    returned_records = selected_records[:limit]
    return {
        "schemaVersion": 1,
        "databasePath": str(database_path),
        "asimSchemas": requested_asim_schemas,
        "contentTypes": requested_content_types or list(SUPPORTED_CONTENT_TYPES),
        "recordsRead": len(records),
        "invalidLinesSkipped": invalid_lines,
        "matchingRecords": matching_records,
        "returnedRecords": returned_records,
    }


def write_result(result: Mapping[str, Any], output_path: Path | None) -> None:
    serialized = json.dumps(result, indent=2, ensure_ascii=True)
    if output_path is None:
        print(serialized)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    arguments = parse_arguments()
    accelerator_root = Path(__file__).resolve().parents[1]
    taxonomy_path = accelerator_root / "database" / "taxonomy.yaml"
    record_schema_path = accelerator_root / "schemas" / "database-record.schema.json"
    database_path = resolve_database_path(arguments.database, accelerator_root)

    if arguments.limit < 1:
        print("--limit must be at least 1.", file=sys.stderr)
        return 2
    if not database_path.is_file():
        print(f"Database file does not exist: {database_path}", file=sys.stderr)
        return 2

    try:
        schema_ids = load_asim_schema_ids(taxonomy_path)
        requested_asim_schemas = list(dict.fromkeys(arguments.asim_schema))
        invalid_schemas = sorted(set(requested_asim_schemas).difference(schema_ids))
        if invalid_schemas:
            valid_schemas = ", ".join(sorted(schema_ids))
            raise ValueError(
                f"Unknown ASIM schema(s) {', '.join(invalid_schemas)}. Valid schemas: {valid_schemas}"
            )
        records, invalid_lines = load_records(database_path, record_schema_path)
        result = build_result(
            database_path,
            requested_asim_schemas,
            arguments.content_type or [],
            records,
            invalid_lines,
            arguments.limit,
        )
        write_result(result, arguments.output)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"Database query failed: {error}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())