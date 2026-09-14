# Validate Sentinel Content

These instructions are for the Sentinel Content Forge Accelerator agent. Run this stage after generating content in a staged run directory.

## Purpose

Validate generated analytic rules, hunting queries, and workbooks before presenting them as review-ready. The static validator checks format, required fields, bound connector and data-source dependencies, MITRE field formats, entity mapping structure, and basic workbook structure. It does not execute KQL or render a workbook, so human and environment-based review remain required.

## Required Actions

1. Identify the current run directory under `Tools/Sentinel-Content-Forge-Accelerator/output/<run-id>/`.
2. Confirm that `content-request.json` exists in the run directory.
3. Run the static validator from the repository root:

   ```powershell
   python Tools/Sentinel-Content-Forge-Accelerator/scripts/validate_output.py `
     --input Tools/Sentinel-Content-Forge-Accelerator/output/<run-id>/content `
     --request Tools/Sentinel-Content-Forge-Accelerator/output/<run-id>/content-request.json `
     --report Tools/Sentinel-Content-Forge-Accelerator/output/<run-id>/validation-report.json
   ```

4. Read `validation-report.json` and summarize its overall status, artifact count, passed checks, warning checks, failed checks, and checks not run.
5. When the report contains failed checks, repair only the affected generated artifacts. Do not alter the Microsoft Content Database, source examples, repository instructions, or files under `Solutions`.
6. Rerun the same validation command after each repair until no failed checks remain or the agent needs user input.
7. When no failures remain, identify the checks marked `notRun` and tell the user what test-workspace or human review is still needed.
8. Check `sourceBinding.status` in `content-request.json`. When it is `provisional`, explicitly identify the derived connector ID and data source as requiring confirmation before solution integration. When it is `unbound`, do not claim dependency validation was performed.

## Validation Interpretation

- `failed`: The artifact has a deterministic defect and is not ready for review. Repair it before delivery.
- `passedWithWarnings`: The artifact passed hard checks but has a quality or convention warning. Explain it clearly to the user and consider a targeted repair.
- `needsReview`: No hard static failure remains, but KQL execution, workbook rendering, or analyst usefulness still requires review. This is the expected result for most generated content.
- A provisional or unbound source binding also produces `needsReview`. The agent can use sample data to classify and retrieve good references without a connector ID, but a real solution integration requires an actual connector and destination table or parser.
- `passed`: All implemented checks passed and no further manual gate is recorded. This does not authorize automatic publication.

## Repair Rules

- Use the report's check IDs, messages, and details as the repair input.
- Do not suppress a failed check by deleting an artifact, weakening the validator, or changing the request to match incorrect output.
- Do not claim KQL is valid merely because it is present. Run it against representative sample data or a test workspace when one is available.
- Do not claim a workbook is usable merely because its JSON parses. Open it in a test workspace and review its parameters, visualizations, and no-data behavior.
- Do not replace a provisional binding with guessed production identifiers. Obtain them from the user or an actual connector definition before moving staged output into a solution.
- Preserve the selected reference paths and generation evidence when repairing content so reviewers can trace the artifact back to the Microsoft examples and sample-data fields.

## Governing Repository Guidance

Apply the relevant existing repository guidance while repairing:

- `.github/instructions/detections.instructions.md`
- `.github/instructions/huntingqueries.instructions.md`
- `.github/instructions/workbook.instructions.md`

## Completion Boundary

The accelerator may label output as review-ready only when:

1. `validation-report.json` contains zero failed checks.
2. The report, selected references, classification, content request, and generation evidence are present in the run directory.
3. The final user summary lists every remaining `notRun` review or execution gate.

Generated content must remain in the staged output directory until a human approves moving it into a real Sentinel solution or pull request.