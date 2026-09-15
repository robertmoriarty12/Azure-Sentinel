# Classify Existing Content by ASIM

These instructions are for maintainers improving the confidence and precision of ASIM mappings in the Microsoft Content Database. Run this workflow only when explicitly asked to investigate a low- or medium-confidence mapping, an unexpected unmapped artifact, or a product or source family that needs a reviewed mapping rule.

## Purpose

Classify Microsoft-supported, manifest-listed content with official ASIM schema IDs. Do not use broad marketplace categories as retrieval labels. The database refresh assigns every analytic rule, hunting query, workbook, and parser a best-fit ASIM retrieval mapping with confidence. This workflow strengthens a deterministic best-effort mapping into an explicit or reviewed rule when the product, source table, and event family have sufficient evidence.

The approved mapping registry is:

```text
Tools/Sentinel-Content-Forge-Accelerator/database/asim-mapping-registry.yaml
```

Proposals are written under:

```text
Tools/Sentinel-Content-Forge-Accelerator/database/asim-mapping-proposals/
```

Do not add a mapping directly to the approved registry until its evidence and false-positive boundaries have been reviewed.

## Classification States

- `explicit`: The artifact directly uses an ASIM parser, ASIM schema tag, or source-specific ASIM parser name.
- `inferredFromRepository`: Local connector, table, parser, and source-content evidence establish the ASIM schema.
- `inferredFromOfficialProductDocumentation`: Official vendor documentation establishes the relevant log type or fields and supports an ASIM mapping after local repository evidence was insufficient.
- `inferredFromContent`: A deterministic retrieval label is inferred from source tables, fields, query text, titles, paths, entities, metadata, or content type. Its `retrievalConfidence` explains the strength of the signal; it does not claim ASIM normalization.
- `ambiguous`: More than one ASIM schema is plausible and the available evidence cannot choose one.
- `unmapped`: No meaningful ASIM schema or fallback can be established. Treat this as an investigation target, not the expected state for a retrieval-relevant artifact.
- `notApplicable`: The item is not telemetry content, such as a generic deployment-only playbook.

## Evidence Order

Investigate in this order. Stop when the evidence is sufficient; do not browse external documentation merely because it is available.

1. The original artifact at its `sourcePath`: KQL, YAML tags, title, description, entity mappings, dependencies, and workbook query items.
2. The owning solution manifest and data connector definitions.
3. Local ASIM parsers under `Parsers/ASim<Schema>/Parsers/`, including `Normalization.Schema`, `Product.Name`, parser source tables, and source selectors.
4. Local ASIM sample and parser test data under `Sample Data/ASIM/` and `Parsers/ASim<Schema>/Tests/`.
5. Official vendor product documentation only when the request enables product research or explicitly asks for it.

## Product Documentation Research

When product documentation lookup is enabled, use only official vendor documentation or documentation URLs supplied by the user. Use the product name and vendor name to find documentation about log types, event families, source tables, field meanings, or forwarding formats.

- Do not use product marketing pages as sole mapping evidence.
- Do not use third-party blogs, forum posts, copied rules, or search-result snippets as mapping evidence.
- Record the exact URL, a concise conclusion, and the fields or event type that support the ASIM schema.
- Treat documentation findings as a proposal until reviewed. Do not automatically alter the approved registry from a live documentation lookup.
- Add an `officialProductDocumentation` evidence item to the staged run's `classification.json` and `decision-log.md` when the conclusion affects a generation request.

## Proposal Workflow

1. Group low- or medium-confidence `inferredFromContent` artifacts and unexpected `unmapped` artifacts by product, connector, table or parser, and related source selector. Do not classify an entire product as one schema when its event types map to different schemas.
2. Identify the narrowest repeatable rule that maps the group. For example, Palo Alto PAN-OS traffic events in `CommonSecurityLog` with `Activity == "TRAFFIC"` map to `NetworkSession`; Palo Alto authentication events map separately to `Authentication`.
3. Create a proposal file named `<product-or-source>-<asim-schema>.md` using the template below.
4. Include positive examples and at least one nearby nonmatching example or exclusion condition.
5. After review, add the approved rule to `asim-mapping-registry.yaml` and rerun the database refresh. Keep the proposal as the decision record.

## Proposal Template

```markdown
# Proposed ASIM Mapping: <Product or Source> to <ASIM Schema>

## Conclusion

- Proposed schema: `<ASIM schema>`
- Proposed status: `<inferredFromRepository or inferredFromOfficialProductDocumentation>`
- Scope: `<solution paths, content types, source tables, and selectors>`

## Evidence

| Source | Reference | Observation |
|---|---|---|
| Local ASIM parser | `Parsers/...` | `<normalization schema and source-table/selectors>` |
| Local connector/content | `Solutions/...` | `<matching connector, data type, fields, or query predicate>` |
| Official product documentation | `https://...` | `<only when used>` |

## Positive Examples

| Artifact | Why it maps |
|---|---|
| `Solutions/...` | `<specific table, selector, or ASIM-compatible fields>` |

## Exclusions and False-Positive Boundaries

| Artifact or event family | Why it does not use this schema |
|---|---|
| `Solutions/...` | `<different event type, different ASIM schema, or insufficient evidence>` |

## Proposed Registry Rule

```yaml
id: <stable-id>
reviewState: proposed
mappingStatus: <status>
asimSchemas:
  - <ASIM schema>
match:
  solutionPaths:
    - Solutions/<solution>
  contentTypes:
    - analyticRule
  requiredText:
    - <required source table or selector>
evidence:
  - source: localAsimParser
    reference: Parsers/<ASIM parser path>
    conclusion: <why the mapping is valid>
```
```

## Output and Review Rules

- Every proposed mapping must include explicit false-positive boundaries, and only a reviewed rule promoted to `reviewState: approved` in `asim-mapping-registry.yaml` affects runtime classification.
- Each approved registry rule must match a narrow, reviewable source family. Avoid broad vendor-wide rules.
- A source with multiple event families requires separate mappings, even when the vendor and table are shared.
- Do not treat a low-confidence retrieval label as proof that a source uses an ASIM parser. Strengthen it with a narrow reviewed mapping when the evidence supports one.
- Record the mapping decision, evidence, exclusions, and review outcome in the relevant `decision-log.md` for generation runs.
- Rebuild and validate the Microsoft Content Database after approving any registry change.