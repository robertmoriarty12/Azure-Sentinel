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
9. Confirm that each analytic-rule format matches its delivery audience: YAML for ISV solution publication, ARM deployment-template JSON for direct customer deployment, or both when dual delivery was requested.
10. For standalone ARM analytic rules, fail validation when `templateVersion` is present without a nonempty `alertRuleTemplateName`. Confirm ARM durations, trigger enums, resource identifiers, and embedded KQL use the deployment API representation.
11. When the sample-data shape differs from the target Log Analytics table, verify every KQL field against the target table schema. Treat raw API field casing or nested paths carried directly into a workspace query as a defect unless the target schema confirms them.
12. For every analytic rule, evaluate the behavior contract recorded during generation. Use KQL execution in a test workspace when available. Otherwise, replay equivalent filter, threshold, grouping, and ordering semantics against representative data and state clearly that the replay is not KQL execution.
13. Include positive, negative, and boundary cases in the behavior evaluation. At minimum test the expected scenario, threshold minus one, threshold exactly, a different grouping key, reversed event order for sequence rules, a related but excluded event type, and an event outside the correlation window. Add rule-specific cases needed to challenge every material claim in the name and description.
14. Record expected alerts, observed alerts, false positives, false negatives, and the result of each case in `behavior-evaluation.md`. Preserve failing cases and subsequent repairs.
15. Review every analytic-rule ATT&CK mapping against the current official technique page. Confirm that the tactic and technique are supported by observable query conditions, and record the URL, review date, supporting conditions, and telemetry limitations. Do not infer downstream techniques from contextual events the rule does not actually detect.
16. For scheduled rules where `queryPeriod` exceeds `queryFrequency`, confirm suppression or a stable episode key, or record repeated alerts as an accepted operational risk. Treat `semantic.schedule-overlap` as requiring an explicit decision, not as a formatting-only warning.
17. Update Step 4 in `decision-log.md` after every static validation, behavior evaluation, ATT&CK review, repair, deployment attempt, or rerun. Include validation counts, case results, artifact-specific failures or warnings, evaluation method, observed result, and remaining review gates.

## Validation Interpretation

- `failed`: The artifact has a deterministic defect and is not ready for review. Repair it before delivery.
- `passedWithWarnings`: The artifact passed hard checks but has a quality or convention warning. Explain it clearly to the user and consider a targeted repair.
- `needsReview`: No hard static failure remains, but KQL execution, workbook rendering, or analyst usefulness still requires review. This is the expected result for most generated content.
- A provisional or unbound source binding also produces `needsReview`. The agent can use sample data to classify and retrieve good references without a connector ID, but a real solution integration requires an actual connector and destination table or parser.
- `passed`: All implemented checks passed and no further manual gate is recorded. This does not authorize automatic publication.

When the static validator cannot run or does not produce `validation-report.json`, record the run itself as `staged-incomplete`. Do not substitute editor diagnostics, JSON/YAML parsing, or behavior replay for the missing report, and do not describe the run as review-ready.

## Repair Rules

- Use the report's check IDs, messages, and details as the repair input.
- Do not suppress a failed check by deleting an artifact, weakening the validator, or changing the request to match incorrect output.
- Do not claim KQL is valid merely because it is present. Run it against representative sample data or a test workspace when one is available.
- Do not treat a positive sample match as sufficient behavior validation. Exercise negative and boundary cases that could falsify the rule's name, description, thresholds, grouping, or event ordering.
- Do not treat a syntactically valid ATT&CK ID as evidence that the query observes the technique. Preserve a behavior-specific mapping rationale and qualify claims when the telemetry cannot prove a defining characteristic.
- Do not claim a workbook is usable merely because its JSON parses. Open it in a test workspace and review its parameters, visualizations, and no-data behavior.
- Do not replace a provisional binding with guessed production identifiers. Obtain them from the user or an actual connector definition before moving staged output into a solution.
- Do not assume a representative API export is already shaped like its target Log Analytics table. Validate table name, column casing, nested dynamic properties, and result semantics against the target schema.
- Do not add `templateVersion` to a standalone ARM analytic rule. It is valid only when paired with a nonempty `alertRuleTemplateName`.
- Preserve the selected reference paths and generation evidence when repairing content so reviewers can trace the artifact back to the Microsoft examples and sample-data fields.
- Preserve the first failing validation result in `decision-log.md`, describe the repair decision, and append the subsequent validation result. Do not rewrite history to show only the final pass.

## Governing Repository Guidance

Apply the relevant existing repository guidance while repairing:

- `.github/instructions/detections.instructions.md`
- `.github/instructions/huntingqueries.instructions.md`
- `.github/instructions/workbook.instructions.md`

## Completion Boundary

The accelerator may label output as review-ready only when:

1. `validation-report.json` contains zero failed checks.
2. The report, selected references, classification, content request, and generation evidence are present in the run directory.
3. Every analytic rule has a behavior evaluation with positive, negative, and boundary cases, and every observed result matches its expectation or is preserved as an unresolved failure.
4. Every analytic-rule ATT&CK mapping has behavior-specific evidence from the query and the official technique page.
5. The final user summary lists every remaining `notRun` review or execution gate.
6. `decision-log.md` documents the final status, decisions, evaluations, repairs, and remaining review gates.

Generated content must remain in the staged output directory until a human approves moving it into a real Sentinel solution or pull request.