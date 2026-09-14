# Sentinel Content Forge Accelerator

The Sentinel Content Forge Accelerator helps a user turn representative connector data into review-ready Microsoft Sentinel content. It uses Microsoft-supported solution content in the local Azure-Sentinel repository as a database of reference examples.

The accelerator is designed for a user who has already cloned the Azure-Sentinel repository. It does not deploy Azure resources, create a Function App, or automatically modify an existing solution.

## User Workflow

1. The user opens the cloned Azure-Sentinel repository in VS Code.
2. The user provides a path to representative sample data. Connector and destination table or parser details are optional at this stage.
3. The root agent instructions refresh the Microsoft Content Database from the local `Solutions` directory.
4. The accelerator classifies the submitted data, retrieves category-matched Microsoft examples, and creates a content plan.
5. The agent generates analytic rules, hunting queries, and optionally workbooks in a staged output directory. When no real connector or data source is provided, it uses a clearly labeled provisional binding derived from the sample-data name.
6. The accelerator validates the generated artifacts, provides structured repair feedback, and produces a review report.

Use this prompt in GitHub Copilot Chat:

```text
Load and follow Tools/Sentinel-Content-Forge-Accelerator/agent-instructions.md.
My sample data is at <sample-data-path>. Generate <requested-content-types>.
```

For a source-specific integration, add the connector ID and destination table or parser to the prompt. Without them, the accelerator can still classify the data, retrieve Microsoft-supported references, and generate staged drafts with a provisional binding that must be confirmed before solution integration.

## Requirements

The accelerator requires Python 3.10 or later and the packages declared in `requirements.txt`. The root agent instructions verify these dependencies before the first database refresh. To prepare the environment manually, run this command from the repository root:

```powershell
python -m pip install -r Tools/Sentinel-Content-Forge-Accelerator/requirements.txt
```

## Microsoft Content Database

The accelerator ships with a baseline Microsoft Content Database. The database is an index of vetted reference examples, not a copy of all Sentinel content. Each record points to the original repository file and stores structured attributes used for retrieval.

On every content-generation request, the accelerator refreshes a local working database from the user's current checkout:

1. Scan `Solutions/*/SolutionMetadata.json`.
2. Include only solutions where `support.tier` is `Microsoft`.
3. Read each qualifying `Data/Solution_*.json` manifest.
4. Index only content files listed by that manifest.
5. Categorize indexed records using the shared accelerator taxonomy.
6. Write the refreshed working database and a refresh report.

The checked-in baseline allows the accelerator to work immediately after cloning. The local working database captures changes in the user's current checkout without causing normal accelerator use to modify tracked repository files. The accelerator never runs `git pull` or changes the user's branch.

Eligibility is evaluated from `SolutionMetadata.json` in the current checkout, so approved Microsoft-supported solution changes on the user's branch are included when they are listed in the solution manifest. User-submitted sample data is used only to classify and generate content; it is never added to the Microsoft Content Database.

## Database Categories

The initial taxonomy is intentionally small and will evolve through reviewed changes:

- Network
- Identity and authentication
- Endpoint
- Cloud and SaaS
- Database and audit
- Email and collaboration
- Data security
- Threat intelligence
- Security operations

Each database record can have a primary category and secondary categories. Raw solution metadata categories and ASIM signals are preserved separately from accelerator categories so that retrieval remains traceable.

## Repository Layout

```text
Tools/Sentinel-Content-Forge-Accelerator/
  agent-instructions.md
  instructions/
  database/
    baseline/
    runtime/
  schemas/
  scripts/
  examples/
  output/
```

The `database/baseline` directory is versioned. The `database/runtime` and `output` directories are local working artifacts and are ignored by Git.

## Validation and Review

Generation is not publication. Every generated artifact is staged under `output` with its selected references, classification result, and validation report. A human must review and approve content before it is copied into a Sentinel solution or submitted in a pull request.

Validation follows the repository guidance for analytic rules, hunting queries, workbooks, and solution manifests. The accelerator checks structure and dependencies deterministically, while the agent reviews relevance, quality, and source-data fit.

## Initial Scope

The first end-to-end scenario will generate and validate one analytic rule and one hunting query from one sample data source. Workbook generation is supported by the design but follows after the first generation and validation path is proven.

## Test the Accelerator

Run the accelerator's focused tests from the repository root:

```powershell
python -m unittest Tools/Sentinel-Content-Forge-Accelerator/tests/test_accelerator.py -v
```

## Maintainer Workflow

Maintainers can explicitly rebuild and review the baseline Microsoft Content Database when they want to publish an updated accelerator snapshot. Routine end-user requests only refresh the ignored local working database.