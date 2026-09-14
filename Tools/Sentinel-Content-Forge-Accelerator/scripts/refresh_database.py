from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from schema_utils import validate_document


ASIM_FUNCTION_PATTERN = re.compile(r"\b_Im_[A-Za-z0-9_]+\b")


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
    taxonomy: Mapping[str, Any], metadata_domains: list[str], asim_functions: list[str]
) -> tuple[str, list[str]]:
    categories = taxonomy.get("categories", [])
    if not isinstance(categories, list):
        raise ValueError("Expected categories to be a list in taxonomy.yaml")

    category_definitions = [category for category in categories if isinstance(category, Mapping)]
    metadata_matches: list[str] = []

    for metadata_domain in metadata_domains:
        for category in category_definitions:
            category_id = category.get("id")
            category_domains = as_string_list(category.get("metadataDomains"))
            if isinstance(category_id, str) and metadata_domain in category_domains:
                metadata_matches.append(category_id)

    metadata_matches = unique_strings(metadata_matches)
    if metadata_matches:
        return metadata_matches[0], metadata_matches[1:]

    asim_matches: list[str] = []
    for asim_function in asim_functions:
        for category in category_definitions:
            category_id = category.get("id")
            category_functions = as_string_list(category.get("asimFunctions"))
            if isinstance(category_id, str) and asim_function in category_functions:
                asim_matches.append(category_id)

    asim_matches = unique_strings(asim_matches)
    if len(asim_matches) == 1:
        return asim_matches[0], []
    if asim_matches:
        return str(taxonomy["databaseCategorization"]["unmatchedCategory"]), asim_matches

    return str(taxonomy["databaseCategorization"]["unmatchedCategory"]), []


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
) -> tuple[dict[str, Any], str | None]:
    parsed_content, raw_content, parse_warning = read_content(content_path)
    connector_ids, data_types = extract_required_data_connectors(parsed_content)
    connector_ids.extend(
        collect_values_for_keys(parsed_content, {"dataConnectorsDependencies"})
    )
    data_types.extend(collect_values_for_keys(parsed_content, {"dataTypesDependencies"}))

    asim_functions = extract_asim_functions(raw_content)
    metadata_domains = as_string_list(metadata.get("categories", {}).get("domains"))
    primary_category, secondary_categories = classify_record(
        taxonomy, metadata_domains, asim_functions
    )

    support = metadata.get("support", {})
    if not isinstance(support, Mapping):
        support = {}

    record = {
        "schemaVersion": 1,
        "sourcePath": workspace_relative_path(repo_root, content_path),
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
            "entityTypes": extract_entity_types(parsed_content),
        },
        "classification": {
            "taxonomyVersion": 1,
            "primaryCategory": primary_category,
            "secondaryCategories": secondary_categories,
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
    repo_root: Path, output_path: Path, report_path: Path, policy: Mapping[str, Any], taxonomy: Mapping[str, Any]
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
        report = refresh_database(repo_root, output_path, report_path, policy, taxonomy)
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