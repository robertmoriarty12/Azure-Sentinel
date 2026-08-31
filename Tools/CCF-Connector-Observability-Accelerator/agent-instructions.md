# CCF Connector Observability Accelerator — Agent Deployment Instructions

> **GitHub:** [Azure/Azure-Sentinel → Tools/CCF-Connector-Observability-Accelerator](https://github.com/Azure/Azure-Sentinel/tree/master/Tools/CCF-Connector-Observability-Accelerator)

> These are instructions for a GitHub Copilot agent. When a user pastes the trigger prompt,
> load this file and follow the steps below exactly.
>
> **Trigger prompt** (paste into Copilot Chat in Agent mode):
> ```
> Load and follow the deployment instructions at Tools/CCF-Connector-Observability-Accelerator/agent-instructions.md. Let's deploy the CCF Observability lab.
> ```

---

## Step 0 — Collect Deployment Values

**Start here every time.** Before taking any deployment action, work through the values below.

**Default behaviour when a value is missing:** this is a lab tool, so resource names do not need to be meaningful as long as they are unique. **If the user doesn't provide a value, generate one** (e.g. append a random 4-digit suffix like `ccfobs-1234`). Do not ask for values the user hasn't volunteered. Generate sensible defaults, show them in the confirmation table, and proceed.

The only value you must confirm with the user is the **Subscription ID** (if more than one exists).

---

### 1. Azure Subscription ID

Run to see available subscriptions and let the user choose:

```powershell
az account list --query "[].{name:name, id:id, isDefault:isDefault}" -o table
```

If only one subscription exists (or one is marked `isDefault: True`), confirm it with the user rather than assuming.

---

### 2. Sentinel Workspace Name + Resource Group

If not provided, ask: *"Do you have an existing Sentinel workspace, or should I create a new one?"*

**Existing workspace** — list and let the user pick:

```powershell
az monitor log-analytics workspace list `
  --query "[].{name:name, resourceGroup:resourceGroup, location:location}" -o table
```

Derive `workspace-resource-group` and `location` from the chosen row — do not ask again.

**New workspace** — suggest these names and ask the user to confirm or change them:
- Workspace name: `ccfobs-ws`
- Resource group: `ccfobs-rg`
- Location: see value 3 below

Once confirmed, run:

```powershell
# Create resource group (skip if reusing an existing one)
az group create `
  --name <workspace-rg> `
  --location <region> `
  --output table

# Create the Log Analytics workspace
az monitor log-analytics workspace create `
  --workspace-name <workspace-name> `
  --resource-group <workspace-rg> `
  --location <region> `
  --output table

# Enable Microsoft Sentinel on the workspace
# Note: use Invoke-WebRequest with a bearer token — az rest can hang in VS Code terminals
$wsId = (az monitor log-analytics workspace show `
  --name <workspace-name> `
  --resource-group <workspace-rg> `
  --query id -o tsv).Trim()
$token = (az account get-access-token --query accessToken -o tsv).Trim()
$sentinelUrl = "https://management.azure.com$wsId/providers/Microsoft.SecurityInsights/onboardingStates/default?api-version=2024-03-01"
$sentinelResp = Invoke-WebRequest -Uri $sentinelUrl -Method PUT `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body "{}"
Write-Host "Sentinel enabled: HTTP $($sentinelResp.StatusCode)"
```

Then immediately enable Sentinel health monitoring so health records start accumulating from the moment the connector is created:

> **⚠️ Prompt the user (new workspace only):**
> "Health monitoring must be enabled now so the Diagnostics Agent has data to analyse later."
>
> **Microsoft Sentinel** → **Settings** → **Auditing and health monitoring** → enable → Save
>
> [Enable Sentinel health monitoring →](https://learn.microsoft.com/en-us/azure/sentinel/enable-monitoring)
>
> Type `next` when done.

**If using an existing workspace**, ask the user: *"Is Sentinel health monitoring already enabled on this workspace?"*
- If **yes** — continue.
- If **no** — prompt them to enable it now (same steps above) before proceeding.

**Verify** workspace exists and Sentinel is enabled:

```powershell
az monitor log-analytics workspace show `
  --name <workspace-name> `
  --resource-group <workspace-rg> `
  --query "{name:name, location:location, resourceGroup:resourceGroup, provisioningState:provisioningState}" `
  --output table
```

---

### 3. Azure Region / Location

- **Existing workspace** — inherit its location automatically — do **not** ask.
- **New workspace** — suggest `eastus` and ask the user to confirm.
- This value is passed as `workspace-location` in Step 3.

---

### 4. API Key

Ask the user: *"What API key should the connector use? (Press Enter to use the default `abc123`.)"*

- If the user provides a key, use it.
- If the user presses Enter or says nothing, use `abc123`.
- Store this as `<api-key>` for use in Steps 3 and 4.

---

### 5. Function App Resource Group + Names

Suggest the following defaults (append the same random suffix throughout) and ask the user to confirm or change:

- Function App RG: `ccfobs-fa-rg-<suffix>`
- Storage Account name: `stccfobs<suffix>` (globally unique; lowercase letters and digits only, 3–24 chars)
- Function App name: `ccf-observability-<suffix>` (globally unique)

Check whether the generated Function App RG already exists before creating it:

```powershell
az group show --name ccfobs-fa-rg-<suffix> --query location -o tsv 2>$null
```

If it exists in a different region, generate a new suffix and re-suggest.

---

### Value Summary Checkpoint

Once all values are collected, print a confirmation table before taking any action:

```
Subscription ID:        xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Workspace name:         <workspace-name>
Workspace RG:           <workspace-rg>
Region:                 eastus
Function App RG:        ccfobs-fa-rg-<suffix>
Storage Account:        stccfobs<suffix>
Function App name:      ccf-observability-<suffix>
Function App URL:       https://ccf-observability-<suffix>.azurewebsites.net
API key:                <api-key>
```

Ask: **"Does this look correct? Type `yes` to begin deployment."**

---

## Deployment Rules — Follow Without Exception

1. **Code deploy**: use the Kudu async REST API (Step 3). Do NOT use `az functionapp deployment source config-zip` — it hangs in VS Code terminals during the remote pip install.

2. **Sentinel ARM deploy**: use the ARM management REST API (Step 4). Do NOT use `az deployment group create` — it hangs in VS Code terminals when the deployment runs silently for more than ~2 minutes.

3. **Enable Sentinel**: use `Invoke-WebRequest` with a bearer token from `az account get-access-token`. Do not use `az rest` — it hangs in VS Code integrated terminals.

4. **Steps 4, 5, 7, and 8 are manual actions** that require the user to act in the portal. At the start of each, print the action required and wait for the user to type `next` or `done` before proceeding. Do not skip or assume they are complete.

5. After **every** CLI step, verify success before proceeding. Run a follow-up command confirming `provisioningState=Succeeded` or the expected resource state. Report the result inline, then immediately continue. Only pause and ask when a step has genuinely failed and you cannot self-recover.

6. Display the Function App URL and API key clearly in chat at Step 4 so the user can copy them into the portal without switching to the terminal.

---

## Step 1 — Deploy the Function App Infrastructure

```powershell
# Create the Function App resource group
az group create `
  --name <fa-rg> `
  --location <region> `
  --output table

# Create storage account (lowercase, 3-24 chars, globally unique)
az storage account create `
  --name <storage-name> `
  --resource-group <fa-rg> `
  --sku Standard_LRS `
  --output table

# Create Linux Python 3.11 consumption Function App
az functionapp create `
  --name <fa-name> `
  --resource-group <fa-rg> `
  --consumption-plan-location <region> `
  --runtime python `
  --runtime-version 3.11 `
  --functions-version 4 `
  --storage-account <storage-name> `
  --os-type Linux `
  --output table
```

**Verify** the Function App was provisioned:

```powershell
az functionapp config show `
  --name <fa-name> `
  --resource-group <fa-rg> `
  --query "{linuxFxVersion:linuxFxVersion}" -o table
```

Expected: `linuxFxVersion` contains `Python|3.11`.

> **Note**: Skip `az functionapp show` — it hangs in VS Code terminals. The `config show` output confirming `Python|3.11` is sufficient.

---

## Step 2 — Deploy the Function App Code

Zip the `FunctionApp/` folder and deploy via the Kudu async REST API. This avoids `az functionapp deployment source config-zip`, which hangs in VS Code terminals during the remote pip install.

```powershell
# Run from the workspace root (e.g. C:\git\Azure-Sentinel)
$zipPath = Join-Path $PWD "ccfobs.zip"
Compress-Archive `
  -Path "Tools/CCF-Connector-Observability-Accelerator/FunctionApp/*" `
  -DestinationPath $zipPath `
  -Force

# Get Kudu publishing credentials
$creds = az functionapp deployment list-publishing-credentials `
  --name <fa-name> `
  --resource-group <fa-rg> `
  --query "{username:publishingUserName, password:publishingPassword}" -o json | ConvertFrom-Json
$base64Auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($creds.username):$($creds.password)"))

# Submit async zip deploy via Kudu REST API
$deployResp = Invoke-WebRequest `
  -Uri "https://<fa-name>.scm.azurewebsites.net/api/zipdeploy?isAsync=true" `
  -Method POST `
  -InFile $zipPath `
  -Headers @{ Authorization = "Basic $base64Auth"; "Content-Type" = "application/zip" }
Write-Host "Deploy submitted: HTTP $($deployResp.StatusCode)"

# Poll until complete (status 4 = Success, status 3 = Failed)
do {
  Start-Sleep -Seconds 10
  $buildStatus = Invoke-RestMethod `
    -Uri "https://<fa-name>.scm.azurewebsites.net/api/deployments/latest" `
    -Headers @{ Authorization = "Basic $base64Auth" }
  Write-Host "[$([datetime]::Now.ToString('HH:mm:ss'))] status=$($buildStatus.status) complete=$($buildStatus.complete)"
} while ($buildStatus.status -lt 3)
Write-Host "Code deploy complete: status=$($buildStatus.status)"
```

Expected: `status=4, complete=True`. Status 3 means the remote build failed — check the Function App's Log stream in the Azure Portal.

**Verify** the API is responding:

```powershell
Invoke-RestMethod "https://<fa-name>.azurewebsites.net/api/status" | ConvertTo-Json -Depth 3
```

Expected: JSON with `active_api_key: "abc123"`, all switches disabled, and a `tip` field.

---

## Step 3 — Deploy the Sentinel Connector

Deploy `CCFObservability_ArmTemplate.json` to register the solution and connector definition in the Sentinel workspace. Use the ARM management REST API directly — this avoids `az deployment group create`, which hangs in VS Code terminals.

```powershell
# Get a fresh access token
$token = (az account get-access-token --query accessToken -o tsv).Trim()

# Read the ARM template from disk
$template = Get-Content `
  "Tools/CCF-Connector-Observability-Accelerator/Data Connectors/CCFObservability_CCF/CCFObservability_ArmTemplate.json" `
  -Raw | ConvertFrom-Json

# Build the deployment request body
$deployBody = @{
  properties = @{
    mode     = "Incremental"
    template = $template
    parameters = @{
      workspace            = @{ value = "<workspace-name>" }
      "workspace-location" = @{ value = "<region>" }
    }
  }
} | ConvertTo-Json -Depth 50

# Submit the deployment
$subId = (az account show --query id -o tsv).Trim()
$deployUrl = "https://management.azure.com/subscriptions/$subId/resourceGroups/<workspace-rg>/providers/Microsoft.Resources/deployments/CCFObservability?api-version=2021-04-01"
$submitResp = Invoke-WebRequest -Uri $deployUrl -Method PUT `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body $deployBody
Write-Host "Deployment submitted: HTTP $($submitResp.StatusCode)"

# Poll until terminal state
do {
  Start-Sleep -Seconds 15
  $token = (az account get-access-token --query accessToken -o tsv).Trim()
  $deployState = (Invoke-RestMethod -Uri $deployUrl `
    -Headers @{ Authorization = "Bearer $token" }).properties.provisioningState
  Write-Host "[$([datetime]::Now.ToString('HH:mm:ss'))] $deployState"
} while ($deployState -notin @("Succeeded","Failed","Canceled"))
Write-Host "Deployment final state: $deployState"
```

Expected final state: `Succeeded`. If `Failed`, check the deployment operations in the Azure Portal (Resource Group → Deployments → CCFObservability → Operation details).

---

## Step 4 — Connect the Connector (Manual)

Print the following values clearly in chat so the user can copy them directly into the portal:

| Field | Value |
|-------|-------|
| Function App Base URL | `https://<fa-name>.azurewebsites.net` |
| API Key | `abc123` |

Then prompt the user:

> **Action required:** Complete the steps below in the Sentinel portal, then come back and type `done` so I can proceed to verification.

1. Navigate to **Microsoft Sentinel** → **Data Connectors**
2. Search for **CCF Observability — Error Injection Test API** — if not visible, click **Refresh** or wait 2–3 minutes for the ARM deployment to propagate
3. Click **Open connector page**
4. Under **STEP 2 — Connect to the Observability API**, enter:
   - **Function App Base URL**: `https://<fa-name>.azurewebsites.net`
   - **API Key**: `abc123`
5. Click **connect**

Wait for the user to confirm before moving to Step 5.

---

## Step 5 — Verify Data is Flowing (Manual)

Prompt the user:

> **Action required:** Allow 5–10 minutes for the first poll cycle, then run the query below in **Microsoft Sentinel → Logs**. Come back and paste the row count (or a screenshot) when done.

```kql
CCFObservabilityEvents_CL
| sort by TimeGenerated desc
| take 10
```

Expected: rows with `EventId`, `SourceIp`, `DestinationIp`, `Action`, `Severity`, `Protocol`, `BytesTransferred` columns populated.

If the user reports no rows after 15 minutes, ask them to confirm:
1. Connector status shows **Connected** in the portal
2. Run: `Invoke-RestMethod "https://<fa-name>.azurewebsites.net/api/status"` — confirm `active_api_key` is `abc123`
3. API key entered in the portal matches `abc123`

Once the user confirms data is flowing, type `next` to continue.

---

## Step 6 — Inject an Error Switch (Agent-assisted)

Ask the user which error scenario they want to test:

> **Which error do you want to inject?**
>
> | # | Switch | What the connector sees |
> |---|--------|------------------------|
> | 1 | `switchhttpstatus?code=429` | HTTP 429 — rate limited |
> | 2 | `switchapikey` | HTTP 401 — invalid API key |
> | 3 | `switchempty` | HTTP 200, zero records ingested |
> | 4 | `switchlatency` | Request timeout (70s > 60s limit) |
> | 5 | `switchpagination` | Pagination loop / stalled checkpoint |
>
> Type a number (1–5) or the switch name.

Once the user picks, run the switch and verify the response:

```powershell
# Activate chosen switch (replace <switch> with the selected endpoint)
$base = "https://<fa-name>.azurewebsites.net"
$resp = Invoke-RestMethod -Uri "$base/api/<switch>" -Method POST
$resp | ConvertTo-Json -Depth 3

# Confirm the switch is active
Invoke-RestMethod "$base/api/status" | ConvertTo-Json -Depth 3
```

Verify the switch state matches (e.g. `httpstatus.enabled = true, code = 429`), report back to the user, then tell the user:

> **While errors are accumulating (2–3 minutes), complete the next step to set up the Diagnostics Agent.**

---

## Step 7 — Set Up Diagnostics Prerequisites (Manual)

Prompt the user to complete both actions while the switch is running and errors are building up in health records.

> **Action required (Part A — Security Copilot compute):**
> Provision an SCU capacity so the Diagnostics Agent has compute to run.
> ⚠️ **SCU charges start immediately and continue until you delete the capacity. Delete it as soon as you finish testing.**
>
> **Azure portal** → search **Microsoft Security compute capacities** → **Set up your Copilot capacity** → provision at least 1 SCU
>
> [Set up Copilot capacity →](https://learn.microsoft.com/en-us/copilot/security/get-started-security-copilot)
>
> Skip this part if you already have an active SCU capacity.

> **Note — Sentinel health monitoring:** This was enabled during workspace setup (Step 0). If you skipped that step or are unsure, confirm it now:
> **Microsoft Sentinel** → **Settings** → **Auditing and health monitoring** → verify it is enabled.
>
> Type `next` when SCU is provisioned (and health monitoring is confirmed active).

---

## Step 8 — Run the Diagnostics Agent (Manual)

Prompt the user:

> **Action required:** Open the Diagnostics Agent in the Sentinel portal to see the injected error explained.
>
> **Microsoft Sentinel** → **Data Connectors** → **CCF Observability — Error Injection Test API** → **Open connector page** → **Data connector diagnostics**
>
> Security Copilot opens with the connector pre-loaded, queries `SentinelHealth`, and returns each detected error with plain-language remediation steps.
>
> Type `done` when you've reviewed the output. If you'd like, share what the agent surfaced (error code, description) so I can include it in the session summary.

After the user types `done`, revert all switches:

```powershell
$r = Invoke-RestMethod -Uri "https://<fa-name>.azurewebsites.net/api/revert" -Method POST
Write-Host $r.message
```

Print a brief session summary of this switch run, for example:

```
────────── Switch Test Summary ──────────
Switch:      <switch used, e.g. switchapikey>
Effect:      <what the connector saw, e.g. HTTP 401 on every poll>
Agent found: <what Security Copilot surfaced, if the user shared it>
Reverted:    yes
──────────────────────────────
```

Then ask:

> Would you like to test another switch, or are you done?
>
> | Option | Action |
> |--------|--------|
> | Type **1–5** | Inject another switch and repeat Steps 6–8 |
> | Type **`finish`** | End the session — print the full Completion Summary |

Repeat Steps 6–8 for as many switches as the user wants. When they type `finish`, print the Completion Summary.

---

## Completion Summary

Print when the user types `finish`:

```
========== Session Summary ==========

Function App URL:    https://<fa-name>.azurewebsites.net
Function App RG:     <fa-rg>  (<region>)
Sentinel Workspace:  <workspace-name>  (<workspace-rg>)
API Key:             abc123
Table:               CCFObservabilityEvents_CL
Status:              Connected

Switches tested this session:
  (list each switch tested with what the agent surfaced)

Switch endpoints for future use:
  POST /api/switchapikey               → connector gets HTTP 401
  POST /api/switchhttpstatus?code=429  → force any 4xx/5xx
  POST /api/switchempty                → zero records ingested
  POST /api/switchlatency              → connector timeout
  POST /api/switchpagination           → pagination loop
  POST /api/revert                     → reset everything

Run diagnostics again any time:
  Sentinel → Data Connectors → CCF Observability → Data connector diagnostics

⚠️  IMPORTANT — Delete your SCU capacity to stop billing:
  Azure portal → Microsoft Security compute capacities → select capacity → Delete

=====================================
```

When the user types `finish`, also offer to run cleanup:

> **Would you like me to clean up the deployed resources?**
>
> | Option | What gets deleted |
> |--------|-------------------|
> | **`cleanup-all`** | Function App RG (Function App + Storage) and disconnects the Sentinel connector |
> | **`cleanup-fa`** | Function App RG only — keeps Sentinel connector and table for future use |
> | **`skip`** | Skip cleanup — leave everything running |

Run the appropriate commands based on the user's choice.

---

## Cleanup (when requested)

```powershell
# Step 1: Delete the Function App resource group (Function App + Storage Account)
az group delete --name <fa-rg> --yes --no-wait
Write-Host "Function App RG deletion submitted (running in background)"

# Step 2: Delete the SCU capacity (stops billing immediately)
# User must do this manually:
# Azure portal → Microsoft Security compute capacities → select capacity → Delete
Write-Host "⚠️  Remember to delete your SCU capacity in the Azure portal to stop billing."

# Step 3 (cleanup-all only): Disconnect the Sentinel connector and remove resources
$token = (az account get-access-token --query accessToken -o tsv).Trim()
$subId = (az account show --query id -o tsv).Trim()
$wsRg  = "<workspace-rg>"
$ws    = "<workspace-name>"

# Delete the RestApiPoller dataConnector
Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/$subId/resourceGroups/$wsRg/providers/Microsoft.OperationalInsights/workspaces/$ws/providers/Microsoft.SecurityInsights/dataConnectors/CCFObservability?api-version=2022-12-01-preview" `
  -Method DELETE -Headers @{ Authorization = "Bearer $token" }
Write-Host "Connector deleted"

# Delete the CCFObservabilityEvents_CL table
Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/$subId/resourceGroups/$wsRg/providers/Microsoft.OperationalInsights/workspaces/$ws/tables/CCFObservabilityEvents_CL?api-version=2022-10-01" `
  -Method DELETE -Headers @{ Authorization = "Bearer $token" }
Write-Host "Table deleted"

# Remove the solution content package from the workspace
Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/$subId/resourceGroups/$wsRg/providers/Microsoft.OperationalInsights/workspaces/$ws/providers/Microsoft.SecurityInsights/contentPackages/azuresentinel.azure-sentinel-solution-CCFObservabilityConnector?api-version=2023-04-01-preview" `
  -Method DELETE -Headers @{ Authorization = "Bearer $token" }
Write-Host "Solution package deleted"
```

After cleanup, print a confirmation:

```
========== Cleanup Complete ==========

Deleted:
  ✓ Function App RG: <fa-rg>
  ✓ Sentinel connector: CCFObservability
  ✓ Table: CCFObservabilityEvents_CL
  ✓ Solution package

⚠️  Still required (manual):
  Delete SCU capacity in the Azure portal to stop billing.
  Azure portal → Microsoft Security compute capacities → select → Delete

======================================
```
