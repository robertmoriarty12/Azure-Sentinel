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
from refresh_database import (
  classify_record,
  extract_mapping_registry_evidence,
    infer_best_effort_classification,
  load_asim_mapping_registry,
  load_yaml,
  refresh_database,
)
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
tags:
  - Schema: ASimNetworkSessions
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
            self.assertEqual(["NetworkSession"], records[0]["classification"]["asimSchemas"])
            self.assertEqual("explicit", records[0]["classification"]["mappingStatus"])
            self.assertEqual("exact", records[0]["classification"]["retrievalConfidence"])
            self.assertEqual(
              {
                "taxonomyVersion",
                "asimSchemas",
                "asimEvidence",
                "mappingStatus",
                "retrievalConfidence",
              },
              set(records[0]["classification"]),
            )
            self.assertTrue(microsoft_rule_path.is_file())
            validate_document(
                records[0],
                ACCELERATOR_ROOT / "schemas" / "database-record.schema.json",
                "test database record",
            )

            result = build_result(
              output_path, ["NetworkSession"], ["analyticRule"], records, 0, 10
            )
            self.assertEqual(1, result["matchingRecords"])
            self.assertEqual(1, len(result["returnedRecords"]))

    def test_approved_mapping_registry_requires_all_selectors(self) -> None:
        mapping_registry = load_asim_mapping_registry(
            ACCELERATOR_ROOT / "database" / "asim-mapping-registry.yaml", self.taxonomy
        )
        source_path = (
            "Solutions/PaloAlto-PAN-OS/Hunting Queries/"
            "Palo Alto - potential beaconing detected.yaml"
        )
        traffic_content = (
            "CommonSecurityLog\n"
            "| where DeviceVendor == \"Palo Alto Networks\"\n"
            "| where Activity == \"TRAFFIC\"\n"
        )

        mapping_evidence = extract_mapping_registry_evidence(
            mapping_registry, source_path, "huntingQuery", traffic_content
        )
        classification = classify_record(
            "huntingQuery", [], mapping_evidence, mapping_registry
        )

        self.assertEqual(["NetworkSession"], classification["asimSchemas"])
        self.assertEqual("inferredFromRepository", classification["mappingStatus"])
        self.assertEqual("high", classification["retrievalConfidence"])
        self.assertEqual(
            [
                {
                    "schema": "NetworkSession",
                    "source": "mappingRegistry",
                    "value": "palo-alto-panos-network-session-traffic",
                }
            ],
            classification["asimEvidence"],
        )

        incomplete_evidence = extract_mapping_registry_evidence(
            mapping_registry,
            source_path,
            "huntingQuery",
            traffic_content.replace("TRAFFIC", "THREAT"),
        )
        incomplete_classification = classify_record(
            "huntingQuery", [], incomplete_evidence, mapping_registry
        )
        self.assertEqual([], incomplete_classification["asimSchemas"])
        self.assertEqual([], incomplete_classification["asimEvidence"])
        self.assertEqual("unmapped", incomplete_classification["mappingStatus"])

    def test_best_effort_inference_maps_source_and_metadata_context(self) -> None:
        inferred = infer_best_effort_classification(
            self.taxonomy,
            "analyticRule",
            "Solutions/Example/Analytic Rules/SignInRule.yaml",
            "SigninLogs | where ResultType != 0 | summarize count() by UserPrincipalName",
            {"name": "Repeated sign-in failures"},
            ["AzureActiveDirectory"],
            ["SigninLogs"],
            ["Identity"],
            ["Account", "IP"],
        )

        self.assertIsNotNone(inferred)
        self.assertEqual(["Authentication"], inferred["asimSchemas"])
        self.assertEqual("inferredFromContent", inferred["mappingStatus"])
        self.assertEqual("high", inferred["retrievalConfidence"])
        self.assertTrue(
            any(item["source"] == "sourceTerm" for item in inferred["asimEvidence"])
        )

        fallback = infer_best_effort_classification(
            self.taxonomy,
            "workbook",
            "Solutions/Example/Workbooks/Overview.json",
            "{}",
            {"name": "Overview"},
            [],
            [],
            ["Security - Network"],
            [],
        )

        self.assertIsNotNone(fallback)
        self.assertEqual(["NetworkSession"], fallback["asimSchemas"])
        self.assertEqual("low", fallback["retrievalConfidence"])
        self.assertEqual("metadataDomain", fallback["asimEvidence"][0]["source"])

        content_type_fallback = infer_best_effort_classification(
            self.taxonomy,
            "analyticRule",
            "Solutions/Example/Analytic Rules/UnknownRule.yaml",
            "{}",
            {"name": "Unknown rule"},
            [],
            [],
            [],
            [],
        )
        self.assertIsNotNone(content_type_fallback)
        self.assertEqual(["AlertEvent"], content_type_fallback["asimSchemas"])
        self.assertEqual(
            "contentTypeFallback", content_type_fallback["asimEvidence"][0]["source"]
        )

        parser_inference = infer_best_effort_classification(
            self.taxonomy,
            "parser",
            "Solutions/Example/Parsers/parser_VendorVPCFlowLogsAliasFunction.json",
            '{"category": "Function"}',
            {"functionAlias": "VendorVPCFlowLogsAliasFunction"},
            [],
            [],
            [],
            [],
        )
        self.assertIsNotNone(parser_inference)
        self.assertEqual(["NetworkSession"], parser_inference["asimSchemas"])
        self.assertEqual("high", parser_inference["retrievalConfidence"])
        self.assertTrue(
            any(item["source"] == "sourceTerm" for item in parser_inference["asimEvidence"])
        )

        workbook_inference = infer_best_effort_classification(
            self.taxonomy,
            "workbook",
            "Solutions/Example/Workbooks/ApiProtection.json",
            '{"queryType": 0, "query": "ExampleApiEvents | summarize count() by SourceIp"}',
            {"name": "API protection"},
            [],
            [],
            [],
            [],
        )
        self.assertIsNotNone(workbook_inference)
        self.assertEqual(["NetworkSession"], workbook_inference["asimSchemas"])
        self.assertNotIn("Dns", workbook_inference["asimSchemas"])

        playbook_classification = classify_record(
            "playbook",
            [],
            [],
            [],
            {
                "asimSchemas": ["AlertEvent"],
                "asimEvidence": [
                    {
                        "schema": "AlertEvent",
                        "source": "fieldTerm",
                        "value": "Entities",
                    }
                ],
                "mappingStatus": "inferredFromContent",
                "retrievalConfidence": "low",
            },
        )
        self.assertEqual([], playbook_classification["asimSchemas"])
        self.assertEqual("notApplicable", playbook_classification["mappingStatus"])

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
                    "context": {
                        "productResearch": {
                            "allowOfficialProductDocumentationLookup": True,
                            "vendorName": "Palo Alto Networks",
                            "productName": "PAN-OS",
                            "officialDocumentationUrls": [
                                "https://docs.paloaltonetworks.com/"
                            ],
                        }
                    },
                },
            )

            request = load_content_request(request_path)
            self.assertEqual("unbound", content_request_binding_status(request))
            self.assertIsNone(content_request_dependency(request))
            self.assertTrue(
                request["context"]["productResearch"][
                    "allowOfficialProductDocumentationLookup"
                ]
            )

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

    def test_database_query_prioritizes_mapping_strength(self) -> None:
        records = [
            {
                "sourcePath": "Solutions/Example/Analytic Rules/ContentLow.yaml",
                "solution": {"supportTier": "Microsoft"},
                "content": {"contentType": "analyticRule"},
                "classification": {
                    "asimSchemas": ["NetworkSession"],
                    "mappingStatus": "inferredFromContent",
                    "retrievalConfidence": "low",
                },
            },
            {
                "sourcePath": "Solutions/Example/Analytic Rules/RepositoryHigh.yaml",
                "solution": {"supportTier": "Microsoft"},
                "content": {"contentType": "analyticRule"},
                "classification": {
                    "asimSchemas": ["NetworkSession"],
                    "mappingStatus": "inferredFromRepository",
                    "retrievalConfidence": "high",
                },
            },
            {
                "sourcePath": "Solutions/Example/Analytic Rules/Explicit.yaml",
                "solution": {"supportTier": "Microsoft"},
                "content": {"contentType": "analyticRule"},
                "classification": {
                    "asimSchemas": ["NetworkSession"],
                    "mappingStatus": "explicit",
                    "retrievalConfidence": "exact",
                },
            },
            {
                "sourcePath": "Solutions/Example/Analytic Rules/ContentHigh.yaml",
                "solution": {"supportTier": "Microsoft"},
                "content": {"contentType": "analyticRule"},
                "classification": {
                    "asimSchemas": ["NetworkSession"],
                    "mappingStatus": "inferredFromContent",
                    "retrievalConfidence": "high",
                },
            },
        ]

        result = build_result(
            Path("database.jsonl"), ["NetworkSession"], ["analyticRule"], records, 0, 10
        )

        self.assertEqual(
            [
                "Solutions/Example/Analytic Rules/Explicit.yaml",
                "Solutions/Example/Analytic Rules/RepositoryHigh.yaml",
                "Solutions/Example/Analytic Rules/ContentHigh.yaml",
                "Solutions/Example/Analytic Rules/ContentLow.yaml",
            ],
            [record["sourcePath"] for record in result["returnedRecords"]],
        )

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