# Classify Sample Data and Retrieve References

These instructions are for the Sentinel Content Forge Accelerator agent. Run this stage only after the Microsoft Content Database refresh completed successfully.

## Purpose

Classify the user's submitted sample data using the categories in `database/taxonomy.yaml`. Use that category to retrieve relevant Microsoft-supported examples from the refreshed local database. The database already contains only content from solutions where `support.tier: Microsoft`; treat every retrieved record as a good reference example.

## Required Inputs

The required input is a path to representative sample data. Collect these additional facts when the user supplies them or they are directly available from an accompanying connector definition:

- Connector or product name, if known
- Sample-data format
- Requested content types: analytic rules, hunting queries, workbooks, or a subset
- Optional field descriptions and known security scenarios
- Optional connector ID and destination table or parser name

Normalize these facts into a request that follows `schemas/content-request.schema.json`. When connector and destination information is absent, set `sourceBinding.status` to `unbound`. This must not block classification or reference retrieval. Store the request with the run output before generating content.

## Categorization Actions

1. Read `database/taxonomy.yaml` and use only its category IDs.
2. Inspect the sample data, connector or product name when available, destination table or parser name when available, supplied field descriptions, and stated security scenarios.
3. Assign one primary category and, only when clearly useful, secondary categories.
4. Record a concise human-readable rationale based on observable sample-data signals. Do not calculate or report a numeric quality score. Write `classification.json` according to `schemas/classification.schema.json`.
5. If the sample data does not clearly fit a defined category, assign `unclassified`, report the closest possible categories, and ask the user to choose before generating content.

Examples of category signals:

- Source and destination addresses, ports, protocols, DNS values, proxy activity, or network actions commonly indicate `network`.
- Users, identities, sign-ins, login outcomes, MFA events, or directory activity commonly indicate `identity-authentication`.
- Database operation names, query text, database or collection names, and audit events commonly indicate `database-audit`.

ASIM parser or function names are useful category signals when available, but ASIM alignment is not required for the initial accelerator workflow.

## Retrieval Actions

Query the refreshed database once for each requested content type. Run from the repository root:

```powershell
python Tools/Sentinel-Content-Forge-Accelerator/scripts/query_database.py `
  --category <primary-category> `
  --content-type <analyticRule-or-huntingQuery-or-workbook> `
  --output Tools/Sentinel-Content-Forge-Accelerator/output/<run-id>/references-<content-type>.json
```

Use a conservative result limit. Start with up to 12 examples per content type. Read the original `sourcePath` files for the most relevant returned records before generating output.

If no records match the primary category for a requested content type:

1. Query any clearly relevant secondary category.
2. If no secondary category applies, report the gap and ask whether the user wants to proceed with broader Microsoft examples or restrict the request to the available content types.
3. Do not retrieve Partner or Community examples as a fallback.

## Output Requirements

Before generation, write the following in `output/<run-id>/`:

- `content-request.json`
- `classification.json`
- One `references-<content-type>.json` file for every requested content type

Tell the user the primary category, the rationale, and the source paths selected for reference. The next stage uses these records to draft new source-specific Sentinel content.

When `sourceBinding.status` is `unbound`, also state that connector and table identifiers will be derived as provisional draft bindings during generation. Do not ask the user for those identifiers before completing classification and database retrieval.