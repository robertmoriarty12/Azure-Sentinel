# Determine ASIM Compatibility and Retrieve References

These instructions are for the Sentinel Content Forge Accelerator agent. Run this stage only after the Microsoft Content Database refresh completed successfully.

## Purpose

Determine which ASIM schema or schemas the user's submitted sample data can support, using `database/taxonomy.yaml`. Use compatible ASIM schemas to retrieve relevant Microsoft-supported examples from the refreshed local database. The database already contains only content from solutions where `support.tier: Microsoft`; treat every retrieved record as a good reference example, but use its mapping status, confidence, and evidence to judge how directly it fits the sample.

## Required Inputs

The required input is a path to representative sample data. Collect these additional facts when the user supplies them or they are directly available from an accompanying connector definition:

- Connector or product name, if known
- Sample-data format
- Requested content types: analytic rules, hunting queries, workbooks, or a subset
- Optional field descriptions and known security scenarios
- Optional connector ID and destination table or parser name

Normalize these facts into a request that follows `schemas/content-request.schema.json`. When connector and destination information is absent, set `sourceBinding.status` to `unbound`. This must not block classification or reference retrieval. Store the request with the run output before generating content.

## ASIM Compatibility Actions

1. Read `database/taxonomy.yaml` and use only its canonical ASIM schema IDs.
2. Inspect the sample data, connector or product name when available, destination table or parser name when available, supplied field descriptions, and stated security scenarios.
3. Record one or more ASIM schemas only when the sample exposes sufficient schema-specific fields and event semantics.
4. Set `mappingStatus` to `compatible` when raw sample data can map to ASIM, `explicit` only when an ASIM parser or schema declaration is already supplied, `ambiguous` when more than one schema is equally plausible, and `unmapped` when no schema is defensible.
5. Record a concise human-readable rationale and evidence based on observable signals. Do not calculate or report a numeric quality score. Write `classification.json` according to `schemas/classification.schema.json`.
6. If the sample data is `unmapped` or `ambiguous`, stop before generation. Explain the local evidence gap and offer official product-documentation research only when the user has enabled it or explicitly asks for it.

Examples of ASIM compatibility signals:

- Source and destination addresses, ports, protocols, and network actions commonly indicate `NetworkSession`.
- DNS queries, response codes, and DNS servers commonly indicate `Dns`.
- Users, identities, sign-ins, login outcomes, MFA events, or directory activity commonly indicate `Authentication`.
- User creation, deletion, membership, role, or permission changes commonly indicate `UserManagement`.
- Process start or termination, file, and registry activities commonly indicate `ProcessEvent`, `FileEvent`, or `RegistryEvent`.
- Security-alert summary records commonly indicate `AlertEvent`. Do not choose `AlertEvent` when the source exposes detailed network, authentication, or process data that fits a specialized ASIM schema.

A raw source can be `compatible` with an ASIM schema without currently using an ASIM parser. Do not label it `explicit` unless the submitted data, connector, or parser directly declares the ASIM parser or schema.

When local sample, connector, and parser evidence is insufficient, inspect `context.productResearch`. If `allowOfficialProductDocumentationLookup` is true or the user explicitly asks for product research, load and follow `instructions/classify-existing-asim-content.md`. Use only official vendor documentation, record the conclusion and URL as evidence, and create a reviewable proposal. Do not automatically add documentation-derived mappings to the approved registry.

## Retrieval Actions

Query the refreshed database once for each requested content type and compatible ASIM schema. Run from the repository root:

```powershell
python Tools/Sentinel-Content-Forge-Accelerator/scripts/query_database.py `
  --asim-schema <ASIM-schema> `
  --content-type <analyticRule-or-huntingQuery-or-workbook> `
  --output Tools/Sentinel-Content-Forge-Accelerator/output/<run-id>/references-<content-type>.json
```

Use a conservative result limit. Start with up to 12 examples per content type. Read the original `sourcePath` files for the most relevant returned records before generating output.

The result order is deliberate: direct ASIM mappings first, reviewed repository or product-documentation mappings next, then best-effort content mappings from high through low confidence. Select the smallest set of references that has both a relevant security scenario and source-field shape. A low-confidence reference may provide a useful structural pattern, but it cannot by itself justify an ASIM parser claim or a source-field assumption.

If no records match a compatible ASIM schema for a requested content type:

1. Query another compatible ASIM schema when the sample has one.
2. If no additional schema applies, report the gap and ask whether the user wants to proceed with schema-compatible Microsoft examples from a different requested content type or defer that artifact.
3. Do not retrieve Partner or Community examples as a fallback.

## Output Requirements

Before generation, write the following in `output/<run-id>/`:

- `content-request.json`
- `classification.json`
- One `references-<content-type>.json` file for every requested content type
- Updated `decision-log.md` sections for classification, retrieval, and reference selection

Tell the user the compatible ASIM schemas, mapping status, rationale, and the source paths selected for reference. The next stage uses these records to draft new source-specific Sentinel content.

When `sourceBinding.status` is `unbound`, also state that connector and table identifiers will be derived as provisional draft bindings during generation. Do not ask the user for those identifiers before completing classification and database retrieval.

## Decision Log Update

Update Step 2 in `decision-log.md` after ASIM compatibility assessment and after reference selection:

1. Record the ASIM schemas, mapping status, observed evidence, and plausible schemas considered but not selected.
2. For each requested content type, record the ASIM schema query, matching-record count, returned-record count, selected-for-generation count, and confidence distribution of selected references.
3. List every Microsoft reference path selected for generation, its mapping status, retrieval confidence, the artifact or pattern it informs, and a concrete reason it fits the sample-data behavior or data shape.
4. List materially considered references that were not used when they were ASIM-schema matches but lacked a relevant scenario, used unavailable source fields, or duplicated a stronger selected pattern.
5. State whether ASIM-schema retrieval produced an exact scenario match or whether the agent selected references for structural and content-format patterns while deriving the security scenario from the sample data.

Do not list an unselected database record as a generation reference. Do not use ASIM schema membership alone as the reason a reference was selected.