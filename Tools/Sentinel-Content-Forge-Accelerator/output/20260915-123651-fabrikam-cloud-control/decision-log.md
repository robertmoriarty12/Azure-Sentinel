# Sentinel Content Forge Decision Log

## Run Summary

| Item | Decision |
|---|---|
| Sample data | `Tools/Sentinel-Content-Forge-Accelerator/examples/cloud-audit/fabrikam-cloud-control-audit-events.jsonl` |
| Requested content | 4 analytic rules and 2 hunting queries |
| ASIM schemas | `AuditEvent`, `UserManagement` |
| ASIM mapping status | `compatible` |
| Source binding | `provisional` |
| Final status | Needs review |

## Step 0: Input and Preflight

### Inputs Observed

- The JSONL sample contains 30 synthetic Fabrikam Cloud Control audit records and 31 fields.
- The sample includes 17 operation names across read, create, update, delete, and export categories.
- The sample includes privileged role assignment, audit-setting, API-key, service-principal credential, data-export, backup-deletion, and remediation activity.
- The user supplied an unbound content request rather than a deployed connector or destination table.

### Decision

- Proceed with `AuditEvent` as the primary ASIM-compatible schema and `UserManagement` as a secondary schema for role and credential-change context.

### Evaluation

| Check | Result | Evidence |
|---|---|---|
| Required Python dependencies | Pass | `yaml` 6.0.3 and `jsonschema` 4.26.0 imported successfully. |
| Sample-data readability | Pass | 30 valid JSONL audit records with consistent fields and ordered UTC timestamps. |
| Source binding | Unbound | The fictional ISV sample does not identify a deployed Sentinel connector or destination table. |

## Step 1: Microsoft Content Database Refresh

### Decision

- Use the local runtime database refreshed from the current `Solutions` checkout.
- Admit only manifest-listed artifacts from solutions where `support.tier` is `Microsoft`.

### Evaluation

| Check | Result | Evidence |
|---|---|---|
| Microsoft-supported solutions | 253 | `database/runtime/refresh-report.json` |
| Solution manifests read | 252 | `database/runtime/refresh-report.json` |
| Database artifacts indexed | 2,748 | `database/runtime/refresh-report.json` |
| Retrieval-mapped records | 2,447 | `database/runtime/refresh-report.json classification.mappedRecords` |
| Mapping-status distribution | 121 explicit, 5 inferred from repository, 2,321 inferred from content, 301 not applicable | `database/runtime/refresh-report.json classification.mappingStatusCounts` |
| Retrieval-confidence distribution | 121 exact, 1,397 high, 375 medium, 554 low, 301 none | `database/runtime/refresh-report.json classification.retrievalConfidenceCounts` |
| Refresh errors | 0 | `database/runtime/refresh-report.json` |
| Refresh warnings | 1 missing solution manifest and 40 missing manifest-listed artifacts | `database/runtime/refresh-report.json` |

### Outcome

- Proceed. The refresh completed with zero errors and every analytic rule, hunting query, workbook, and parser has at least one ASIM retrieval schema.

## Step 2: ASIM Compatibility and Reference Retrieval

### ASIM Compatibility Decision

- ASIM schemas: `AuditEvent`, `UserManagement`
- Mapping status: `compatible`
- Rationale: The sample is control-plane and administrative audit telemetry; role and credential changes provide secondary identity-management evidence.

### Alternatives Considered

| ASIM schema | Decision | Reason |
|---|---|---|
| `AuditEvent` | Selected as primary | Operation names, categories, results, actor context, target resources, values, and correlation IDs are audit-event evidence. |
| `UserManagement` | Selected as secondary | Role assignment and service-principal credential events affect identities and privileges. |
| `Authentication` | Rejected | AuthMethod is contextual, but the sample does not contain sign-in or authentication outcome events. |
| `AlertEvent` | Rejected | The sample contains source audit records, not alert-provider findings. |

### Retrieval Evaluation

| Content type | ASIM schema query | Matching records | Returned records | Selected for generation | Selected confidence |
|---|---:|---:|---:|---:|---|
| Analytic rule | `AuditEvent` | 287 | 12 | 3 reference patterns | Exact and high |
| Analytic rule | `UserManagement` | 49 | 12 | 2 reference patterns | High |
| Hunting query | `AuditEvent` | 390 | 12 | 3 reference patterns | Exact and high |
| Hunting query | `UserManagement` | 73 | 12 | 1 reference pattern | High |

### Selected Microsoft References

| Reference path | Content type | Mapping status | Retrieval confidence | Used for | Why selected |
|---|---|---|---|---|---|
| `Solutions/Amazon Web Services/Analytic Rules/AWS_CreatedCloudFormationPolicytoPrivilegeEscalation.yaml` | Analytic rule | `inferredFromContent` | `high` | Privileged role assignment | Provides a create-and-attach privilege escalation sequence pattern. |
| `Solutions/GoogleWorkspaceReports/Analytic Rules/GWorkspaceAdminPermissionsGranted.yaml` | Analytic rule | `inferredFromContent` | `high` | Privileged role assignment | Provides an administrative-permission change pattern. |
| `Solutions/Amazon Web Services/Analytic Rules/AWS_ClearStopChangeTrailLogs.yaml` | Analytic rule | `inferredFromContent` | `high` | Audit telemetry tampering | Provides a control-plane logging manipulation pattern. |
| `Solutions/Amazon Web Services/Analytic Rules/AWS_UserAccessKeyCreated.yaml` | Analytic rule | `inferredFromContent` | `high` | Multiple API keys | Provides a credential-creation persistence pattern. |
| `Solutions/GoogleWorkspaceReports/Analytic Rules/GWorkspaceChangedUserAccess.yaml` | Analytic rule | `inferredFromContent` | `high` | External sharing exposure | Provides a user-access change pattern. |
| `Solutions/GoogleWorkspaceReports/Analytic Rules/GWorkspaceApiAccessToNewClient.yaml` | Analytic rule | `inferredFromContent` | `high` | Public API exposure | Provides an API access change pattern. |
| `Solutions/Hybrid Attack - Cloud & Identity/Hunting Queries/InitialAccess/entra-app-credential-change-sp-signin-burst-chain.yaml` | Hunting query | `explicit` | `exact` | External privileged activity timeline | Provides a correlated credential and control-plane investigation pattern. |
| `Solutions/Amazon Web Services/Hunting Queries/AWS_CreateAccessKey.yaml` | Hunting query | `inferredFromContent` | `high` | External privileged activity timeline | Provides a credential-creation investigation pattern. |
| `Solutions/GoogleWorkspaceReports/Hunting Queries/GWorkspaceDocumentSharedExternally.yaml` | Hunting query | `inferredFromContent` | `high` | External privileged activity timeline | Provides an external-sharing investigation pattern. |
| `Solutions/Amazon Web Services/Hunting Queries/AWS_BucketVersioningSuspended.yaml` | Hunting query | `inferredFromContent` | `high` | Audit control change timeline | Provides a cloud-control change and impact investigation pattern. |

### Considered but Not Used

| Reference path | Mapping status and confidence | Reason not used |
|---|---|---|
| `Solutions/Amazon Web Services/Analytic Rules/AWS_ConsoleLogonWithoutMFA.yaml` | `inferredFromContent; high` | The sample has AuthMethod but no interactive sign-in or MFA outcome event stream. |
| `Solutions/GoogleWorkspaceReports/Analytic Rules/GWorkspacePossibleBruteForce.yaml` | `inferredFromContent; high` | Failed role-assignment API operations are not authentication attempts. |
| `Solutions/GoogleWorkspaceReports/Hunting Queries/GWorkspaceMultiIPAddresses.yaml` | `inferredFromContent; high` | The sample does not establish a historical IP baseline per user. |
| `Solutions/Amazon Web Services/Hunting Queries/AWS_EC2_WithoutKeyPair.yaml` | `inferredFromContent; high` | The sample contains no virtual machine provisioning events. |

## Step 3: Generation Decisions

### Source-Binding Decision

- Status: `provisional`
- Connector ID: `FabrikamCloudControl`
- Data source: `FabrikamCloudControlAudit_CL` table
- Rationale: The fictional ISV sample does not identify a deployed Sentinel connector or destination table. The names are draft identifiers derived from the sample.
- Integration impact: Confirm or replace the connector ID and table name before solution integration or a pull request.

### Content Coverage Evaluation

| Requested type | Requested count | Generated count | Decision |
|---|---:|---:|---|
| Analytic rule | 4 | 4 | Generated detections for role escalation, audit tampering, API-key persistence, and exposure changes. |
| Hunting query | 2 | 2 | Generated timelines for external privileged activity and audit-control changes. |
| Workbook | 0 | 0 | Not requested in this run. |

### Artifact Decisions

| Generated artifact | Scenario | Sample-data fields used | Microsoft references used | Why this scenario was chosen |
|---|---|---|---|---|
| `content/Analytic Rules/FabrikamCloudControl_PrivilegedRoleAssignmentAfterFailures.yaml` | Successful OrganizationOwner assignment after failures | Role operation, result, actor, source IP, target user, target role, correlation ID | AWS CloudFormation privilege escalation; Google Workspace admin permissions | The sample contains one successful assignment after 3 failures from one external actor and IP. |
| `content/Analytic Rules/FabrikamCloudControl_AuditTelemetryTampering.yaml` | Audit streaming disabled and retention reduced | Operation, result, target, old value, new value, actor, source IP | AWS CloudTrail log changes | The sample contains both audit-control tampering operations. |
| `content/Analytic Rules/FabrikamCloudControl_MultipleApiKeysFromExternalSource.yaml` | Multiple API key creation | Operation, result, actor, IP, country, authentication method, key and workspace names | AWS access-key creation | One external actor created 2 API keys within one minute. |
| `content/Analytic Rules/FabrikamCloudControl_ExternalSharingOrPublicApiEnabled.yaml` | External sharing and public API exposure | Operation, result, actor, IP, workspace, policy values | Google Workspace access and API access changes | The sample contains 2 exposure-enabling policy changes from an external source. |
| `content/Hunting Queries/FabrikamCloudControl_ExternalPrivilegedActivityTimeline.yaml` | High-impact external activity sequence | Operation, actor, IP, source country, target, values, export URL, correlation ID | Entra credential change; AWS API key; Google external sharing | The sample has a compact 12-event sequence from one external actor. |
| `content/Hunting Queries/FabrikamCloudControl_AuditControlChangeTimeline.yaml` | Audit tampering and remediation sequence | Operation, actor, IP, target, previous and new values, correlation ID | AWS bucket-versioning suspension | The sample includes changes that reduce audit visibility and later restore it. |

### Generation Evaluations

| Evaluation | Result | Decision or evidence |
|---|---|---|
| Source-field coverage | Pass | Every field in `generation-evidence.json` exists in the 30-record sample. |
| Binding consistency | Pass with review gate | Every artifact declares `FabrikamCloudControl` and `FabrikamCloudControlAudit_CL`; both are provisional. |
| Scenario distinctness | Pass | The detections and hunts separately cover escalation, audit tampering, credential persistence, exposure, external activity, and remediation. |
| Originality | Pass | The artifacts adapt Microsoft patterns to the Fabrikam field names and sample behavior without copying a source artifact. |
| Unsupported scenario handling | Pass | Authentication and alert scenarios were not generated because the sample does not provide sign-in outcomes or alert-provider records. |

## Step 4: Validation and Review

### Static Validation

| Validation run | Artifacts | Passed | Warnings | Failed | Not run | Result |
|---|---:|---:|---:|---:|---:|---|
| Initial analytic-rule probe | 2 | 38 | 0 | 0 | 4 | `needsReview` |
| Complete content set | 6 | 104 | 0 | 0 | 12 | `needsReview` |

### Behavior Evaluation

| Artifact group | Evaluation method | Observed result | Result |
|---|---|---|---|
| 4 analytic rules | Synthetic sample replay | One role-escalation group, 2 audit-tampering rows, one API-key group, and 2 exposure-change rows. | Pass |
| 2 hunting queries | Synthetic sample replay | 12 high-impact external activity rows and 5 audit-control timeline rows. | Pass |

The detailed replay is recorded in `behavior-evaluation.md`. It is not KQL execution against a Log Analytics workspace.

### Repairs

| Issue | Decision | Result |
|---|---|---|
| No deterministic validation failures | No repair required | Complete static validation reported zero failed checks and zero warnings. |

### Remaining Review Gates

- Confirm or replace provisional `FabrikamCloudControl` and `FabrikamCloudControlAudit_CL` bindings with actual connector and table values.
- Execute the generated KQL against representative data in a test workspace.
- Review thresholds and false-positive behavior with an analyst before integrating content into a solution.
- Review the staged content for production naming, scheduling, and environment-specific tuning.

## Final Decision

- Run status: `staged-review-only`
- Reason: The run generated the requested 4 analytic rules and 2 hunting queries. Static validation has zero failures, and synthetic sample replay produced expected results. KQL execution and provisional source-binding confirmation remain unperformed.
- Next required action: Review the staged artifacts, confirm the source binding, and run the queries in a test workspace before solution integration.