# Statically validates staged Sentinel analytic rules, hunting queries, and workbooks and writes a review report.
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from schema_utils import validate_document


GUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
SEMANTIC_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
TECHNIQUE_PATTERN = re.compile(r"^T\d{4}(\.\d{3})?$")
TIMESPAN_PATTERN = re.compile(r"^(\d+)(ms|s|m|h|d|w)$", re.IGNORECASE)

VALID_SEVERITIES = {"Informational", "Low", "Medium", "High"}
VALID_STATUSES = {"Available", "InPreview", "Deprecated"}
VALID_TRIGGER_OPERATORS = {"gt", "lt", "eq"}
VALID_TACTICS = {
    "Reconnaissance",
    "ResourceDevelopment",
    "InitialAccess",
    "Execution",
    "Persistence",
    "PrivilegeEscalation",
    "DefenseEvasion",
    "CredentialAccess",
    "Discovery",
    "LateralMovement",
    "Collection",
    "CommandAndControl",
    "Exfiltration",
    "Impact",
}
VALID_ENTITY_TYPES = {
    "Account",
    "AzureResource",
    "CloudApplication",
    "DNS",
    "File",
    "FileHash",
    "Host",
    "IP",
    "IoTDevice",
    "Mailbox",
    "MailCluster",
    "MailMessage",
    "Malware",
    "Process",
    "RegistryKey",
    "RegistryValue",
    "SecurityGroup",
    "SentinelEntities",
    "SubmissionMail",
    "URL",
}
WORKBOOK_SCHEMA = (
    "https://github.com/Microsoft/Application-Insights-Workbooks/blob/master/schema/workbook.json"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate generated Microsoft Sentinel content and write a structured report."
    )
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        required=True,
        help="Generated content file or directory. Repeat to validate multiple paths.",
    )
    parser.add_argument(
        "--request",
        type=Path,
        help="Optional content request JSON used to validate connector and data-source dependencies.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="Path for the structured validation report JSON.",
    )
    return parser.parse_args()


def make_check(
    check_id: str,
    category: str,
    status: str,
    message: str,
    details: str | None = None,
    reference: str | None = None,
) -> dict[str, str]:
    check: dict[str, str] = {
        "id": check_id,
        "category": category,
        "status": status,
        "message": message,
    }
    if details:
        check["details"] = details
    if reference:
        check["reference"] = reference
    return check


def passed_check(check_id: str, category: str, message: str) -> dict[str, str]:
    return make_check(check_id, category, "passed", message)


def failed_check(
    check_id: str, category: str, message: str, details: str | None = None
) -> dict[str, str]:
    return make_check(check_id, category, "failed", message, details)


def warning_check(
    check_id: str, category: str, message: str, details: str | None = None
) -> dict[str, str]:
    return make_check(check_id, category, "warning", message, details)


def manual_review_check(
    check_id: str, message: str, details: str | None = None
) -> dict[str, str]:
    return make_check(check_id, "manualReview", "notRun", message, details)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source_file:
        loaded = json.load(source_file)
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return loaded


def load_content_request(path: Path) -> dict[str, Any]:
    request = load_json(path)
    accelerator_root = Path(__file__).resolve().parents[1]
    validate_document(
        request,
        accelerator_root / "schemas" / "content-request.schema.json",
        str(path),
    )
    connector = request.get("sourceBinding")
    if isinstance(connector, Mapping) and connector.get("status") == "unbound":
        return request
    if not isinstance(connector, Mapping):
        raise ValueError("The content request must contain a sourceBinding object.")
    connector_id = connector.get("connectorId")
    data_source = connector.get("dataSource")
    if not isinstance(connector_id, str) or not connector_id.strip():
        raise ValueError("The content request sourceBinding.connectorId must be a nonempty string.")
    if not isinstance(data_source, Mapping):
        raise ValueError("The content request sourceBinding.dataSource must be an object.")
    data_source_name = data_source.get("name")
    data_source_kind = data_source.get("kind")
    if not isinstance(data_source_name, str) or not data_source_name.strip():
        raise ValueError("The content request sourceBinding.dataSource.name must be a nonempty string.")
    if data_source_kind not in {"table", "parser"}:
        raise ValueError("The content request sourceBinding.dataSource.kind must be table or parser.")
    return request


def content_request_dependency(request: Mapping[str, Any] | None) -> tuple[str, str] | None:
    if request is None:
        return None
    connector = request["sourceBinding"]
    if connector["status"] == "unbound":
        return None
    data_source = connector["dataSource"]
    return str(connector["connectorId"]), str(data_source["name"])


def content_request_binding_status(request: Mapping[str, Any] | None) -> str | None:
    if request is None:
        return None
    return str(request["sourceBinding"]["status"])


def validate_source_binding(
    dependency: tuple[str, str] | None, binding_status: str | None
) -> dict[str, str]:
    if binding_status == "provided" and dependency:
        return passed_check(
            "dependency.source-binding",
            "dependency",
            "The content request includes a user-provided connector and data-source binding.",
        )
    if binding_status == "provisional" and dependency:
        connector_id, data_source_name = dependency
        return manual_review_check(
            "dependency.source-binding",
            "The content uses a provisional connector and data-source binding.",
            f"Confirm or replace connectorId={connector_id} and dataSource={data_source_name} before solution integration.",
        )
    return manual_review_check(
        "dependency.source-binding",
        "No connector ID or destination table or parser has been bound to this content.",
        "Classify and retrieve examples from sample data first, then provide or derive a binding before solution integration.",
    )


def find_content_files(paths: Iterable[Path]) -> list[Path]:
    content_files: set[Path] = set()
    allowed_extensions = {".yaml", ".yml", ".json"}

    for path in paths:
        if not path.exists():
            raise ValueError(f"Input path does not exist: {path}")
        if path.is_file():
            if path.suffix.lower() in allowed_extensions:
                content_files.add(path)
            continue
        for child_path in path.rglob("*"):
            if child_path.is_file() and child_path.suffix.lower() in allowed_extensions:
                content_files.add(child_path)

    return sorted(content_files, key=lambda content_path: content_path.as_posix().casefold())


def artifact_type_from_path(path: Path) -> str | None:
    parent_names = {parent.name.casefold() for parent in path.parents}
    if "analytic rules" in parent_names:
        return "analyticRule"
    if "hunting queries" in parent_names:
        return "huntingQuery"
    if "workbooks" in parent_names:
        return "workbook"
    return None


def read_artifact(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw_text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            content = yaml.safe_load(raw_text)
        else:
            content = json.loads(raw_text)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        return None, str(error)

    if not isinstance(content, dict):
        return None, "Content does not contain an object at its root."
    return content, None


def detect_artifact_type(path: Path, content: Mapping[str, Any] | None) -> str | None:
    path_type = artifact_type_from_path(path)
    if path_type:
        return path_type
    if content is None:
        return None
    if path.suffix.lower() in {".yaml", ".yml"}:
        if "severity" in content or "kind" in content:
            return "analyticRule"
        return "huntingQuery"
    if path.suffix.lower() == ".json" and (
        content.get("version") == "Notebook/1.0" or "$schema" in content
    ):
        return "workbook"
    return None


def validate_file_extension(path: Path, artifact_type: str) -> dict[str, str]:
    expected_extensions = {
        "analyticRule": {".yaml", ".yml"},
        "huntingQuery": {".yaml", ".yml"},
        "workbook": {".json"},
    }
    expected = expected_extensions[artifact_type]
    if path.suffix.lower() in expected:
        return passed_check(
            "structure.file-extension", "structure", "The artifact file extension matches its content type."
        )
    return failed_check(
        "structure.file-extension",
        "structure",
        f"{artifact_type} files must use one of: {', '.join(sorted(expected))}.",
    )


def require_fields(
    content: Mapping[str, Any], fields: Iterable[str], check_id: str = "structure.required-fields"
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    missing_fields = [field for field in fields if field not in content]
    if missing_fields:
        checks.append(
            failed_check(
                check_id,
                "structure",
                "Required fields are missing.",
                ", ".join(missing_fields),
            )
        )
    else:
        checks.append(
            passed_check(check_id, "structure", "All required fields are present.")
        )
    return checks


def validate_id(content: Mapping[str, Any]) -> dict[str, str]:
    value = content.get("id")
    if isinstance(value, str) and GUID_PATTERN.fullmatch(value):
        return passed_check("structure.id", "structure", "The ID is a valid GUID.")
    return failed_check("structure.id", "structure", "The ID must be a valid GUID.")


def validate_name(content: Mapping[str, Any]) -> dict[str, str]:
    value = content.get("name")
    if not isinstance(value, str) or not value.strip():
        return failed_check("structure.name", "structure", "The name must be a nonempty string.")
    if len(value) > 100:
        return failed_check("structure.name", "structure", "The name must be 100 characters or fewer.")
    if value.rstrip().endswith("."):
        return failed_check("structure.name", "structure", "The name must not end with a period.")
    return passed_check("structure.name", "structure", "The name has a valid format.")


def validate_description(content: Mapping[str, Any], artifact_type: str) -> dict[str, str]:
    value = content.get("description")
    if not isinstance(value, str) or not value.strip():
        return failed_check("structure.description", "structure", "The description must be a nonempty string.")
    if len(value) > 255:
        return failed_check("structure.description", "structure", "The description must be 255 characters or fewer.")
    if not value.isascii():
        return failed_check("structure.description", "structure", "The description must use ASCII characters only.")
    if artifact_type == "analyticRule" and not value.lstrip().startswith(
        ("This query searches for", "Identifies")
    ):
        return warning_check(
            "semantic.description-opening",
            "semantic",
            "The analytic rule description should begin with 'This query searches for' or 'Identifies'.",
        )
    return passed_check("structure.description", "structure", "The description has a valid format.")


def validate_semantic_version(content: Mapping[str, Any]) -> dict[str, str]:
    value = content.get("version")
    if isinstance(value, str) and SEMANTIC_VERSION_PATTERN.fullmatch(value):
        return passed_check("structure.version", "structure", "The version uses semantic versioning.")
    return failed_check("structure.version", "structure", "The version must use X.Y.Z semantic versioning.")


def validate_tactics(content: Mapping[str, Any]) -> list[dict[str, str]]:
    tactics = content.get("tactics")
    if not isinstance(tactics, list) or not tactics:
        return [failed_check("semantic.tactics", "semantic", "At least one MITRE tactic is required.")]
    invalid_tactics = [tactic for tactic in tactics if tactic not in VALID_TACTICS]
    checks: list[dict[str, str]] = []
    if len(tactics) > 5:
        checks.append(
            failed_check("semantic.tactics-count", "semantic", "A template can define at most five tactics.")
        )
    if invalid_tactics:
        checks.append(
            failed_check(
                "semantic.tactics-values",
                "semantic",
                "One or more MITRE tactics are invalid.",
                ", ".join(str(tactic) for tactic in invalid_tactics),
            )
        )
    if not checks:
        checks.append(passed_check("semantic.tactics", "semantic", "MITRE tactics are valid."))
    return checks


def validate_techniques(content: Mapping[str, Any]) -> list[dict[str, str]]:
    techniques = content.get("relevantTechniques")
    if not isinstance(techniques, list) or not techniques:
        return [
            failed_check(
                "semantic.techniques", "semantic", "At least one MITRE technique is required."
            )
        ]
    invalid_techniques = [
        technique
        for technique in techniques
        if not isinstance(technique, str) or not TECHNIQUE_PATTERN.fullmatch(technique)
    ]
    checks: list[dict[str, str]] = []
    if len(techniques) > 10:
        checks.append(
            failed_check(
                "semantic.techniques-count", "semantic", "A template can define at most ten techniques."
            )
        )
    if invalid_techniques:
        checks.append(
            failed_check(
                "semantic.techniques-values",
                "semantic",
                "One or more MITRE techniques have an invalid format.",
                ", ".join(str(technique) for technique in invalid_techniques),
            )
        )
    if not checks:
        checks.append(passed_check("semantic.techniques", "semantic", "MITRE technique formats are valid."))
    return checks


def validate_query(content: Mapping[str, Any], data_source_name: str | None) -> list[dict[str, str]]:
    query = content.get("query")
    if not isinstance(query, str) or not query.strip():
        return [failed_check("query.present", "query", "The KQL query must be a nonempty string.")]

    checks = [passed_check("query.present", "query", "The KQL query is present.")]
    if len(query) > 10000:
        checks.append(
            failed_check("query.length", "query", "The KQL query must not exceed 10,000 characters.")
        )
    else:
        checks.append(passed_check("query.length", "query", "The KQL query is within the character limit."))

    if data_source_name:
        if data_source_name in query:
            checks.append(
                passed_check(
                    "dependency.query-data-source",
                    "dependency",
                    "The KQL query references the requested data source.",
                )
            )
        else:
            checks.append(
                failed_check(
                    "dependency.query-data-source",
                    "dependency",
                    "The KQL query does not reference the requested data source.",
                    data_source_name,
                )
            )

    checks.append(
        manual_review_check(
            "query.execution",
            "KQL execution was not run by the static validator.",
            "Run the query against representative sample data or a test workspace before approval.",
        )
    )
    return checks


def validate_data_connectors(
    content: Mapping[str, Any], dependency: tuple[str, str] | None
) -> list[dict[str, str]]:
    connector_definitions = content.get("requiredDataConnectors")
    if not isinstance(connector_definitions, list):
        return [
            failed_check(
                "dependency.required-data-connectors",
                "dependency",
                "requiredDataConnectors must be an array.",
            )
        ]

    checks: list[dict[str, str]] = []
    malformed_definitions = []
    for connector_definition in connector_definitions:
        if not isinstance(connector_definition, Mapping):
            malformed_definitions.append("non-object connector entry")
            continue
        connector_id = connector_definition.get("connectorId")
        data_types = connector_definition.get("dataTypes")
        if not isinstance(connector_id, str) or not connector_id.strip():
            malformed_definitions.append("connectorId")
        if not isinstance(data_types, list) or not all(
            isinstance(data_type, str) and data_type.strip() for data_type in data_types
        ):
            malformed_definitions.append("dataTypes")

    if malformed_definitions:
        checks.append(
            failed_check(
                "dependency.required-data-connectors-format",
                "dependency",
                "One or more data connector dependency entries are malformed.",
                ", ".join(malformed_definitions),
            )
        )
    else:
        checks.append(
            passed_check(
                "dependency.required-data-connectors-format",
                "dependency",
                "Data connector dependency entries have a valid structure.",
            )
        )

    if dependency is None:
        return checks

    requested_connector_id, requested_data_source = dependency
    for connector_definition in connector_definitions:
        if not isinstance(connector_definition, Mapping):
            continue
        if connector_definition.get("connectorId") != requested_connector_id:
            continue
        data_types = connector_definition.get("dataTypes", [])
        if isinstance(data_types, list) and requested_data_source in data_types:
            checks.append(
                passed_check(
                    "dependency.requested-data-source",
                    "dependency",
                    "The requested connector and data source are declared as dependencies.",
                )
            )
            return checks

    checks.append(
        failed_check(
            "dependency.requested-data-source",
            "dependency",
            "The requested connector and data source are not declared together in requiredDataConnectors.",
            f"connectorId={requested_connector_id}; dataSource={requested_data_source}",
        )
    )
    return checks


def validate_entity_mappings(content: Mapping[str, Any]) -> list[dict[str, str]]:
    entity_mappings = content.get("entityMappings")
    query = content.get("query") if isinstance(content.get("query"), str) else ""
    if not isinstance(entity_mappings, list) or not entity_mappings:
        return [
            failed_check(
                "semantic.entity-mappings", "semantic", "At least one entity mapping is required."
            )
        ]

    checks: list[dict[str, str]] = []
    if len(entity_mappings) > 10:
        checks.append(
            failed_check(
                "semantic.entity-mappings-count",
                "semantic",
                "A template can define at most ten entity mappings.",
            )
        )

    invalid_entity_types: list[str] = []
    missing_field_mappings = False
    excessive_field_mappings = False
    missing_mapping_values = False
    missing_query_columns: list[str] = []

    for entity_mapping in entity_mappings:
        if not isinstance(entity_mapping, Mapping):
            invalid_entity_types.append("non-object entity mapping")
            continue
        entity_type = entity_mapping.get("entityType")
        if entity_type not in VALID_ENTITY_TYPES:
            invalid_entity_types.append(str(entity_type))
        field_mappings = entity_mapping.get("fieldMappings")
        if not isinstance(field_mappings, list) or not field_mappings:
            missing_field_mappings = True
            continue
        if len(field_mappings) > 3:
            excessive_field_mappings = True
        for field_mapping in field_mappings:
            if not isinstance(field_mapping, Mapping):
                missing_mapping_values = True
                continue
            identifier = field_mapping.get("identifier")
            column_name = field_mapping.get("columnName")
            if not isinstance(identifier, str) or not identifier.strip():
                missing_mapping_values = True
            if not isinstance(column_name, str) or not column_name.strip():
                missing_mapping_values = True
            elif column_name not in query:
                missing_query_columns.append(column_name)

    if invalid_entity_types:
        checks.append(
            failed_check(
                "semantic.entity-types",
                "semantic",
                "One or more entity mapping types are invalid.",
                ", ".join(invalid_entity_types),
            )
        )
    if missing_field_mappings:
        checks.append(
            failed_check(
                "semantic.entity-field-mappings",
                "semantic",
                "Each entity mapping must include at least one field mapping.",
            )
        )
    if excessive_field_mappings:
        checks.append(
            failed_check(
                "semantic.entity-field-mapping-count",
                "semantic",
                "Each entity mapping can define at most three field mappings.",
            )
        )
    if missing_mapping_values:
        checks.append(
            failed_check(
                "semantic.entity-field-mapping-values",
                "semantic",
                "Each entity field mapping requires a nonempty identifier and columnName.",
            )
        )
    if missing_query_columns:
        checks.append(
            failed_check(
                "query.entity-mapping-columns",
                "query",
                "One or more entity mapping columns are not referenced in the KQL query.",
                ", ".join(sorted(set(missing_query_columns))),
            )
        )
    if not checks:
        checks.append(
            passed_check(
                "semantic.entity-mappings", "semantic", "Entity mappings have a valid structure."
            )
        )
    return checks


def parse_timespan(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = TIMESPAN_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    magnitude = int(match.group(1))
    unit = match.group(2).lower()
    unit_milliseconds = {
        "ms": 1,
        "s": 1000,
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
        "w": 7 * 24 * 60 * 60 * 1000,
    }
    return magnitude * unit_milliseconds[unit]


def validate_analytic_schedule(content: Mapping[str, Any]) -> list[dict[str, str]]:
    kind = content.get("kind")
    if kind not in {"Scheduled", "NRT"}:
        return [
            failed_check(
                "structure.kind", "structure", "Analytic rule kind must be Scheduled or NRT."
            )
        ]

    checks = [passed_check("structure.kind", "structure", "Analytic rule kind is supported.")]
    if kind == "NRT":
        scheduled_fields = [
            field
            for field in ("queryFrequency", "queryPeriod", "triggerOperator", "triggerThreshold")
            if field in content
        ]
        if scheduled_fields:
            checks.append(
                warning_check(
                    "structure.nrt-scheduled-fields",
                    "structure",
                    "NRT rules should not define scheduled-rule fields.",
                    ", ".join(scheduled_fields),
                )
            )
        return checks

    schedule_fields = ("queryFrequency", "queryPeriod", "triggerOperator", "triggerThreshold")
    checks.extend(require_fields(content, schedule_fields, "structure.scheduled-fields"))
    frequency_milliseconds = parse_timespan(content.get("queryFrequency"))
    period_milliseconds = parse_timespan(content.get("queryPeriod"))
    if frequency_milliseconds is None:
        checks.append(
            failed_check(
                "structure.query-frequency", "structure", "queryFrequency must use KQL timespan format."
            )
        )
    if period_milliseconds is None:
        checks.append(
            failed_check(
                "structure.query-period", "structure", "queryPeriod must use KQL timespan format."
            )
        )
    if frequency_milliseconds is not None and period_milliseconds is not None:
        if frequency_milliseconds > period_milliseconds:
            checks.append(
                failed_check(
                    "semantic.schedule-order",
                    "semantic",
                    "queryFrequency must be less than or equal to queryPeriod.",
                )
            )
        elif period_milliseconds > 14 * 24 * 60 * 60 * 1000:
            checks.append(
                failed_check(
                    "semantic.query-period-limit",
                    "semantic",
                    "queryPeriod must not exceed 14 days.",
                )
            )
        else:
            checks.append(
                passed_check(
                    "semantic.schedule-order", "semantic", "The scheduled rule time range is valid."
                )
            )

    if content.get("triggerOperator") not in VALID_TRIGGER_OPERATORS:
        checks.append(
            failed_check(
                "structure.trigger-operator", "structure", "triggerOperator must be gt, lt, or eq."
            )
        )
    if not isinstance(content.get("triggerThreshold"), int) or not 0 <= content["triggerThreshold"] <= 10000:
        checks.append(
            failed_check(
                "structure.trigger-threshold",
                "structure",
                "triggerThreshold must be an integer from 0 through 10,000.",
            )
        )
    return checks


def validate_analytic_rule(
    content: Mapping[str, Any], dependency: tuple[str, str] | None
) -> list[dict[str, str]]:
    checks = require_fields(
        content,
        (
            "id",
            "name",
            "description",
            "severity",
            "status",
            "requiredDataConnectors",
            "tactics",
            "relevantTechniques",
            "query",
            "entityMappings",
            "version",
            "kind",
        ),
    )
    checks.extend([validate_id(content), validate_name(content), validate_description(content, "analyticRule")])
    if content.get("severity") in VALID_SEVERITIES:
        checks.append(passed_check("structure.severity", "structure", "The severity value is valid."))
    else:
        checks.append(
            failed_check(
                "structure.severity",
                "structure",
                "severity must be Informational, Low, Medium, or High.",
            )
        )
    if content.get("status") in VALID_STATUSES:
        checks.append(passed_check("structure.status", "structure", "The status value is valid."))
    else:
        checks.append(
            failed_check(
                "structure.status",
                "structure",
                "status must be Available, InPreview, or Deprecated.",
            )
        )
    checks.append(validate_semantic_version(content))
    checks.extend(validate_analytic_schedule(content))
    checks.extend(validate_data_connectors(content, dependency))
    checks.extend(validate_tactics(content))
    checks.extend(validate_techniques(content))
    data_source_name = dependency[1] if dependency else None
    checks.extend(validate_query(content, data_source_name))
    checks.extend(validate_entity_mappings(content))
    return checks


def validate_hunting_query(
    content: Mapping[str, Any], dependency: tuple[str, str] | None
) -> list[dict[str, str]]:
    checks = require_fields(
        content,
        (
            "id",
            "name",
            "description",
            "requiredDataConnectors",
            "tactics",
            "relevantTechniques",
            "query",
            "entityMappings",
            "version",
        ),
    )
    checks.extend([validate_id(content), validate_name(content), validate_description(content, "huntingQuery")])
    checks.append(validate_semantic_version(content))
    checks.extend(validate_data_connectors(content, dependency))
    checks.extend(validate_tactics(content))
    checks.extend(validate_techniques(content))
    data_source_name = dependency[1] if dependency else None
    checks.extend(validate_query(content, data_source_name))
    checks.extend(validate_entity_mappings(content))
    return checks


def find_query_strings(value: Any) -> list[str]:
    queries: list[str] = []
    if isinstance(value, Mapping):
        for key, child_value in value.items():
            if key == "query" and isinstance(child_value, str):
                queries.append(child_value)
            queries.extend(find_query_strings(child_value))
    elif isinstance(value, list):
        for child_value in value:
            queries.extend(find_query_strings(child_value))
    return queries


def validate_workbook(
    content: Mapping[str, Any], dependency: tuple[str, str] | None
) -> list[dict[str, str]]:
    checks = require_fields(content, ("version", "items", "fromTemplateId", "$schema"))
    if content.get("version") == "Notebook/1.0":
        checks.append(
            passed_check("structure.workbook-version", "structure", "The workbook version is valid.")
        )
    else:
        checks.append(
            failed_check(
                "structure.workbook-version", "structure", "Workbook version must be Notebook/1.0."
            )
        )

    items = content.get("items")
    if isinstance(items, list) and items:
        checks.append(passed_check("structure.workbook-items", "structure", "The workbook has items."))
    else:
        checks.append(
            failed_check("structure.workbook-items", "structure", "The workbook must contain at least one item.")
        )

    from_template_id = content.get("fromTemplateId")
    if isinstance(from_template_id, str) and from_template_id.startswith("sentinel-"):
        checks.append(
            passed_check(
                "structure.workbook-template-id", "structure", "The workbook template ID has the sentinel prefix."
            )
        )
    else:
        checks.append(
            failed_check(
                "structure.workbook-template-id",
                "structure",
                "fromTemplateId must begin with sentinel-.",
            )
        )

    if content.get("$schema") == WORKBOOK_SCHEMA:
        checks.append(
            passed_check("structure.workbook-schema", "structure", "The workbook schema is valid.")
        )
    else:
        checks.append(
            failed_check(
                "structure.workbook-schema", "structure", "The workbook schema URL is invalid."
            )
        )

    fallback_resource_ids = content.get("fallbackResourceIds")
    if fallback_resource_ids is not None and fallback_resource_ids != []:
        checks.append(
            failed_check(
                "structure.workbook-fallback-resource-ids",
                "structure",
                "fallbackResourceIds must be an empty array when present.",
            )
        )

    query_strings = find_query_strings(content.get("items", []))
    if dependency:
        _, data_source_name = dependency
        if any(data_source_name in query for query in query_strings):
            checks.append(
                passed_check(
                    "dependency.workbook-data-source",
                    "dependency",
                    "At least one workbook query references the requested data source.",
                )
            )
        else:
            checks.append(
                failed_check(
                    "dependency.workbook-data-source",
                    "dependency",
                    "No workbook query references the requested data source.",
                    data_source_name,
                )
            )

    if not query_strings:
        checks.append(
            warning_check(
                "query.workbook-queries",
                "query",
                "The workbook has no KQL query items to review.",
            )
        )
    else:
        checks.append(
            passed_check(
                "query.workbook-queries", "query", "The workbook includes KQL query items."
            )
        )
    checks.append(
        manual_review_check(
            "manual-review.workbook-rendering",
            "Workbook rendering and analyst usability were not evaluated by the static validator.",
            "Open the workbook in a test workspace and review parameters, visualizations, and no-data behavior.",
        )
    )
    return checks


def calculate_artifact_status(checks: Iterable[Mapping[str, Any]]) -> str:
    statuses = {check.get("status") for check in checks}
    if "failed" in statuses:
        return "failed"
    if "notRun" in statuses:
        return "needsReview"
    if "warning" in statuses:
        return "passedWithWarnings"
    return "passed"


def validate_artifact(
    path: Path, dependency: tuple[str, str] | None, binding_status: str | None = None
) -> dict[str, Any] | None:
    content, parse_error = read_artifact(path)
    artifact_type = detect_artifact_type(path, content)
    if artifact_type is None:
        return None

    checks = [
        validate_file_extension(path, artifact_type),
        validate_source_binding(dependency, binding_status),
    ]
    if parse_error:
        checks.append(
            failed_check(
                "structure.parse",
                "structure",
                "The artifact could not be parsed as YAML or JSON.",
                parse_error,
            )
        )
    elif artifact_type == "analyticRule":
        checks.extend(validate_analytic_rule(content, dependency))
    elif artifact_type == "huntingQuery":
        checks.extend(validate_hunting_query(content, dependency))
    else:
        checks.extend(validate_workbook(content, dependency))

    return {
        "path": path.as_posix(),
        "contentType": artifact_type,
        "status": calculate_artifact_status(checks),
        "checks": checks,
    }


def build_report(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    all_checks = [check for artifact in artifacts for check in artifact["checks"]]
    failed_checks = sum(check["status"] == "failed" for check in all_checks)
    warning_checks = sum(check["status"] == "warning" for check in all_checks)
    passed_checks = sum(check["status"] == "passed" for check in all_checks)
    not_run_checks = sum(check["status"] == "notRun" for check in all_checks)
    statuses = {artifact["status"] for artifact in artifacts}
    if "failed" in statuses:
        overall_status = "failed"
    elif "needsReview" in statuses:
        overall_status = "needsReview"
    elif "passedWithWarnings" in statuses:
        overall_status = "passedWithWarnings"
    else:
        overall_status = "passed"

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "overallStatus": overall_status,
        "summary": {
            "artifactsChecked": len(artifacts),
            "passedChecks": passed_checks,
            "warningChecks": warning_checks,
            "failedChecks": failed_checks,
            "notRunChecks": not_run_checks,
        },
        "artifacts": artifacts,
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    arguments = parse_arguments()
    try:
        request = load_content_request(arguments.request) if arguments.request else None
        dependency = content_request_dependency(request)
        binding_status = content_request_binding_status(request)
        content_files = find_content_files(arguments.input)
        artifacts = [
            artifact
            for content_file in content_files
            if (artifact := validate_artifact(content_file, dependency, binding_status)) is not None
        ]
        if not artifacts:
            raise ValueError("No supported analytic rule, hunting query, or workbook artifacts were found.")
        report = build_report(artifacts)
        write_report(arguments.report, report)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        print(f"Output validation failed: {error}", file=sys.stderr)
        return 2

    summary = report["summary"]
    print(
        f"Validation {report['overallStatus']}: {summary['artifactsChecked']} artifacts, "
        f"{summary['passedChecks']} passed checks, {summary['warningChecks']} warnings, "
        f"{summary['failedChecks']} failed checks, {summary['notRunChecks']} not run."
    )
    print(f"Report: {arguments.report}")
    return 1 if report["overallStatus"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())