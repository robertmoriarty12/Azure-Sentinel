# Microsoft Content Database Baseline

This directory contains the checked-in baseline of Microsoft-supported Sentinel content used by the accelerator immediately after a repository clone.

The baseline is generated from the local `Solutions` directory using these rules:

1. A solution is included only when its `SolutionMetadata.json` declares `support.tier: Microsoft`.
2. An artifact is included only when it is listed by that solution's `Data/Solution_*.json` manifest.
3. ASIM schema classifications organize references for retrieval. Each record records canonical `asimSchemas`, `mappingStatus`, `retrievalConfidence`, and supporting `asimEvidence`; these fields do not affect whether Microsoft-supported content is included as a good example.

The files in this directory are:

- `microsoft-content-database.jsonl`: one normalized reference record per eligible artifact.
- `refresh-report.json`: snapshot counts, warnings, and errors from the generation run.

## Maintainer Refresh

Run this command from the Azure-Sentinel repository root when intentionally updating the checked-in baseline:

```powershell
python Tools/Sentinel-Content-Forge-Accelerator/scripts/refresh_database.py `
  --repo-root <repository-root> `
  --output Tools/Sentinel-Content-Forge-Accelerator/database/baseline/microsoft-content-database.jsonl `
  --report Tools/Sentinel-Content-Forge-Accelerator/database/baseline/refresh-report.json
```

Review the report and the database diff before committing a new baseline. Do not use this command during an ordinary content-generation request; normal requests refresh only `database/runtime`.

Use the approved ASIM mappings in `../asim-mapping-registry.yaml` during a refresh. After direct and reviewed evidence, use the deterministic inference rules in `../taxonomy.yaml` to assign every analytic rule, hunting query, workbook, and parser a best-fit retrieval schema and confidence. This classification supports lookup; it does not assert that each source is ASIM normalized. Playbooks remain `notApplicable`. Official product-documentation research may produce a proposal, but only a reviewed `reviewState: approved` mapping affects a future baseline refresh.