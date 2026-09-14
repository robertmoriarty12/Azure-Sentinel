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
        description="Retrieve Microsoft Content Database records by category and content type."
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="Path to the JSONL Microsoft Content Database. Defaults to runtime, then the checked-in baseline.",
    )
    parser.add_argument(
        "--category",
        required=True,
        help="Category ID defined in database/taxonomy.yaml.",
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


def load_taxonomy_category_ids(taxonomy_path: Path) -> set[str]:
    with taxonomy_path.open(encoding="utf-8") as taxonomy_file:
        taxonomy = yaml.safe_load(taxonomy_file)
    if not isinstance(taxonomy, Mapping):
        raise ValueError(f"Expected a YAML mapping in {taxonomy_path}")

    categories = taxonomy.get("categories", [])
    if not isinstance(categories, list):
        raise ValueError("Expected categories to be a list in taxonomy.yaml")

    category_ids = {
        category["id"]
        for category in categories
        if isinstance(category, Mapping) and isinstance(category.get("id"), str)
    }
    unmatched_category = taxonomy.get("databaseCategorization", {}).get("unmatchedCategory")
    if isinstance(unmatched_category, str):
        category_ids.add(unmatched_category)
    return category_ids


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


def is_category_match(record: Mapping[str, Any], category: str) -> tuple[bool, bool]:
    classification = record.get("classification")
    if not isinstance(classification, Mapping):
        return False, False

    if classification.get("primaryCategory") == category:
        return True, True

    secondary_categories = classification.get("secondaryCategories", [])
    return isinstance(secondary_categories, list) and category in secondary_categories, False


def record_sort_key(record: Mapping[str, Any], is_primary_match: bool) -> tuple[int, str, str]:
    content = record.get("content")
    content_type = content.get("contentType", "") if isinstance(content, Mapping) else ""
    source_path = record.get("sourcePath", "")
    return (0 if is_primary_match else 1, str(content_type).casefold(), str(source_path).casefold())


def build_result(
    database_path: Path,
    category: str,
    requested_content_types: list[str],
    records: list[dict[str, Any]],
    invalid_lines: int,
    limit: int,
) -> dict[str, Any]:
    selected_records: list[tuple[dict[str, Any], bool]] = []
    matching_records = 0

    for record in records:
        if not is_microsoft_supported(record):
            continue
        content = record.get("content")
        if not isinstance(content, Mapping):
            continue
        if requested_content_types and content.get("contentType") not in requested_content_types:
            continue
        is_match, is_primary_match = is_category_match(record, category)
        if not is_match:
            continue
        matching_records += 1
        selected_records.append((record, is_primary_match))

    selected_records.sort(key=lambda item: record_sort_key(item[0], item[1]))
    returned_records = [record for record, _ in selected_records[:limit]]
    return {
        "schemaVersion": 1,
        "databasePath": str(database_path),
        "category": category,
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
        category_ids = load_taxonomy_category_ids(taxonomy_path)
        if arguments.category not in category_ids:
            valid_categories = ", ".join(sorted(category_ids))
            raise ValueError(
                f"Unknown category '{arguments.category}'. Valid categories: {valid_categories}"
            )
        records, invalid_lines = load_records(database_path, record_schema_path)
        result = build_result(
            database_path,
            arguments.category,
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