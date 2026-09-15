# Generate Sentinel Content

These instructions are for the Sentinel Content Forge Accelerator agent. Run this stage after the database refresh and classify-and-retrieve stages completed successfully.

## Purpose

Generate review-ready Microsoft Sentinel content from the user's representative sample data and selected Microsoft Content Database references. The selected examples establish good Sentinel content patterns. The submitted sample-data fields establish what the generated content may reference. A provided or provisional source binding supplies the connector ID and destination table or parser used in staged output.

## Generation Boundaries

- Generate only the content types requested in `content-request.json`: analytic rules, hunting queries, workbooks, or a subset.
- Do not generate content until the current run contains nonempty `references-*.json` files retrieved from the Microsoft Content Database.
- Treat `decision-log.md` as a required narrative companion to `generation-evidence.json`. The evidence file records structured paths and fields; the decision log explains why each reference and scenario was chosen.
- When `sourceBinding.status` is `provided`, use its connector ID and destination table or parser exactly as supplied.
- When `sourceBinding.status` is `unbound`, derive a local provisional connector ID and table or parser name from the sample-data product label. Set the status to `provisional` and record the rationale in `content-request.json` before generating content.
- A provisional binding is a local draft identifier, not a claim about a deployed Sentinel connector, table, or parser. Do not use it outside the staged run output.
- Do not invent a source field or event value. Do not claim a raw source uses an ASIM parser unless the input or approved mapping evidence establishes that parser relationship. Provisional connector and data-source names are the only permitted derived identifiers.
- Use an ASIM parser in generated KQL only when the source has explicit ASIM evidence or an approved inferred mapping. A raw sample classified only as `compatible` must use its source table or provisional data source in generated KQL.
- For `compatible` raw sample data, record that the ASIM parser must be confirmed before producing source-agnostic ASIM content or integrating the staged output into a solution.
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

## Decision Log Update

Before writing generated artifacts, update Step 3 in `decision-log.md` with the source-binding decision, requested artifact counts, planned artifact names, chosen scenarios, required sample-data fields, and selected Microsoft references.

After writing generated artifacts, update the same section with:

1. Requested versus generated counts for analytic rules, hunting queries, and workbooks.
2. Every generated artifact path, its scenario, the exact sample-data fields it uses, and the Microsoft references used to inform it.
3. A source-field coverage result confirming that all generated query fields exist in the sample data or were explicitly supplied by the user.
4. A binding-consistency result confirming the provided or provisional connector ID and data source are used consistently.
5. A distinctness result explaining why generated artifacts do not duplicate one another.
6. Any scenario omitted because the input did not contain sufficient fields or meaningful event behavior.
7. An originality statement explaining how the generated output adapts selected patterns without copying a full reference artifact.

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
- Keep the workbook focused on investigation and operational visibility for the compatible ASIM schema or schemas.

Use `.github/instructions/workbook.instructions.md` as the governing format and quality guidance.

## Completion Boundary

Generation is complete only when the staged files, content request, classification, selected references, and generation evidence exist together in the same run directory. The content remains unapproved until the validation stage reports no hard failures, a human completes the required review, and any provisional source binding is confirmed or replaced with actual connector and destination information.