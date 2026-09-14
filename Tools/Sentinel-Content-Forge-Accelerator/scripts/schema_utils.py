from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def load_schema(schema_path: Path) -> dict[str, Any]:
    with schema_path.open(encoding="utf-8") as schema_file:
        schema = json.load(schema_file)
    if not isinstance(schema, dict):
        raise ValueError(f"Expected a JSON object in schema file {schema_path}")
    return schema


def format_validation_errors(errors: list[Any]) -> str:
    formatted_errors: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        formatted_errors.append(f"{location}: {error.message}")
    return "; ".join(formatted_errors)


def validate_document(
    document: Mapping[str, Any], schema_path: Path, document_name: str
) -> None:
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        raise ValueError(
            f"{document_name} does not match {schema_path.name}: "
            f"{format_validation_errors(errors)}"
        )