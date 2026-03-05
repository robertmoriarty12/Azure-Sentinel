# Microsoft Sentinel – XBOW Security Platform Data Connector

This solution connects the **XBOW Security Platform** to Microsoft Sentinel, ingesting security findings and assessments from your XBOW-monitored assets into two custom Sentinel tables: `XbowFindings_CL` and `XbowAssessments_CL`.

The connector polls the XBOW REST API on a 5-minute timer, performs an incremental diff against a persisted cursor in Azure Blob Storage, and forwards new or updated records via the Azure Monitor DCE/DCR Ingestion API.

---

## Deployment Flow Overview

```
Step 1: Microsoft Sentinel + Log Analytics Workspace (LAW)
        │
        └── Step 2: Deploy mainTemplate.json
                    → installs the connector card in Sentinel Data Connectors
                        │
                        └── Step 3: Open connector in Sentinel → create App Registration
                                    → click Deploy to Azure inside the connector
                                        → deploys Function App + DCE + DCR + tables
                                            │
                                            └── Function App running every 5 min
                                                → polls XBOW API
                                                → diffs against stored state
                                                → ingests into XbowFindings_CL
                                                              XbowAssessments_CL
```

| Step | What you deploy | Template used |
|---|---|---|
| 1 | Microsoft Sentinel + Log Analytics Workspace | Azure Portal (built-in) |
| 2 | Sentinel connector UI definition (connector card) | `Package/mainTemplate.json` |
| 3 | Azure Function App + DCE + DCR + custom tables | `Data Connectors/azuredeploy_Xbow_API_Xbow.json` |

---

## Step 1 – Deploy Microsoft Sentinel with a Log Analytics Workspace

1. In the [Azure Portal](https://portal.azure.com), search for **Microsoft Sentinel** and click **Create**
2. Click **Create a new workspace**, fill in the workspace name, resource group, and region
3. Click **Add** to enable Microsoft Sentinel on the workspace

Note down:
- **Workspace name** — needed in Step 2
- **Workspace Resource ID** — go to **Log Analytics workspace → Properties → Resource ID** — needed in Step 3
- **Region** — all subsequent resources should be in the same region

---

## Step 2 – Deploy the Sentinel Connector Solution (mainTemplate.json)

This step installs the **connector card** into your Sentinel workspace.

### Option A – Azure Portal (Custom Deployment)

1. Go to **Azure Portal → search "Deploy a custom template" → Build your own template in the editor**
2. Paste the contents of [`Package/mainTemplate.json`](Package/mainTemplate.json) and click **Save**
3. Fill in the parameters:

| Parameter | Description |
|---|---|
| `workspace` | Name of your Log Analytics / Sentinel workspace |
| `workspace-location` | Azure region (e.g. `centralus`) |

4. Deploy to the **same resource group** as your Sentinel workspace

### Verify

After deployment, go to **Microsoft Sentinel → Data Connectors** and search for **"XBOW"**. The connector card should appear.

---

## Step 3 – Enable the Connector and Deploy the Function App

### 3a – Create an Azure AD App Registration

1. In the Azure Portal, go to **Microsoft Entra ID → App registrations → New registration**
2. Name it (e.g. `Xbow-Sentinel-Connector`) and click **Register**
3. Under **Certificates & secrets**, create a new client secret — note the **value** (shown once only)
4. On the App Registration **Overview** page, note:
   - **Application (client) ID** → `ClientId`
   - **Directory (tenant) ID** → `TenantId`
   - **Object ID** → `AzureClientObjectId`

### 3b – Get your XBOW API credentials

1. Log in to the [XBOW Console](https://console.xbow.com)
2. Go to **Settings → Personal Access Tokens** and generate a new token
3. Note your **Organization ID** from the console URL or the Organizations API

### 3c – Deploy the Function App

1. In **Microsoft Sentinel → Data Connectors**, find **"XBOW (Ingestion API)"** and open it
2. Click **Open connector page**, then **Deploy to Azure**
3. Fill in the parameters:

| Parameter | Description |
|---|---|
| `FunctionName` | Prefix for all resources (max 11 chars), e.g. `Xbow` |
| `WorkspaceName` | Your Log Analytics workspace name |
| `XbowApiToken` | Your XBOW Personal Access Token |
| `XbowOrgId` | Your XBOW Organization ID |
| `TenantId` | Tenant ID from Step 3a |
| `ClientId` | Client ID from Step 3a |
| `ClientSecret` | Client secret value from Step 3a |
| `AzureClientObjectId` | Object ID from App Registration Overview |
| `AppInsightsWorkspaceResourceID` | Full Resource ID of the Log Analytics workspace |

### What the ARM template creates automatically

| Resource | Purpose |
|---|---|
| Data Collection Endpoint (DCE) | Receives HTTP POST from the Function App |
| `XbowFindings_CL` table | Security findings from XBOW-monitored assets |
| `XbowAssessments_CL` table | Assessment history and state per asset |
| Data Collection Rule (DCR) | Maps both streams to their respective tables |
| Role assignment | Grants the App Registration `Monitoring Metrics Publisher` on the DCR |
| Application Insights | Function App monitoring |
| Storage Account | Azure Functions runtime + connector state blob |
| App Service Plan (Y1/Consumption) | Serverless |
| Function App | Timer-triggered Python function (every 5 minutes) |

---

## Step 4 – Verify the Deployment

### Check data in Sentinel

In **Microsoft Sentinel → Logs**, run (allow ~5 minutes for ingestion lag):

```kql
XbowFindings_CL
| sort by TimeGenerated desc
| take 20
```

```kql
XbowAssessments_CL
| sort by TimeGenerated desc
| take 20
```

### Manually trigger the function

**Portal:**
1. Function App → **Functions** → `AzureFunctionXbow`
2. Click **Test/Run** → **Run**
3. Watch the **Logs** tab for ingestion output

**PowerShell:**
```powershell
$key = az functionapp keys list --name <function-app-name> --resource-group <rg> --query masterKey -o tsv
Invoke-WebRequest `
  -Uri "https://<function-app-name>.azurewebsites.net/admin/functions/AzureFunctionXbow" `
  -Method Post `
  -Headers @{"x-functions-key" = $key} `
  -ContentType "application/json" `
  -Body "{}" `
  -UseBasicParsing
```

---

## Architecture – How It Works

```
Azure Function (Timer, every 5 min)
    │
    ├── Load cursor state from Azure Blob Storage (xbow-connector-state/sync_state.json)
    ├── List all assets via GET /organizations/{orgId}/assets (paginated)
    │
    ├── For each asset → GET /organizations/{orgId}/assets/{id}/findings (paginated)
    │       → GET /findings/{findingId}  (enriched: evidence, recipe, impact, mitigations)
    │       → diff: keep only findings newer than last-seen updatedAt
    │       → emit XbowFindings_CL events
    │
    ├── For each asset → GET /organizations/{orgId}/assets/{id}/assessments (paginated)
    │       → diff: keep only assessments newer than last-seen updatedAt
    │       → emit XbowAssessments_CL events
    │
    ├── ClientSecretCredential → LogsIngestionClient.upload() → DCE → DCR
    │       XbowFindings_CL stream    (batches of 500)
    │       XbowAssessments_CL stream (batches of 500)
    │
    └── Save updated cursor state to Blob Storage (only on success)
```

### Key App Settings

| Setting | Description |
|---|---|
| `XBOW_API_TOKEN` | XBOW Personal Access Token |
| `XBOW_ORG_ID` | XBOW Organization ID |
| `TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` | Service principal for Azure Monitor auth |
| `DCE_ENDPOINT` | Auto-resolved from DCE resource at deploy time |
| `DCR_ID` | Auto-resolved from DCR `immutableId` at deploy time |
| `FINDINGS_STREAM_NAME` | `Custom-XbowFindings_CL` |
| `ASSESSMENTS_STREAM_NAME` | `Custom-XbowAssessments_CL` |
| `AzureWebJobsStorage` | Used by Functions runtime and connector state blob |

---

## Rebuilding the Zip Package

After modifying `main.py` or `requirements.txt`, rebuild `Xbow.zip`:

```powershell
$src     = "path\to\Data Connectors"
$staging = "$env:TEMP\xbow_staging"
$pkgDir  = "$staging\.python_packages\lib\site-packages"

Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $pkgDir -Force

# Install packages (Linux manylinux platform for Azure Functions Linux runtime)
$wheelDir = "$env:TEMP\xbow_wheels"
New-Item -ItemType Directory -Path $wheelDir -Force
python -m pip install azure-functions==1.21.3 azure-identity==1.19.0 `
  azure-monitor-ingestion==1.0.4 azure-core==1.32.0 `
  azure-storage-blob==12.23.1 requests==2.32.3 `
  --target $pkgDir --no-user

# Replace cryptography/cffi with Linux manylinux wheels
Remove-Item "$pkgDir\cryptography*","$pkgDir\cffi*","$pkgDir\_cffi_backend*" -Recurse -Force -ErrorAction SilentlyContinue
python -m pip download cryptography cffi `
  --dest $wheelDir `
  --platform manylinux2014_x86_64 --python-version 311 `
  --implementation cp --only-binary=:all:
Get-ChildItem $wheelDir -Filter "*.whl" | ForEach-Object {
    Expand-Archive -Path $_.FullName -DestinationPath $pkgDir -Force
}

# Copy function files and zip
Copy-Item "$src\host.json","$src\requirements.txt","$src\proxies.json" $staging -Force
Copy-Item "$src\AzureFunctionXbow" "$staging\AzureFunctionXbow" -Recurse -Force
Push-Location $staging
Compress-Archive -Path ".\*" -DestinationPath "$src\Xbow.zip" -Force
Pop-Location
```

Push the updated zip:
```powershell
git add "Data Connectors/Xbow.zip"
git commit -m "Rebuild Xbow function zip"
git push
az functionapp restart --name <function-app-name> --resource-group <rg>
```

> **Critical packaging rules:**
> - All Python packages must be pre-bundled inside the zip under `.python_packages/lib/site-packages/`
> - `cryptography` and `cffi` **must** use Linux manylinux wheels — Windows builds fail on the Linux runtime

---

## File Structure

```
Solutions/Xbow/
├── Package/
│   ├── mainTemplate.json                          ← Step 2: installs connector card
│   └── createUiDefinition.json
├── Data Connectors/
│   ├── azuredeploy_Xbow_API_Xbow.json             ← Step 3: Deploy to Azure
│   ├── Xbow_API_Xbow.json                         ← Connector UI definition
│   ├── Xbow.zip                                   ← Pre-built function + Linux packages
│   ├── host.json
│   ├── requirements.txt
│   ├── proxies.json
│   ├── .funcignore
│   └── AzureFunctionXbow/
│       ├── main.py                ← Timer trigger + XBOW API polling + DCE/DCR ingestion
│       └── function.json          ← Schedule: every 5 minutes
├── Data/
│   └── Solution_Xbow.json
├── SolutionMetadata.json
├── ReleaseNotes.md
└── README.md
```

---

## Troubleshooting

### No data in `XbowFindings_CL` or `XbowAssessments_CL`
- Allow up to 5 minutes for ingestion lag
- Check Function App **Invocations** for errors
- Verify `XBOW_API_TOKEN` and `XBOW_ORG_ID` app settings are correct
- Run a manual `GET https://console.xbow.com/api/v1/organizations/{orgId}/assets` curl to confirm the token works

### `ModuleNotFoundError: No module named 'azure.storage.blob'`
The zip was built without `azure-storage-blob`. Rebuild following the [Rebuilding the Zip](#rebuilding-the-zip-package) section.

### `ImportError: cannot import name 'x509' from cryptography`
Use Linux manylinux wheels for `cryptography` and `cffi`. See [Rebuilding the Zip](#rebuilding-the-zip-package).

### `SubscriptionIsOverQuotaForSku` on Function App deployment
No Consumption plan quota in the selected region. Deploy to **Central US**:
```powershell
az group create --name <rg> --location centralus
```

### Authentication errors
- Verify `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` app settings
- Confirm `Monitoring Metrics Publisher` role is assigned on the DCR:
```powershell
$dcrId = az monitor data-collection rule list -g <rg> --query "[0].id" -o tsv
az role assignment list --scope $dcrId --query "[].{role:roleDefinitionName,principal:principalId}" -o table
```

---

## Resources

- [XBOW API Documentation](https://docs.xbow.com/api/)
- [Azure Monitor Ingestion API](https://learn.microsoft.com/azure/azure-monitor/logs/logs-ingestion-api-overview)
- [Data Collection Rules overview](https://learn.microsoft.com/azure/azure-monitor/essentials/data-collection-rule-overview)
- [Azure Functions Python developer guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)
- [Microsoft Sentinel – Create custom data connectors](https://learn.microsoft.com/azure/sentinel/create-custom-connector)
