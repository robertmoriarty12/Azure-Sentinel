# Fabrikam Cloud Control Sample Replay

This replay evaluates the staged filters and thresholds against the 30-record synthetic JSONL sample. It is not KQL execution against a Log Analytics workspace.

## Analytic Rules

| Artifact | Expected sample result | Observed key values |
|---|---:|---|
| Privileged role assignment after denied attempts | 1 result | `lena@contoso.example` at `203.0.113.77` created an `OrganizationOwner` assignment for `contractor@partner.example` after 3 failures in `corr-role-escalation`. |
| Audit telemetry disabled or retention reduced | 2 results | Audit streaming changed to `Disabled` and audit retention changed to `7 days`. |
| Multiple API keys from external source | 1 result | `lena@contoso.example` created 2 API keys from `203.0.113.77` using `ApiToken`. |
| External sharing or public API enabled | 2 results | Finance external sharing and public API access were both enabled from `203.0.113.77`. |

## Hunting Queries

| Artifact | Expected sample result | Observed key values |
|---|---:|---|
| External privileged cloud control activity timeline | 12 rows | The external actor completed role, API-key, service-principal credential, audit, policy, export, and backup operations. |
| Audit control change and remediation timeline | 5 rows | The sample includes a normal retention change, audit tampering, and later restoration of audit streaming and retention. |

## Remaining Evaluation

The provisional `FabrikamCloudControl` connector and `FabrikamCloudControlAudit_CL` table must be confirmed. The KQL must also be run against representative data in a test workspace before solution integration.