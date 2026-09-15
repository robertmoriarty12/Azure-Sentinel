# Refresh the Microsoft Content Database

These instructions are for the Sentinel Content Forge Accelerator agent. Run this stage before classifying sample data or generating any Sentinel content.

## Purpose

Refresh the local Microsoft Content Database from the current `Solutions` directory in the user's cloned Azure-Sentinel repository. The database contains only manifest-listed artifacts from solutions whose `SolutionMetadata.json` declares `support.tier: Microsoft`.

Microsoft support tier is the only admission rule for v1. Every manifest-listed artifact from a Microsoft-supported solution is treated as a good reference example. ASIM schema mappings organize reference examples for retrieval; they do not include or exclude content from the database.

## Required Actions

1. Determine the repository root. It is the directory containing both `Solutions` and `Tools/Sentinel-Content-Forge-Accelerator`.
2. Run the refresh script from the repository root:

   ```powershell
   python Tools/Sentinel-Content-Forge-Accelerator/scripts/refresh_database.py --repo-root <repository-root>
   ```

3. Read `Tools/Sentinel-Content-Forge-Accelerator/database/runtime/refresh-report.json`.
4. Confirm that the report has zero errors and that the runtime database exists at `Tools/Sentinel-Content-Forge-Accelerator/database/runtime/microsoft-content-database.jsonl`.
5. Confirm that `classification.mappedRecords` covers every non-playbook record and that every playbook has `mappingStatus: notApplicable`. Investigate any unexpected `unmapped` record before continuing.
6. Report the number of Microsoft-supported solutions, indexed artifacts, warnings, errors, mapping-status counts, and retrieval-confidence counts in the next response to the user.
7. Continue to the classify-and-retrieve stage only when the refresh completed successfully, produced a nonempty runtime database, and has usable mapped reference coverage.
8. Update Step 1 in the current run's `decision-log.md` with the source root, Microsoft-supported solution count, manifest count, indexed artifact count, warnings grouped by kind, error count, mapping-status counts, retrieval-confidence counts, and the decision to proceed or stop.

## Refresh Rules

- Use the user's local checkout as the source of truth. Do not run `git pull`, switch branches, stash changes, or modify files under `Solutions`.
- Do not add user-provided sample data to the Microsoft Content Database.
- Do not add Partner or Community content, even when it appears relevant to the submitted sample data.
- Do not add source files merely because they appear in a solution folder. Only index files listed in a qualifying solution manifest.
- Preserve workspace-relative source paths so that the agent can open the original examples later.
- Apply the deterministic retrieval inference in `database/taxonomy.yaml` after direct parser/tag evidence and approved mapping-registry evidence. It must create a best-fit ASIM retrieval mapping for every analytic rule, hunting query, workbook, and parser.
- Preserve `mappingStatus`, `retrievalConfidence`, and concrete evidence on each database record. Low confidence means the label is a weak retrieval signal, not an ASIM normalization claim.
- Treat missing manifest-listed files as warnings and do not fabricate database records for them.
- Treat malformed metadata or manifests as refresh errors. Stop the generation workflow and explain the error rather than silently using an incomplete refresh.
- Do not modify `database/baseline` during a normal user request. The baseline is updated only by a maintainer's explicit request.
- Do not modify `selection-policy.yaml` or `taxonomy.yaml` merely to classify an incoming user sample.

## Refresh Result

The runtime database is a local working artifact. It is intentionally ignored by Git and can be regenerated from the local `Solutions` directory on every request. Use it for retrieval during the current request, then retain the source paths in the generated request evidence.

The decision log must distinguish refresh warnings from errors and state why warnings did or did not block the run. Do not paste all warning records; report grouped counts and name only warnings that changed a decision.