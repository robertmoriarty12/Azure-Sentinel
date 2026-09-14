# Generate Sentinel Content

These instructions are for the Sentinel Content Forge Accelerator agent. Run this stage after the database refresh and classify-and-retrieve stages completed successfully.

## Purpose

Generate review-ready Microsoft Sentinel content from the user's representative sample data and selected Microsoft Content Database references. The selected examples establish good Sentinel content patterns. The submitted sample-data fields establish what the generated content may reference. A provided or provisional source binding supplies the connector ID and destination table or parser used in staged output.

## Generation Boundaries

- Generate only the content types requested in `content-request.json`: analytic rules, hunting queries, workbooks, or a subset.
- Do not generate content until the current run contains nonempty `references-*.json` files retrieved from the Microsoft Content Database.
- When `sourceBinding.status` is `provided`, use its connector ID and destination table or parser exactly as supplied.
- When `sourceBinding.status` is `unbound`, derive a local provisional connector ID and table or parser name from the sample-data product label. Set the status to `provisional` and record the rationale in `content-request.json` before generating content.
- A provisional binding is a local draft identifier, not a claim about a deployed Sentinel connector, table, or parser. Do not use it outside the staged run output.
- Do not invent a source field, event value, or ASIM mapping. Provisional connector and data-source names are the only permitted derived identifiers.
- Use the selected Microsoft examples to learn relevant security scenarios, content structure, KQL style, MITRE mapping patterns, entity mapping patterns, and workbook design patterns.
- Do not copy an entire source artifact. Produce original content tailored to the submitted data.
- Do not use Partner or Community examples.
- Do not write generated content into `Solutions` or change a solution manifest. Write only to the staged run output directory.
- Generate distinct artifacts. Do not produce near-duplicate rules, hunts, or workbook queries.
- If the sample data cannot support a meaningful requested scenario, explain the missing fields and omit that artifact rather than fabricating it.

## Required Actions

1. Read `content-request.json`, `classification.json`, and all `references-*.json` files for the current run. Stop and report the missing retrieval artifact if any requested content type has no selected Microsoft references.
2. Open the original `sourcePath` files for selected references that best match the incoming data shape and requested content type.
3. Inspect `sourceBinding` in `content-request.json`. Use a provided binding unchanged. If it is unbound, derive a provisional binding, record its rationale, and save the updated request before creating any YAML or JSON.
4. Create a concise generation plan that names every proposed artifact, its purpose, required source fields, expected MITRE tactic or techniques when applicable, the source-binding status, and the reference paths informing it.
5. Verify each required source field exists in the submitted sample data or has a supplied field description before generating the artifact.
6. Generate artifacts into these directories:

   ```text
   output/<run-id>/content/Analytic Rules/
   output/<run-id>/content/Hunting Queries/
   output/<run-id>/content/Workbooks/
   ```

7. Create `generation-evidence.json` according to `schemas/generation-evidence.schema.json`. Map every generated file to the selected reference source paths and the sample-data fields it uses.
8. Continue directly to the validation stage after generation.

## Analytic Rules

For each analytic rule:

- Use a unique GUID for `id`.
- Include a clear sentence-case `name`, a concise ASCII `description`, valid `severity`, `status`, `kind`, and semantic `version`.
- Declare the provided or provisional connector ID and data source together in `requiredDataConnectors`.
- Use valid MITRE tactics and techniques that match the behavior, not merely the product category.
- Return columns needed by the entity mappings and include at least one useful investigation entity when the source data supports it.
- For scheduled rules, include a valid query frequency, query period, trigger operator, and trigger threshold.
- Write KQL that references only the supplied data source and supported source fields.

Use `.github/instructions/detections.instructions.md` as the governing format and quality guidance.

## Hunting Queries

For each hunting query:

- Use a unique GUID for `id` and a semantic `version`.
- Declare the provided or provisional connector ID and data source together in `requiredDataConnectors`.
- Use valid MITRE tactics and techniques that match the hunt.
- Return investigation-ready fields and entity mappings when supported by the submitted data.
- Write original KQL that references only the supplied data source and supported source fields.

Use `.github/instructions/huntingqueries.instructions.md` as the governing format and quality guidance.

## Workbooks

For each workbook:

- Use `version: Notebook/1.0` and the required workbook schema URL.
- Use a unique `fromTemplateId` that begins with `sentinel-`.
- Include a useful time-range parameter and multiple purposeful query or visualization items when the data supports them.
- Query only the submitted data source and fields that the sample data supports.
- Keep the workbook focused on investigation and operational visibility for the classified category.

Use `.github/instructions/workbook.instructions.md` as the governing format and quality guidance.

## Completion Boundary

Generation is complete only when the staged files, content request, classification, selected references, and generation evidence exist together in the same run directory. The content remains unapproved until the validation stage reports no hard failures, a human completes the required review, and any provisional source binding is confirmed or replaced with actual connector and destination information.