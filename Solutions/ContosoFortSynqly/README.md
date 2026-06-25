# Synqly ISV Onboarding Guide — Microsoft Sentinel Solution Template

This folder is a template for ISVs integrating with Microsoft Sentinel via the Synqly platform. Follow the steps below to rename, configure, package, and publish your own solution.

---

## Prerequisites

- GitHub account with a fork of https://github.com/Azure/Azure-Sentinel
- Azure subscription with an active Microsoft Sentinel workspace
- Azure CLI installed: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
- PowerShell 7+: https://github.com/PowerShell/PowerShell/releases
- Node.js: https://nodejs.org

---

## STEP 1 — Clone your fork

    git clone https://github.com/your-github-username/Azure-Sentinel.git
    cd Azure-Sentinel

---

## STEP 2 — Copy this template into your fork

    git remote add robert https://github.com/robertmoriarty12/Azure-Sentinel.git
    git fetch robert feature/cloudfort-synqly-solutions
    git checkout robert/feature/cloudfort-synqly-solutions -- Solutions/ContosoFortSynqly

---

## STEP 3 — Rename the solution folder

Rename Solutions/ContosoFortSynqly to your company name:

    Rename-Item Solutions/ContosoFortSynqly Solutions/YourCompanyName

Use this same name consistently in all steps below.

---

## STEP 4 — Update the solution files

Replace every occurrence of **ContosoFort** and **contosofort** with your company name in these four files:

**SolutionMetadata.json**
- `publisherId` — your Partner Center publisher ID (lowercase, no spaces)
- `offerId` — a unique ID for this offering, e.g. yourcompany-sentinel-solution
- `providers` — your company display name
- `support.name`, `support.email`, `support.link` — your support details

**Data/Solution_YourCompanyName.json**
- `Name`, `Author`, `Description` — update to your company
- `Data Connectors` array — update path to match your renamed folder

**Data Connectors/YourCompanyName.json**
- `id`, `title`, `publisher` — update to your company
- `EventVendor` — must match exactly what Synqly writes to the ASIM table (confirm with Synqly)
- `graphQueriesTableName` — the target ASIM table (confirm with Synqly which table your data lands in)

**ReleaseNotes.md**
- Update the product name and add an entry for the initial 1.0.0 release

---

## STEP 5 — Update the connector instruction steps

In `Data Connectors/YourCompanyName.json`, find the `instructionSteps` section and fill in:

1. How a customer enables the integration on your ISV portal
2. How to configure the Synqly connector to point to your product

---

## STEP 6 — Package the solution

Run the packaging tool from the repository root and enter `Solutions/YourCompanyName/Data` when prompted:

    pwsh Tools/Create-Azure-Sentinel-Solution/V3/createSolutionV3.ps1

This generates `Package/mainTemplate.json`, `createUiDefinition.json`, and a versioned zip.

---

## STEP 7 — Deploy and test

Deploy the generated ARM template to your Sentinel workspace:

    az deployment group create --resource-group your-sentinel-rg --template-file Solutions/YourCompanyName/Package/mainTemplate.json

Verify data flows into the ASIM table using the sample queries in the connector definition. If that looks good, proceed.

---

## STEP 8 — Add additional content (optional)

Add any of the following to the solution folder, then repackage and retest:

- `Analytic Rules/` — KQL detection rules
- `Hunting Queries/` — threat hunting queries
- `Workbooks/` — dashboard visualizations
- `Playbooks/` — automated response logic

---

## STEP 9 — Run local validation

    npm install
    npm run tsc
    node .script/local-validation/validate.js --path "Solutions/YourCompanyName"

Fix any findings before submitting. Full docs: https://github.com/Azure/Azure-Sentinel/blob/master/.script/local-validation/README.md

---

## STEP 10 — Push a branch and open a PR

    git checkout -b feature/yourcompanyname-sentinel-solution
    git add Solutions/YourCompanyName
    git commit -m "Add YourCompanyName Sentinel solution"
    git push origin feature/yourcompanyname-sentinel-solution

Open a pull request from your fork to https://github.com/Azure/Azure-Sentinel.

---

## STEP 11 — Publish in Partner Center

Once the PR is merged, publish in Microsoft Partner Center. Use the preview audience feature to validate before going fully live. The solution appears in Microsoft Sentinel Content Hub within approximately 3 business days.
