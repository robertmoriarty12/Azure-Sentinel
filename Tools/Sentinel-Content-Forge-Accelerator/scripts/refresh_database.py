# Builds an ASIM-indexed Microsoft Content Database from manifest-listed Microsoft-supported Sentinel solution assets.
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from schema_utils import validate_document


ASIM_FUNCTION_PATTERN = re.compile(r"\b_Im_[A-Za-z0-9_]+\b")
ASIM_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:_Im_|_ASim_|ASim|vim)[A-Za-z0-9_]+\b", re.IGNORECASE
)


def parse_arguments() -> argparse.Namespace:
    accelerator_root = Path(__file__).resolve().parents[1]
    default_repo_root = accelerator_root.parents[1]

    parser = argparse.ArgumentParser(
        description="Refresh the local Microsoft Content Database from a cloned Azure-Sentinel repository."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root,
        help="Path to the Azure-Sentinel repository root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional database output path. Defaults to database/runtime/microsoft-content-database.jsonl.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional refresh-report output path. Defaults to database/runtime/refresh-report.json.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source_file:
        loaded = yaml.safe_load(source_file)
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return loaded


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source_file:
        loaded = json.load(source_file)
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return loaded


def resolve_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def workspace_relative_path(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def unique_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized_value = value.strip()
        if normalized_value and normalized_value not in seen:
            seen.add(normalized_value)
            result.append(normalized_value)
    return result


def as_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return unique_strings([value])
    if isinstance(value, list):
        return unique_strings(value)
    return []


def collect_values_for_keys(value: Any, keys: set[str]) -> list[str]:
    collected: list[str] = []
    if isinstance(value, Mapping):
        for key, child_value in value.items():
            if key in keys:
                collected.extend(as_string_list(child_value))
            collected.extend(collect_values_for_keys(child_value, keys))
    elif isinstance(value, list):
        for child_value in value:
            collected.extend(collect_values_for_keys(child_value, keys))
    return unique_strings(collected)


def extract_required_data_connectors(content: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    connector_ids: list[str] = []
    data_types: list[str] = []
    connector_definitions = content.get("requiredDataConnectors", [])

    if not isinstance(connector_definitions, list):
        return connector_ids, data_types

    for connector_definition in connector_definitions:
        if not isinstance(connector_definition, Mapping):
            continue
        connector_ids.extend(as_string_list(connector_definition.get("connectorId")))
        data_types.extend(as_string_list(connector_definition.get("dataTypes")))

    return unique_strings(connector_ids), unique_strings(data_types)


def extract_entity_types(content: Mapping[str, Any]) -> list[str]:
    entity_mappings = content.get("entityMappings", [])
    if not isinstance(entity_mappings, list):
        return []
    return unique_strings(
        mapping.get("entityType")
        for mapping in entity_mappings
        if isinstance(mapping, Mapping)
    )


def extract_asim_functions(text: str) -> list[str]:
    return unique_strings(ASIM_FUNCTION_PATTERN.findall(text))


def normalize_asim_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def get_asim_schema_definitions(taxonomy: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    schema_definitions = taxonomy.get("asimSchemas", [])
    if not isinstance(schema_definitions, list):
        raise ValueError("Expected asimSchemas to be a list in taxonomy.yaml")

    valid_definitions: list[Mapping[str, Any]] = []
    schema_ids: set[str] = set()
    for definition in schema_definitions:
        if not isinstance(definition, Mapping):
            raise ValueError("Each ASIM schema definition must be a mapping")
        schema_id = definition.get("id")
        aliases = as_string_list(definition.get("aliases"))
        if not isinstance(schema_id, str) or not schema_id:
            raise ValueError("Each ASIM schema definition requires an id")
        if schema_id in schema_ids:
            raise ValueError(f"ASIM schema id is duplicated: {schema_id}")
        if not aliases:
            raise ValueError(f"ASIM schema {schema_id} requires at least one alias")
        schema_ids.add(schema_id)
        valid_definitions.append(definition)
    return valid_definitions


def find_asim_schema_ids(
    value: str, schema_definitions: Iterable[Mapping[str, Any]]
) -> list[str]:
    normalized_value = normalize_asim_value(value)
    if not normalized_value:
        return []

    matched_schema_ids: list[str] = []
    for definition in schema_definitions:
        schema_id = definition["id"]
        for alias in as_string_list(definition.get("aliases")):
            normalized_alias = normalize_asim_value(alias)
            parser_prefixes = (
                normalized_alias,
                f"im{normalized_alias}",
                f"asim{normalized_alias}",
                f"vim{normalized_alias}",
            )
            if any(
                normalized_value == prefix or normalized_value.startswith(prefix)
                for prefix in parser_prefixes
            ):
                matched_schema_ids.append(str(schema_id))
                break
    return unique_strings(matched_schema_ids)


def extract_identifier_values(text: str) -> list[str]:
    return unique_strings(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))


def find_exact_term_matches(values: Iterable[str], terms: Iterable[Any]) -> list[str]:
    normalized_values: dict[str, str] = {}
    for value in values:
        normalized_value = normalize_asim_value(value)
        if normalized_value and normalized_value not in normalized_values:
            normalized_values[normalized_value] = value

    matches: list[str] = []
    for term in as_string_list(list(terms)):
        normalized_term = normalize_asim_value(term)
        match = normalized_values.get(normalized_term)
        if match:
            matches.append(match)
    return unique_strings(matches)


def find_source_term_matches(values: Iterable[str], terms: Iterable[Any]) -> list[str]:
    normalized_values = [
        (value, normalize_asim_value(value))
        for value in values
        if normalize_asim_value(value)
    ]
    matches: list[str] = []
    for term in as_string_list(list(terms)):
        normalized_term = normalize_asim_value(term)
        if not normalized_term:
            continue
        for value, normalized_value in normalized_values:
            if normalized_value == normalized_term or (
                len(normalized_term) >= 5 and normalized_term in normalized_value
            ):
                matches.append(value)
                break
    return unique_strings(matches)


def find_text_term_matches(text: str, terms: Iterable[Any]) -> list[str]:
    normalized_text = normalize_asim_value(text)
    if not normalized_text:
        return []
    return unique_strings(
        term
        for term in as_string_list(list(terms))
        if normalize_asim_value(term) in normalized_text
    )


def inference_settings(taxonomy: Mapping[str, Any]) -> Mapping[str, Any]:
    settings = taxonomy.get("retrievalInference")
    if not isinstance(settings, Mapping):
        raise ValueError("taxonomy.yaml requires a retrievalInference mapping")
    scoring = settings.get("scoring")
    thresholds = settings.get("thresholds")
    if not isinstance(scoring, Mapping) or not isinstance(thresholds, Mapping):
        raise ValueError("retrievalInference requires scoring and thresholds mappings")
    return settings


def inference_weight(settings: Mapping[str, Any], name: str) -> int:
    scoring = settings["scoring"]
    value = scoring.get(name)
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"retrievalInference.scoring.{name} must be a positive integer")
    return value


def inference_threshold(settings: Mapping[str, Any], name: str) -> int:
    thresholds = settings["thresholds"]
    value = thresholds.get(name)
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"retrievalInference.thresholds.{name} must be a positive integer")
    return value


def build_inference_evidence(
    schema_id: str, source: str, values: Iterable[str]
) -> list[dict[str, str]]:
    return [
        {"schema": schema_id, "source": source, "value": value}
        for value in values
    ]


def infer_best_effort_classification(
    taxonomy: Mapping[str, Any],
    content_type: str,
    source_path: str,
    raw_content: str,
    content: Mapping[str, Any],
    connector_ids: Iterable[str],
    data_types: Iterable[str],
    metadata_domains: Iterable[str],
    entity_types: Iterable[str],
) -> dict[str, Any] | None:
    settings = inference_settings(taxonomy)
    maximum_matches = inference_weight(settings, "maximumMatchesPerSignal")
    identifier_values = extract_identifier_values(raw_content)
    title = first_string(content, ["name", "title", "fromTemplateId"], "")
    description = first_string(content, ["description"], "")
    source_name_values = unique_strings(
        [
            content.get("functionAlias"),
            content.get("displayName"),
            content.get("name"),
            content.get("title"),
            content.get("fromTemplateId"),
        ]
    )
    source_values = unique_strings(
        list(connector_ids) + list(data_types) + source_name_values + identifier_values
    )
    title_path_text = "\n".join((source_path, title))
    text = "\n".join((raw_content, title, description))
    scores: dict[str, int] = {}
    evidence_by_schema: dict[str, list[dict[str, str]]] = {}
    source_signal_by_schema: set[str] = set()

    signal_definitions = (
        ("sourceTerms", "sourceTerm", "sourceTerm", source_values, find_source_term_matches),
        ("fieldTerms", "fieldTerm", "fieldTerm", identifier_values, find_exact_term_matches),
        ("textTerms", "textTerm", "textTerm", text, find_text_term_matches),
        ("titlePathTerms", "titlePathTerm", "titlePathTerm", title_path_text, find_text_term_matches),
        ("entityTypes", "entityType", "entityType", entity_types, find_exact_term_matches),
    )

    for definition in get_asim_schema_definitions(taxonomy):
        schema_id = str(definition["id"])
        signals = definition.get("retrievalSignals", {})
        if not isinstance(signals, Mapping):
            continue

        score = 0
        evidence: list[dict[str, str]] = []
        for signal_key, weight_key, evidence_source, candidate_values, matcher in signal_definitions:
            configured_terms = as_string_list(signals.get(signal_key))
            if not configured_terms:
                continue
            matches = matcher(candidate_values, configured_terms)[:maximum_matches]
            if not matches:
                continue
            if signal_key == "entityTypes" and score == 0:
                continue
            score += inference_weight(settings, weight_key) * len(matches)
            evidence.extend(build_inference_evidence(schema_id, evidence_source, matches))
            if signal_key == "sourceTerms":
                source_signal_by_schema.add(schema_id)

        if score:
            scores[schema_id] = score
            evidence_by_schema[schema_id] = unique_asim_evidence(evidence)

    if scores:
        ranked_schemas = sorted(scores, key=lambda schema_id: (-scores[schema_id], schema_id))
        primary_schema = ranked_schemas[0]
        primary_score = scores[primary_schema]
        selected_schemas = [primary_schema]
        for schema_id in ranked_schemas[1:]:
            if len(selected_schemas) >= inference_threshold(settings, "maximumSchemas"):
                break
            if scores[schema_id] < inference_threshold(settings, "secondaryMinimumScore"):
                continue
            if primary_score - scores[schema_id] > inference_threshold(
                settings, "secondaryMaximumDifference"
            ):
                continue
            selected_schemas.append(schema_id)

        if primary_score >= inference_threshold(settings, "highScore"):
            confidence = "high"
        elif primary_score >= inference_threshold(settings, "mediumScore"):
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "asimSchemas": selected_schemas,
            "asimEvidence": unique_asim_evidence(
                evidence
                for schema_id in selected_schemas
                for evidence in evidence_by_schema[schema_id]
            ),
            "mappingStatus": "inferredFromContent",
            "retrievalConfidence": confidence,
        }

    metadata_fallbacks = settings.get("metadataDomainFallbacks", {})
    if not isinstance(metadata_fallbacks, Mapping):
        raise ValueError("retrievalInference.metadataDomainFallbacks must be a mapping")
    normalized_domain_fallbacks = {
        normalize_asim_value(str(domain)): str(schema_id)
        for domain, schema_id in metadata_fallbacks.items()
        if isinstance(domain, str) and isinstance(schema_id, str)
    }
    for metadata_domain in as_string_list(list(metadata_domains)):
        schema_id = normalized_domain_fallbacks.get(normalize_asim_value(metadata_domain))
        if schema_id:
            return {
                "asimSchemas": [schema_id],
                "asimEvidence": build_inference_evidence(
                    schema_id, "metadataDomain", [metadata_domain]
                ),
                "mappingStatus": "inferredFromContent",
                "retrievalConfidence": "low",
            }

    content_type_fallbacks = settings.get("contentTypeFallbacks", {})
    if not isinstance(content_type_fallbacks, Mapping):
        raise ValueError("retrievalInference.contentTypeFallbacks must be a mapping")
    schema_id = content_type_fallbacks.get(content_type)
    if isinstance(schema_id, str) and schema_id:
        return {
            "asimSchemas": [schema_id],
            "asimEvidence": build_inference_evidence(
                schema_id, "contentTypeFallback", [content_type]
            ),
            "mappingStatus": "inferredFromContent",
            "retrievalConfidence": "low",
        }
    return None


def extract_asim_schema_tag_values(value: Any) -> list[str]:
    tag_values: list[str] = []
    if isinstance(value, Mapping):
        for key, child_value in value.items():
            if isinstance(key, str) and key.casefold() == "schema":
                tag_values.extend(as_string_list(child_value))
            tag_values.extend(extract_asim_schema_tag_values(child_value))
    elif isinstance(value, list):
        for child_value in value:
            tag_values.extend(extract_asim_schema_tag_values(child_value))
    return unique_strings(tag_values)


def unique_asim_evidence(evidence: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    unique_evidence: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in evidence:
        schema_id = item.get("schema", "")
        source = item.get("source", "")
        value = item.get("value", "")
        key = (schema_id, source, value)
        if all(key) and key not in seen:
            seen.add(key)
            unique_evidence.append(
                {"schema": schema_id, "source": source, "value": value}
            )
    return unique_evidence


def extract_asim_evidence(
    taxonomy: Mapping[str, Any], content: Mapping[str, Any], raw_content: str, content_path: Path
) -> list[dict[str, str]]:
    schema_definitions = get_asim_schema_definitions(taxonomy)
    evidence: list[dict[str, str]] = []

    for identifier in unique_strings(ASIM_IDENTIFIER_PATTERN.findall(raw_content)):
        for schema_id in find_asim_schema_ids(identifier, schema_definitions):
            evidence.append(
                {
                    "schema": schema_id,
                    "source": "parserReference",
                    "value": identifier,
                }
            )

    for tag_value in extract_asim_schema_tag_values(content):
        for schema_id in find_asim_schema_ids(tag_value, schema_definitions):
            evidence.append(
                {
                    "schema": schema_id,
                    "source": "schemaTag",
                    "value": tag_value,
                }
            )

    parser_name_candidates = [
        content_path.stem,
        content.get("name"),
        content.get("functionAlias"),
        content.get("displayName"),
    ]
    for parser_name in unique_strings(parser_name_candidates):
        normalized_name = normalize_asim_value(parser_name)
        if not normalized_name.startswith(("asim", "vim", "im")):
            continue
        for schema_id in find_asim_schema_ids(parser_name, schema_definitions):
            evidence.append(
                {
                    "schema": schema_id,
                    "source": "parserName",
                    "value": parser_name,
                }
            )

    return unique_asim_evidence(evidence)


def load_asim_mapping_registry(
    registry_path: Path, taxonomy: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    registry = load_yaml(registry_path)
    if registry.get("version") != 1:
        raise ValueError("ASIM mapping registry version must be 1")

    mappings = registry.get("mappings", [])
    if not isinstance(mappings, list):
        raise ValueError("ASIM mapping registry mappings must be a list")

    schema_ids = {
        definition["id"] for definition in get_asim_schema_definitions(taxonomy)
    }
    valid_statuses = {
        "inferredFromRepository",
        "inferredFromOfficialProductDocumentation",
    }
    mapping_ids: set[str] = set()
    approved_mappings: list[Mapping[str, Any]] = []

    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            raise ValueError("Each ASIM mapping registry entry must be a mapping")
        mapping_id = mapping.get("id")
        if not isinstance(mapping_id, str) or not mapping_id:
            raise ValueError("Each ASIM mapping registry entry requires an id")
        if mapping_id in mapping_ids:
            raise ValueError(f"ASIM mapping registry id is duplicated: {mapping_id}")
        mapping_ids.add(mapping_id)

        if mapping.get("reviewState") != "approved":
            continue
        if mapping.get("mappingStatus") not in valid_statuses:
            raise ValueError(f"ASIM mapping {mapping_id} has an invalid mappingStatus")

        mapped_schemas = as_string_list(mapping.get("asimSchemas"))
        if not mapped_schemas or any(schema not in schema_ids for schema in mapped_schemas):
            raise ValueError(f"ASIM mapping {mapping_id} references an invalid schema")

        match = mapping.get("match")
        if not isinstance(match, Mapping):
            raise ValueError(f"ASIM mapping {mapping_id} requires a match mapping")
        for match_key in ("solutionPaths", "contentTypes", "requiredText"):
            if not as_string_list(match.get(match_key)):
                raise ValueError(f"ASIM mapping {mapping_id} requires match.{match_key}")

        evidence = mapping.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"ASIM mapping {mapping_id} requires evidence")
        approved_mappings.append(mapping)

    return approved_mappings


def mapping_matches_artifact(
    mapping: Mapping[str, Any], source_path: str, content_type: str, raw_content: str
) -> bool:
    match = mapping["match"]
    source_path_key = source_path.casefold()
    normalized_solution_paths = [
        solution_path.rstrip("/").casefold()
        for solution_path in as_string_list(match.get("solutionPaths"))
    ]
    if not any(
        source_path_key == solution_path
        or source_path_key.startswith(f"{solution_path}/")
        for solution_path in normalized_solution_paths
    ):
        return False

    if content_type not in as_string_list(match.get("contentTypes")):
        return False

    content_key = raw_content.casefold()
    return all(
        required_text.casefold() in content_key
        for required_text in as_string_list(match.get("requiredText"))
    )


def extract_mapping_registry_evidence(
    mappings: Iterable[Mapping[str, Any]], source_path: str, content_type: str, raw_content: str
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for mapping in mappings:
        if not mapping_matches_artifact(mapping, source_path, content_type, raw_content):
            continue
        for schema_id in as_string_list(mapping.get("asimSchemas")):
            evidence.append(
                {
                    "schema": schema_id,
                    "source": "mappingRegistry",
                    "value": str(mapping["id"]),
                }
            )
    return unique_asim_evidence(evidence)


def read_content(path: Path) -> tuple[dict[str, Any], str, str | None]:
    raw_content = path.read_text(encoding="utf-8", errors="replace")
    extension = path.suffix.lower()

    try:
        if extension in {".yaml", ".yml"}:
            parsed_content = yaml.safe_load(raw_content)
        elif extension == ".json":
            parsed_content = json.loads(raw_content)
        else:
            parsed_content = {}
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        return {}, raw_content, str(error)

    if not isinstance(parsed_content, dict):
        return {}, raw_content, "Content does not contain an object at its root."

    return parsed_content, raw_content, None


def first_string(content: Mapping[str, Any], keys: Iterable[str], fallback: str) -> str:
    for key in keys:
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def classify_record(
    content_type: str,
    direct_evidence: list[dict[str, str]],
    mapping_evidence: list[dict[str, str]],
    mapping_registry: Iterable[Mapping[str, Any]],
    best_effort_classification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if content_type == "playbook":
        return {
            "asimSchemas": [],
            "asimEvidence": [],
            "mappingStatus": "notApplicable",
            "retrievalConfidence": "none",
        }

    direct_schemas = unique_strings(item["schema"] for item in direct_evidence)
    if direct_schemas:
        return {
            "asimSchemas": direct_schemas,
            "asimEvidence": direct_evidence,
            "mappingStatus": "explicit",
            "retrievalConfidence": "exact",
        }

    inferred_schemas = unique_strings(item["schema"] for item in mapping_evidence)
    if inferred_schemas:
        mapping_status_by_id = {
            str(mapping["id"]): str(mapping["mappingStatus"])
            for mapping in mapping_registry
        }
        inferred_statuses = unique_strings(
            mapping_status_by_id.get(item["value"], "")
            for item in mapping_evidence
        )
        if len(inferred_schemas) == 1 and len(inferred_statuses) == 1:
            return {
                "asimSchemas": inferred_schemas,
                "asimEvidence": mapping_evidence,
                "mappingStatus": inferred_statuses[0],
                "retrievalConfidence": "high",
            }
        return {
            "asimSchemas": inferred_schemas,
            "asimEvidence": mapping_evidence,
            "mappingStatus": "ambiguous",
            "retrievalConfidence": "medium",
        }

    if best_effort_classification is not None:
        return dict(best_effort_classification)

    return {
        "asimSchemas": [],
        "asimEvidence": [],
        "mappingStatus": "unmapped",
        "retrievalConfidence": "none",
    }


def resolve_manifest_file(
    repo_root: Path, solutions_root: Path, solution_directory: Path, manifest_value: str
) -> Path | None:
    normalized_value = manifest_value.strip().lstrip("/\\").replace("\\", "/")
    path_parts = [part for part in normalized_value.split("/") if part not in {"", "."}]
    if not path_parts:
        return None
    manifest_path = Path(*path_parts)

    candidates = [
        solution_directory / manifest_path,
        solutions_root / manifest_path,
        repo_root / manifest_path,
    ]

    for candidate in candidates:
        resolved_candidate = candidate.resolve()
        try:
            resolved_candidate.relative_to(solutions_root.resolve())
        except ValueError:
            continue
        if resolved_candidate.is_file():
            return resolved_candidate

    return None


def find_manifest_paths(
    solution_directory: Path, manifest_directory_name: str, manifest_prefix: str, manifest_suffix: str
) -> list[Path]:
    manifest_directories = [
        directory
        for directory in solution_directory.iterdir()
        if directory.is_dir() and directory.name.casefold() == manifest_directory_name.casefold()
    ]
    manifest_paths = [
        path
        for manifest_directory in manifest_directories
        for path in manifest_directory.iterdir()
        if path.is_file()
        and path.name.casefold().startswith(manifest_prefix.casefold())
        and path.name.casefold().endswith(manifest_suffix.casefold())
    ]
    return sorted(manifest_paths, key=lambda path: path.as_posix().casefold())


def get_manifest_values(manifest: Mapping[str, Any], manifest_key: str) -> Any:
    if manifest_key in manifest:
        return manifest[manifest_key]

    normalized_manifest_key = manifest_key.casefold()
    for key, value in manifest.items():
        if isinstance(key, str) and key.casefold() == normalized_manifest_key:
            return value
    return []


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_record(
    repo_root: Path,
    metadata_path: Path,
    manifest_path: Path,
    content_path: Path,
    metadata: Mapping[str, Any],
    manifest: Mapping[str, Any],
    content_type: str,
    manifest_key: str,
    taxonomy: Mapping[str, Any],
    mapping_registry: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    parsed_content, raw_content, parse_warning = read_content(content_path)
    connector_ids, data_types = extract_required_data_connectors(parsed_content)
    connector_ids.extend(
        collect_values_for_keys(parsed_content, {"dataConnectorsDependencies"})
    )
    data_types.extend(collect_values_for_keys(parsed_content, {"dataTypesDependencies"}))

    source_path = workspace_relative_path(repo_root, content_path)
    asim_functions = extract_asim_functions(raw_content)
    direct_asim_evidence = extract_asim_evidence(
        taxonomy, parsed_content, raw_content, content_path
    )
    mapping_registry_evidence = extract_mapping_registry_evidence(
        mapping_registry, source_path, content_type, raw_content
    )
    metadata_domains = as_string_list(metadata.get("categories", {}).get("domains"))
    entity_types = extract_entity_types(parsed_content)
    best_effort_classification = infer_best_effort_classification(
        taxonomy,
        content_type,
        source_path,
        raw_content,
        parsed_content,
        connector_ids,
        data_types,
        metadata_domains,
        entity_types,
    )
    classification = classify_record(
        content_type,
        direct_asim_evidence,
        mapping_registry_evidence,
        mapping_registry,
        best_effort_classification,
    )

    support = metadata.get("support", {})
    if not isinstance(support, Mapping):
        support = {}

    record = {
        "schemaVersion": 1,
        "sourcePath": source_path,
        "sourceHash": source_hash(content_path),
        "solution": {
            "name": first_string(manifest, ["Name"], content_path.parent.name),
            "folderPath": workspace_relative_path(repo_root, metadata_path.parent),
            "metadataPath": workspace_relative_path(repo_root, metadata_path),
            "manifestPath": workspace_relative_path(repo_root, manifest_path),
            "publisherId": first_string(metadata, ["publisherId"], "unknown"),
            "offerId": first_string(metadata, ["offerId"], "unknown"),
            "providers": as_string_list(metadata.get("providers")),
            "supportTier": "Microsoft",
            "metadataDomains": metadata_domains,
        },
        "content": {
            "contentType": content_type,
            "manifestKey": manifest_key,
            "fileExtension": content_path.suffix.lower(),
            "title": first_string(parsed_content, ["name", "title", "fromTemplateId"], content_path.stem),
            "description": first_string(parsed_content, ["description"], ""),
            "connectorIds": unique_strings(connector_ids),
            "dataTypes": unique_strings(data_types),
            "asimFunctions": asim_functions,
            "tactics": as_string_list(parsed_content.get("tactics")),
            "techniques": as_string_list(parsed_content.get("relevantTechniques")),
            "entityTypes": entity_types,
        },
        "classification": {
            "taxonomyVersion": int(taxonomy["version"]),
            **classification,
        },
    }
    return record, parse_warning


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as destination_file:
        json.dump(value, destination_file, indent=2, ensure_ascii=True)
        destination_file.write("\n")
    temporary_path.replace(path)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as destination_file:
        for record in records:
            destination_file.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            destination_file.write("\n")
    temporary_path.replace(path)


def refresh_database(
    repo_root: Path,
    output_path: Path,
    report_path: Path,
    policy: Mapping[str, Any],
    taxonomy: Mapping[str, Any],
    mapping_registry: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    accelerator_root = Path(__file__).resolve().parents[1]
    record_schema_path = accelerator_root / "schemas" / "database-record.schema.json"
    database_settings = policy["database"]
    selection_settings = policy["selection"]
    content_types = policy["contentTypes"]
    source_root = str(database_settings["sourceRoot"])
    solutions_root = repo_root / source_root

    if not solutions_root.is_dir():
        raise ValueError(f"Solutions directory does not exist: {solutions_root}")

    metadata_file_name = str(selection_settings["metadataFileName"])
    manifest_directory_name = str(selection_settings["manifestDirectory"])
    manifest_prefix = str(selection_settings["manifestFilePrefix"])
    manifest_suffix = str(selection_settings["manifestFileSuffix"])
    required_support_tier = str(selection_settings["supportTier"])
    approved_mappings = mapping_registry if mapping_registry is not None else []

    statistics = {
        "solutionMetadataFilesScanned": 0,
        "microsoftSupportedSolutions": 0,
        "nonMicrosoftSupportedSolutions": 0,
        "manifestsRead": 0,
        "artifactsIndexed": 0,
        "missingArtifacts": 0,
        "duplicateArtifacts": 0,
        "contentParseWarnings": 0,
        "errors": 0,
    }
    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    records_by_path: dict[str, dict[str, Any]] = {}

    metadata_paths = sorted(solutions_root.glob(f"*/{metadata_file_name}"), key=lambda path: path.as_posix().lower())
    for metadata_path in metadata_paths:
        statistics["solutionMetadataFilesScanned"] += 1
        solution_directory = metadata_path.parent

        try:
            metadata = load_json(metadata_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            statistics["errors"] += 1
            errors.append(
                {
                    "kind": "invalidSolutionMetadata",
                    "path": workspace_relative_path(repo_root, metadata_path),
                    "message": str(error),
                }
            )
            continue

        support = metadata.get("support", {})
        support_tier = support.get("tier") if isinstance(support, Mapping) else None
        if support_tier != required_support_tier:
            statistics["nonMicrosoftSupportedSolutions"] += 1
            continue

        statistics["microsoftSupportedSolutions"] += 1
        manifest_paths = find_manifest_paths(
            solution_directory, manifest_directory_name, manifest_prefix, manifest_suffix
        )
        if not manifest_paths:
            warnings.append(
                {
                    "kind": "missingSolutionManifest",
                    "path": workspace_relative_path(repo_root, metadata_path),
                    "message": "No solution manifest was found for this Microsoft-supported solution.",
                }
            )
            continue

        for manifest_path in manifest_paths:
            try:
                manifest = load_json(manifest_path)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                statistics["errors"] += 1
                errors.append(
                    {
                        "kind": "invalidSolutionManifest",
                        "path": workspace_relative_path(repo_root, manifest_path),
                        "message": str(error),
                    }
                )
                continue

            statistics["manifestsRead"] += 1
            for content_type, content_type_settings in content_types.items():
                if not isinstance(content_type_settings, Mapping):
                    continue
                manifest_key = content_type_settings.get("manifestKey")
                if not isinstance(manifest_key, str):
                    continue
                manifest_values = get_manifest_values(manifest, manifest_key)
                if not isinstance(manifest_values, list):
                    continue

                expected_extensions = set(as_string_list(content_type_settings.get("extensions")))
                for manifest_value in manifest_values:
                    if not isinstance(manifest_value, str):
                        continue

                    content_path = resolve_manifest_file(
                        repo_root, solutions_root, solution_directory, manifest_value
                    )
                    if content_path is None:
                        statistics["missingArtifacts"] += 1
                        warnings.append(
                            {
                                "kind": "missingManifestListedArtifact",
                                "path": workspace_relative_path(repo_root, manifest_path),
                                "message": f"The manifest lists an unavailable file: {manifest_value}",
                            }
                        )
                        continue

                    if expected_extensions and content_path.suffix.lower() not in expected_extensions:
                        warnings.append(
                            {
                                "kind": "unexpectedContentExtension",
                                "path": workspace_relative_path(repo_root, content_path),
                                "message": f"Expected one of {sorted(expected_extensions)} for {content_type}.",
                            }
                        )

                    try:
                        record, parse_warning = build_record(
                            repo_root,
                            metadata_path,
                            manifest_path,
                            content_path,
                            metadata,
                            manifest,
                            content_type,
                            manifest_key,
                            taxonomy,
                            approved_mappings,
                        )
                        validate_document(
                            record,
                            record_schema_path,
                            workspace_relative_path(repo_root, content_path),
                        )
                    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
                        statistics["errors"] += 1
                        errors.append(
                            {
                                "kind": "invalidDatabaseRecord",
                                "path": workspace_relative_path(repo_root, content_path),
                                "message": str(error),
                            }
                        )
                        continue
                    source_path = str(record["sourcePath"])
                    if source_path in records_by_path:
                        statistics["duplicateArtifacts"] += 1
                        continue

                    records_by_path[source_path] = record
                    if parse_warning:
                        statistics["contentParseWarnings"] += 1
                        warnings.append(
                            {
                                "kind": "contentParseWarning",
                                "path": source_path,
                                "message": parse_warning,
                            }
                        )

    records = [records_by_path[path] for path in sorted(records_by_path, key=str.lower)]
    statistics["artifactsIndexed"] = len(records)
    mapping_status_counts = Counter(
        str(record["classification"]["mappingStatus"]) for record in records
    )
    confidence_counts = Counter(
        str(record["classification"]["retrievalConfidence"]) for record in records
    )
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "sourceRoot": source_root,
        "selection": {
            "supportTier": required_support_tier,
            "indexOnlyManifestListedFiles": bool(
                selection_settings.get("indexOnlyManifestListedFiles")
            ),
        },
        "statistics": statistics,
        "classification": {
            "mappedRecords": sum(
                1 for record in records if record["classification"]["asimSchemas"]
            ),
            "mappingStatusCounts": dict(sorted(mapping_status_counts.items())),
            "retrievalConfidenceCounts": dict(sorted(confidence_counts.items())),
        },
        "warnings": warnings,
        "errors": errors,
    }

    write_jsonl(output_path, records)
    write_json(report_path, report)
    return report


def main() -> int:
    arguments = parse_arguments()
    accelerator_root = Path(__file__).resolve().parents[1]
    repo_root = arguments.repo_root.resolve()

    try:
        policy = load_yaml(accelerator_root / "database" / "selection-policy.yaml")
        taxonomy = load_yaml(accelerator_root / "database" / "taxonomy.yaml")
        mapping_registry = load_asim_mapping_registry(
            accelerator_root / "database" / "asim-mapping-registry.yaml", taxonomy
        )
        database_settings = policy["database"]
        output_path = (
            resolve_path(repo_root, arguments.output)
            if arguments.output
            else resolve_path(accelerator_root, Path(database_settings["runtimePath"]))
        )
        report_path = (
            resolve_path(repo_root, arguments.report)
            if arguments.report
            else resolve_path(accelerator_root, Path(database_settings["refreshReportPath"]))
        )
        report = refresh_database(
            repo_root, output_path, report_path, policy, taxonomy, mapping_registry
        )
    except (KeyError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"Database refresh failed: {error}", file=sys.stderr)
        return 2

    statistics = report["statistics"]
    print(
        "Database refresh complete: "
        f"{statistics['artifactsIndexed']} artifacts from "
        f"{statistics['microsoftSupportedSolutions']} Microsoft-supported solutions."
    )
    print(
        f"Warnings: {len(report['warnings'])}; errors: {len(report['errors'])}. "
        f"Report: {report_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())