# Sentinel Content Forge Accelerator Instructions

These instructions are for a GitHub Copilot agent. Load this file when a user asks to generate Microsoft Sentinel content from representative sample data.

## Purpose

Use the local Azure-Sentinel repository to refresh the Microsoft Content Database, determine the ASIM schema compatibility of the user's data, retrieve relevant Microsoft-supported examples by ASIM schema, generate source-specific Sentinel content, and validate the staged output.

The user has already cloned the Azure-Sentinel repository. Do not clone the repository, deploy Azure resources, run `git pull`, switch branches, or modify files under `Solutions`.

## Required User Prompt

The only required input is a path to representative sample data.

The user may also provide a connector ID, a destination table or parser name, and requested content types. If content types are not specified, default to one analytic rule, one hunting query, and one workbook.

Do not block database refresh, sample-data classification, or reference retrieval when connector and destination information is absent. Create `content-request.json` with one of these source-binding states:

- `provided`: The user supplied a connector ID and destination table or parser.
- `unbound`: The user supplied sample data only. This is valid for database refresh, classification, and reference retrieval.
- `provisional`: The agent derived local draft identifiers from the sample-data name after retrieval. These identifiers are for staged content only and require later confirmation before a solution integration or pull request.

Do not present a provisional connector ID or data source as an actual deployed Sentinel connector or table.

## Workflow

Complete the stages in order. Do not skip database refresh, do not generate output before retrieval, and do not present generated output as publish-ready before validation and human review.

Before preflight, create a unique run ID using this format:

```text
YYYYMMDD-HHMMSS-<short-product-slug>
```

Write all run artifacts under:

```text
Tools/Sentinel-Content-Forge-Accelerator/output/<run-id>/
```

### Decision Log

Load and follow `Tools/Sentinel-Content-Forge-Accelerator/instructions/document-run-decisions.md` throughout the run. Create `decision-log.md` in the run directory before preflight, then update it after every stage and validation or repair attempt.

The decision log is the human-readable account of the run. It must record observable inputs, database refresh results, classification rationale, matching versus selected reference counts, selected and materially considered-but-not-used Microsoft reference paths, generation choices, evaluation outcomes, repairs, and remaining gates. Do not include hidden reasoning or claim unperformed checks.

### Preflight: Verify Python Dependencies

Before Stage 1, verify that Python can import `yaml` and `jsonschema`. If either import fails, install only the accelerator dependencies from the repository root:

```powershell
python -m pip install -r Tools/Sentinel-Content-Forge-Accelerator/requirements.txt
```

Verify the imports again before continuing. Do not install unrelated packages.

### Stage 1: Refresh the Microsoft Content Database

Load and follow `Tools/Sentinel-Content-Forge-Accelerator/instructions/update-microsoft-content-database.md`.

The database must include only manifest-listed assets from solutions whose `SolutionMetadata.json` has `support.tier: Microsoft`. Treat Microsoft support tier as the v1 admission rule for good reference examples. Every analytic rule, hunting query, workbook, and parser must receive one or more best-fit ASIM retrieval schemas with evidence and `retrievalConfidence`; deployment playbooks remain `notApplicable`. ASIM schemas organize and retrieve the database; they do not decide whether content is good or claim that every source is ASIM normalized.

Stop if database refresh reports errors or produces no records.

Update Step 1 in `decision-log.md` with the refresh-report values and the decision to proceed or stop.

### Stage 2: Classify Sample Data and Retrieve References

Load and follow `Tools/Sentinel-Content-Forge-Accelerator/instructions/classify-and-retrieve.md`.

Update Step 2 in `decision-log.md` with the ASIM compatibility decision, mapping status, classification evidence, considered ASIM alternatives, retrieval counts, and selected versus considered-but-not-used reference paths. For every selected database reference, record its mapping status and retrieval confidence. Prefer exact, high, and medium-confidence references; use a low-confidence reference only when its source fields and security scenario demonstrably fit the submitted sample data.

If sample data is `unmapped` or `ambiguous` to ASIM, stop and explain the local evidence gap. Offer official product-documentation research only when the user has enabled it in `context.productResearch` or explicitly asks for it. For approved research, load `instructions/classify-existing-asim-content.md`, use only official vendor documentation or user-supplied official URLs, log the evidence and conclusion, and create a reviewable proposal. Do not automatically alter `database/asim-mapping-registry.yaml` or use Partner or Community content as a fallback.

### Stage 3: Generate Sentinel Content

Load and follow `Tools/Sentinel-Content-Forge-Accelerator/instructions/generate-sentinel-content.md`.

Use the original repository files referenced by the selected database records. The selected Microsoft examples inform content patterns and security scenarios. The submitted sample data determines the source fields the generated content may use. A provided or provisional source binding supplies the connector ID and data source used in staged YAML and JSON output.

When `sourceBinding.status` is `unbound`, derive a clearly labeled provisional connector ID and table or parser name from the sample-data product label. Update the current run's `content-request.json` to `provisional` before generating artifacts. Generate only requested artifact types and counts. Write all output to the current run directory, not to `Solutions`.

Update Step 3 in `decision-log.md` before generating content with the binding decision and content plan. Update it again after generation with generated paths, field coverage, reference use, content coverage, distinctness, and omitted scenarios.

### Stage 4: Validate and Repair

Load and follow `Tools/Sentinel-Content-Forge-Accelerator/instructions/validate-sentinel-content.md`.

Repair deterministic validation failures in the generated run output and rerun validation. Do not edit reference examples, the database policy, taxonomy, or files under `Solutions` to make validation pass.

Update Step 4 in `decision-log.md` after every validation or repair attempt. Preserve earlier failures and repairs rather than replacing them with a later result.

## Final Response

Report:

1. The database refresh summary: Microsoft-supported solutions, indexed artifacts, warnings, and errors.
2. The sample-data ASIM schemas, mapping status, and rationale.
3. Every selected Microsoft reference path, ASIM mapping status, retrieval confidence, and the source evidence that made it relevant.
4. Every generated artifact path and its purpose.
5. Validation status, including failed checks, warnings, and checks not run.
6. Source-binding status and, when provisional, the connector ID and data source that require confirmation.
7. The remaining human or test-workspace actions required before the content can move into a solution or pull request.
8. The path to `decision-log.md` and its final run decision.

## Safety and Scope Rules

- Never update `database/baseline` during an ordinary user request.
- Never treat user sample data as an entry in the Microsoft Content Database.
- Never copy an entire reference artifact; generate original source-specific content.
- Never automatically copy output into a solution package, update a solution manifest, or create a pull request.
- Never claim KQL execution or workbook rendering passed unless the agent actually ran the relevant test.
- Never claim staged content with a provisional source binding is package-ready or ready for solution integration.