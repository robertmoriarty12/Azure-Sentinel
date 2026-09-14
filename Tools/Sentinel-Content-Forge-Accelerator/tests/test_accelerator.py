from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ACCELERATOR_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = ACCELERATOR_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from query_database import build_result, resolve_database_path
from refresh_database import load_yaml, refresh_database
from schema_utils import validate_document
from validate_output import (
  content_request_binding_status,
  content_request_dependency,
  load_content_request,
  validate_artifact,
)


VALID_RULE = """\
id: 11111111-2222-3333-4444-555555555555
name: Example network source activity
description: Identifies example network source activity for validation testing.
severity: Medium
status: Available
requiredDataConnectors:
  - connectorId: ExampleConnector
    dataTypes:
      - ExampleNetworkEvents_CL
queryFrequency: 1h
queryPeriod: 1h
triggerOperator: gt
triggerThreshold: 0
tactics:
  - Discovery
relevantTechniques:
  - T1046
query: |
  ExampleNetworkEvents_CL
  | where TimeGenerated > ago(1h)
  | summarize EventCount = count() by SourceIpAddress
entityMappings:
  - entityType: IP
    fieldMappings:
      - identifier: Address
        columnName: SourceIpAddress
version: 1.0.0
kind: Scheduled
"""


INVALID_RULE = """\
id: invalid
name: Invalid example.
description: Detects a deliberately invalid rule.
severity: Critical
status: Ready
requiredDataConnectors:
  - connectorId: WrongConnector
    dataTypes:
      - WrongTable_CL
queryFrequency: 2h
queryPeriod: 1h
triggerOperator: greaterThan
triggerThreshold: -1
tactics:
  - InvalidTactic
relevantTechniques:
  - InvalidTechnique
query: |
  WrongTable_CL
  | summarize count() by MissingColumn
entityMappings:
  - entityType: InvalidEntity
    fieldMappings:
      - identifier: InvalidIdentifier
        columnName: AbsentColumn
version: 1
kind: Scheduled
"""


class SentinelContentForgeAcceleratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_yaml(ACCELERATOR_ROOT / "database" / "selection-policy.yaml")
        self.taxonomy = load_yaml(ACCELERATOR_ROOT / "database" / "taxonomy.yaml")

    def write_json(self, path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def write_solution(
        self, repo_root: Path, solution_name: str, support_tier: str, data_directory: str
    ) -> Path:
        solution_directory = repo_root / "Solutions" / solution_name
        self.write_json(
            solution_directory / "SolutionMetadata.json",
            {
                "publisherId": "azuresentinel",
                "offerId": f"example-{solution_name.lower().replace(' ', '-')}",
                "providers": ["Microsoft"],
                "categories": {"domains": ["Security - Network"]},
                "support": {"tier": support_tier},
            },
        )
        self.write_json(
            solution_directory / data_directory / f"Solution_{solution_name.replace(' ', '')}.json",
            {
                "Name": solution_name,
                "Analytic Rules": ["/Analytic Rules/ExampleNetworkRule.yaml"],
            },
        )
        rule_path = solution_directory / "Analytic Rules" / "ExampleNetworkRule.yaml"
        rule_path.parent.mkdir(parents=True, exist_ok=True)
        rule_path.write_text(VALID_RULE, encoding="utf-8")
        return rule_path

    def test_refresh_indexes_only_microsoft_manifest_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            microsoft_rule_path = self.write_solution(
                repo_root, "Microsoft Example", "Microsoft", "data"
            )
            self.write_solution(repo_root, "Partner Example", "Partner", "Data")

            output_path = repo_root / "database.jsonl"
            report_path = repo_root / "refresh-report.json"
            report = refresh_database(
                repo_root, output_path, report_path, self.policy, self.taxonomy
            )
            records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line
            ]

            self.assertEqual(1, len(records))
            self.assertEqual(1, report["statistics"]["artifactsIndexed"])
            self.assertEqual(1, report["statistics"]["microsoftSupportedSolutions"])
            self.assertEqual(1, report["statistics"]["nonMicrosoftSupportedSolutions"])
            self.assertEqual(
                "Solutions/Microsoft Example/Analytic Rules/ExampleNetworkRule.yaml",
                records[0]["sourcePath"],
            )
            self.assertEqual("Microsoft", records[0]["solution"]["supportTier"])
            self.assertEqual("network", records[0]["classification"]["primaryCategory"])
            self.assertTrue(microsoft_rule_path.is_file())
            validate_document(
                records[0],
                ACCELERATOR_ROOT / "schemas" / "database-record.schema.json",
                "test database record",
            )

            result = build_result(
                output_path, "network", ["analyticRule"], records, 0, 10
            )
            self.assertEqual(1, result["matchingRecords"])
            self.assertEqual(1, len(result["returnedRecords"]))

    def test_static_validation_distinguishes_valid_and_invalid_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            rule_directory = Path(temporary_directory) / "Analytic Rules"
            rule_directory.mkdir(parents=True)
            valid_rule_path = rule_directory / "ValidRule.yaml"
            invalid_rule_path = rule_directory / "InvalidRule.yaml"
            valid_rule_path.write_text(VALID_RULE, encoding="utf-8")
            invalid_rule_path.write_text(INVALID_RULE, encoding="utf-8")

            dependency = ("ExampleConnector", "ExampleNetworkEvents_CL")
            valid_artifact = validate_artifact(valid_rule_path, dependency)
            invalid_artifact = validate_artifact(invalid_rule_path, dependency)

            self.assertIsNotNone(valid_artifact)
            self.assertIsNotNone(invalid_artifact)
            self.assertEqual("needsReview", valid_artifact["status"])
            self.assertEqual("failed", invalid_artifact["status"])

            invalid_check_ids = {
                check["id"]
                for check in invalid_artifact["checks"]
                if check["status"] == "failed"
            }
            self.assertIn("structure.id", invalid_check_ids)
            self.assertIn("dependency.requested-data-source", invalid_check_ids)
            self.assertIn("dependency.query-data-source", invalid_check_ids)
            self.assertIn("semantic.schedule-order", invalid_check_ids)

    def test_sample_only_request_defers_source_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            request_path = Path(temporary_directory) / "content-request.json"
            self.write_json(
                request_path,
                {
                    "requestVersion": 1,
                    "sampleData": {"path": "sample-events.jsonl", "format": "jsonl"},
                    "requestedContent": {"types": ["analyticRule"]},
                    "sourceBinding": {"status": "unbound"},
                },
            )

            request = load_content_request(request_path)
            self.assertEqual("unbound", content_request_binding_status(request))
            self.assertIsNone(content_request_dependency(request))

            rule_directory = Path(temporary_directory) / "Analytic Rules"
            rule_directory.mkdir()
            rule_path = rule_directory / "SampleOnlyRule.yaml"
            rule_path.write_text(VALID_RULE, encoding="utf-8")
            artifact = validate_artifact(rule_path, None, "unbound")

            self.assertIsNotNone(artifact)
            checks_by_id = {check["id"]: check for check in artifact["checks"]}
            self.assertEqual("needsReview", artifact["status"])
            self.assertEqual("notRun", checks_by_id["dependency.source-binding"]["status"])
            self.assertNotIn("dependency.requested-data-source", checks_by_id)
            self.assertNotIn("dependency.query-data-source", checks_by_id)

    def test_database_path_uses_baseline_when_runtime_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            accelerator_root = Path(temporary_directory)
            baseline_path = (
                accelerator_root / "database" / "baseline" / "microsoft-content-database.jsonl"
            )
            baseline_path.parent.mkdir(parents=True)
            baseline_path.write_text("", encoding="utf-8")

            self.assertEqual(
                baseline_path, resolve_database_path(None, accelerator_root)
            )

            runtime_path = (
                accelerator_root / "database" / "runtime" / "microsoft-content-database.jsonl"
            )
            runtime_path.parent.mkdir(parents=True)
            runtime_path.write_text("", encoding="utf-8")
            self.assertEqual(runtime_path, resolve_database_path(None, accelerator_root))


if __name__ == "__main__":
    unittest.main()