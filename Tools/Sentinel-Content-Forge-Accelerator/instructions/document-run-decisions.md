# Document Run Decisions

These instructions are for the Sentinel Content Forge Accelerator agent. Create and maintain a human-readable decision log for every new run.

## Purpose

The JSON artifacts in a staged run are machine-readable evidence. `decision-log.md` is the companion narrative for a person reviewing the run. It explains the decisions made at each stage, the evidence used, which Microsoft Content Database references informed the output, evaluations performed, repair actions, and remaining review gates.

Create this file before the preflight stage:

```text
Tools/Sentinel-Content-Forge-Accelerator/output/<run-id>/decision-log.md
```

Update the same file after every stage. Do not create a decision log for an existing run retroactively unless the user explicitly asks.

## Evidence Rules

- State only facts observed in the current run's files, command results, or original Microsoft reference artifacts.
- Link every selected reference by its workspace-relative `Solutions/...` path.
- Distinguish a reference considered during retrieval from a reference actually used to generate an artifact.
- Do not claim a database item was selected merely because it matched an ASIM schema.
- Do not claim KQL execution, workbook rendering, or human review occurred unless it actually occurred.
- When a source binding is provisional, name it as provisional and explain that it cannot be used for solution integration until confirmed.
- Summarize large record sets with counts. Do not paste all database records or entire source artifacts into the decision log.
- Preserve failed evaluations and repair decisions. Do not erase them after a repair succeeds.

## Required Structure

Use these sections in this order. Keep entries specific to the current run.

```markdown
# Sentinel Content Forge Decision Log

## Run Summary

| Item | Decision |
|---|---|
| Sample data | `<workspace-relative-path>` |
| Requested content | `<types and requested counts>` |
| ASIM schemas | `<schemas or unmapped>` |
| ASIM mapping status | `<explicit, inferred, ambiguous, unmapped, or not applicable>` |
| Source binding | `<provided, provisional, or unbound>` |
| Final status | `<in progress, failed, needs review, or complete>` |

## Step 0: Input and Preflight

### Inputs Observed

- `<sample format, record count, and key schema signals>`
- `<user-provided connector or table details, if any>`

### Decision

- `<why the request can proceed or why it must stop>`

### Evaluation

| Check | Result | Evidence |
|---|---|---|
| Required Python dependencies | `<pass or fail>` | `<versions or error>` |
| Sample-data readability | `<pass or fail>` | `<record count and format>` |
| Source binding | `<provided, unbound, or provisional>` | `<reason>` |

## Step 1: Microsoft Content Database Refresh

### Decision

- Use the local runtime database refreshed from the current `Solutions` checkout.
- Admit only manifest-listed artifacts from solutions where `support.tier` is `Microsoft`.

### Evaluation

| Check | Result | Evidence |
|---|---|---|
| Microsoft-supported solutions | `<count>` | `refresh-report.json` |
| Solution manifests read | `<count>` | `refresh-report.json` |
| Database artifacts indexed | `<count>` | `refresh-report.json` |
| Retrieval-mapped records | `<count>` | `refresh-report.json classification.mappedRecords` |
| Mapping-status distribution | `<counts>` | `refresh-report.json classification.mappingStatusCounts` |
| Retrieval-confidence distribution | `<counts>` | `refresh-report.json classification.retrievalConfidenceCounts` |
| Refresh errors | `<count>` | `refresh-report.json` |
| Refresh warnings | `<count grouped by kind>` | `refresh-report.json` |

### Outcome

- `<why the refresh can proceed or why the run stopped>`

## Step 2: ASIM Compatibility and Reference Retrieval

### ASIM Compatibility Decision

- ASIM schemas: `<schemas or none>`
- Mapping status: `<explicit, compatible, ambiguous, unmapped, or not applicable>`
- Rationale: `<observable fields, event patterns, local parser evidence, and user context>`

### Alternatives Considered

| ASIM schema | Decision | Reason |
|---|---|---|
| `<ASIM schema>` | `<selected, secondary, or rejected>` | `<evidence>` |

### Retrieval Evaluation

| Content type | ASIM schema query | Matching records | Returned records | Selected for generation | Selected confidence |
|---|---:|---:|---:|---:|---|
| Analytic rule | `<ASIM schema>` | `<count>` | `<count>` | `<count>` | `<exact, high, medium, or low>` |
| Hunting query | `<ASIM schema>` | `<count>` | `<count>` | `<count>` | `<exact, high, medium, or low>` |
| Workbook | `<ASIM schema>` | `<count>` | `<count>` | `<count>` | `<exact, high, medium, or low>` |

### Selected Microsoft References

| Reference path | Content type | Mapping status | Retrieval confidence | Used for | Why selected |
|---|---|---|---|---|---|
| `Solutions/...` | `<type>` | `<status>` | `<exact, high, medium, or low>` | `<artifact or pattern>` | `<data-shape or scenario fit>` |

### Considered but Not Used

| Reference path | Mapping status and confidence | Reason not used |
|---|---|---|
| `Solutions/...` | `<status; confidence>` | `<not scenario-aligned, not data-shape-aligned, redundant, or other concrete reason>` |

## Step 3: Generation Decisions

### Source-Binding Decision

- Status: `<provided or provisional>`
- Connector ID: `<value>`
- Data source: `<value>`
- Rationale: `<why this binding was supplied or derived>`
- Integration impact: `<what must happen before it can move into a solution>`

### Content Coverage Evaluation

| Requested type | Requested count | Generated count | Decision |
|---|---:|---:|---|
| Analytic rule | `<count>` | `<count>` | `<why>` |
| Hunting query | `<count>` | `<count>` | `<why>` |
| Workbook | `<count>` | `<count>` | `<why>` |

### Artifact Decisions

| Generated artifact | Scenario | Sample-data fields used | Microsoft references used | Why this scenario was chosen |
|---|---|---|---|---|
| `<path>` | `<scenario>` | `<fields>` | `Solutions/...` | `<observed behavior or meaningful coverage>` |

### Generation Evaluations

| Evaluation | Result | Decision or evidence |
|---|---|---|
| Source-field coverage | `<pass or fail>` | `<every referenced field exists, or list missing fields>` |
| Binding consistency | `<pass or fail>` | `<connector and data source used consistently>` |
| Scenario distinctness | `<pass or fail>` | `<why outputs are not duplicates>` |
| Originality | `<pass or fail>` | `<how output adapts patterns without copying a source artifact>` |
| Unsupported scenario handling | `<generated or omitted>` | `<reason>` |

## Step 4: Validation and Review

### Static Validation

| Validation run | Artifacts | Passed | Warnings | Failed | Not run | Result |
|---|---:|---:|---:|---:|---:|---|
| `<timestamp or run number>` | `<count>` | `<count>` | `<count>` | `<count>` | `<count>` | `<status>` |

### Behavior Evaluation

| Artifact | Evaluation method | Observed result | Result |
|---|---|---|---|
| `<path>` | `<sample-data replay, KQL test, or workbook rendering>` | `<specific counts or outcome>` | `<pass, fail, or not run>` |

### Repairs

| Issue | Decision | Result |
|---|---|---|
| `<validation check or issue>` | `<repair performed or why no repair>` | `<rerun result>` |

### Remaining Review Gates

- `<provisional binding confirmation, KQL execution, workbook rendering, or human review>`

## Final Decision

- Run status: `<failed, staged-review-only, or integration-ready>`
- Reason: `<specific reason>`
- Next required action: `<specific action>`
```

## Required Evaluations

Record each evaluation that applies to the run. A result may be `pass`, `fail`, `not run`, or `not applicable`.

1. Database admission: confirm references came only from Microsoft-supported, manifest-listed solution artifacts.
2. Database refresh integrity: confirm the refresh report has zero errors and disclose warnings.
3. Sample-data readability: confirm the sample format parses and identify its record count and available fields.
4. ASIM compatibility: explain why each selected ASIM schema matches the sample and why plausible alternatives were not selected.
5. Reference relevance: explain why each selected Microsoft reference maps to a sample-data behavior, content type, or structure.
6. Reference exclusion: explain why materially considered references were not used when their ASIM schema fits but their scenario or data shape does not.
7. Source-field coverage: verify every field referenced by a generated artifact exists in the sample or was explicitly supplied by the user.
8. Source-binding status: identify whether the connector/table binding is provided, provisional, or unbound and its consequence for integration.
9. Requested-content coverage: compare requested counts to generated counts and explain omissions.
10. Scenario distinctness: explain why generated rules, hunts, and workbook views are not redundant.
11. Static validation: report the latest validation result and preserve any repair loop.
12. Behavior evaluation: when possible, replay thresholds or filters against representative sample data; otherwise state why it was not run.
13. Human and test-workspace gates: state KQL execution, workbook rendering, analyst review, and source-binding confirmation separately.

## When to Update

- After preflight: create the file and complete Step 0.
- After database refresh: update Step 1 with the actual refresh-report values.
- After classification and retrieval: update Step 2 before selecting source references.
- After selecting references and before writing content: update the selected and excluded references in Step 2, then complete the generation plan in Step 3.
- After each generated artifact batch: update the coverage and artifact-decision tables in Step 3.
- After every validation or repair attempt: append a row to Step 4. Never replace earlier failed results with a later passing result.
- Before the final response: complete Final Decision and link the decision log in the user-facing summary.