# Microsoft Sentinel – Function App Sample Data Connector

This solution demonstrates how to build a Microsoft Sentinel data connector using an **Azure Function** and the **Azure Monitor Ingestion API** (DCE/DCR). Use it as a starting template for ingesting custom JSON events from any source into a Sentinel custom log table.

---

## Deployment Flow Overview

This solution uses the **standard two-ARM-template pattern** for Microsoft Sentinel solutions:

```
Step 1: Microsoft Sentinel + Log Analytics Workspace (LAW)
        │
        └── Step 2: Deploy mainTemplate.json
                    → installs the connector card in Sentinel Data Connectors
                        │
                        └── Step 3: Open connector in Sentinel → create App Registration
                                    → click Deploy to Azure inside the connector
                                        → deploys Function App + DCE + DCR + table
                                            │
                                            └── Function App running every 10 min
                                                → data flows into FunctionAppSample_CL
```

| Step | What you deploy | Template used |
|---|---|---|
| 1 | Microsoft Sentinel + Log Analytics Workspace | Azure Portal (built-in) |
| 2 | Sentinel connector UI definition (connector card) | `Package/mainTemplate.json` |
| 3 | Azure Function App + DCE + DCR + custom table | `Data Connectors/azuredeploy_FunctionApp_API_FunctionApp.json` |

---

## Step 1 – Deploy Microsoft Sentinel with a Log Analytics Workspace

If you don't already have a Sentinel workspace, create one:

1. In the [Azure Portal](https://portal.azure.com), search for **Microsoft Sentinel** and click **Create**
2. Click **Create a new workspace**, fill in the workspace name, resource group, and region
3. Click **Add** to enable Microsoft Sentinel on the workspace

Note down:
- **Workspace name** — needed in Step 2
- **Workspace Resource ID** — go to **Log Analytics workspace → Properties → Resource ID** — needed in Step 3
- **Region** — all subsequent resources should be in the same region

> **Region note:** Deploy to **Central US** if your subscription has limited quota. East US commonly blocks Consumption-plan Function App deployments (`SubscriptionIsOverQuotaForSku`).

---

## Step 2 – Deploy the Sentinel Connector Solution (mainTemplate.json)

This step installs the **connector card** into your Sentinel workspace so it appears under **Data Connectors**. It does not deploy the Function App itself — that happens in Step 3.

### Option A – Azure Portal (Custom Deployment)

1. Go to **Azure Portal → search "Deploy a custom template" → Build your own template in the editor**
2. Paste the contents of [`Package/mainTemplate.json`](Package/mainTemplate.json) and click **Save**
3. Fill in the parameters:

| Parameter | Description |
|---|---|
| `workspace` | Name of your Log Analytics / Sentinel workspace from Step 1 |
| `workspace-location` | Azure region of the workspace (e.g. `centralus`) |

4. Deploy to the **same resource group** as your Sentinel workspace

### Option B – Azure CLI

```powershell
az deployment group create `
  --resource-group <your-sentinel-rg> `
  --template-file "Package/mainTemplate.json" `
  --parameters workspace="<your-workspace-name>" "workspace-location"="centralus"
```

### Verify

After deployment, go to **Microsoft Sentinel → Data Connectors** and search for **"Function App Sample"**. The connector card should appear. If it does not, wait 1-2 minutes and refresh.

---

## Step 3 – Enable the Connector and Deploy the Function App

This step deploys the actual Azure Function and all Azure Monitor infrastructure (DCE, DCR, custom table, role assignment).

### 3a – Create an Azure AD App Registration

The Function App authenticates to Azure Monitor using a service principal.

1. In the Azure Portal, go to **Microsoft Entra ID → App registrations → New registration**
2. Name it (e.g. `FunctionApp-Sentinel-Connector`) and click **Register**
3. Under **Certificates & secrets**, create a new client secret — note the **value** (shown once only)
4. On the App Registration **Overview** page, note:
   - **Application (client) ID** → `ClientId`
   - **Directory (tenant) ID** → `TenantId`
   - **Object ID** → `AzureClientObjectId`

> The **Object ID** on the App Registration overview is used by the ARM template to assign the **Monitoring Metrics Publisher** role on the DCR. Do not use the Enterprise Application Object ID.

### 3b – Open the Connector in Sentinel and Deploy

1. In **Microsoft Sentinel → Data Connectors**, find **"Function App Sample (Ingestion API)"** and open it
2. Click **Open connector page**
3. Follow **STEP 1** in the connector page (App Registration — done above)
4. Under **STEP 2 – Deploy the Azure Function App**, click **Deploy to Azure**
5. Fill in the parameters:

| Parameter | Description |
|---|---|
| `FunctionName` | Prefix for all resources created (e.g. `FunctionAppSample`, max 18 chars) |
| `WorkspaceName` | Your Log Analytics workspace name from Step 1 |
| `TenantId` | Tenant ID from Step 3a |
| `ClientId` | Client ID from Step 3a |
| `ClientSecret` | Client secret value from Step 3a |
| `AzureClientObjectId` | Object ID from Step 3a |
| `AppInsightsWorkspaceResourceID` | Full Resource ID of the Log Analytics workspace (from workspace **Properties → Resource ID**) |

6. Deploy to the **same region** as your Sentinel workspace

### What the Function App ARM template creates automatically

| Resource | Purpose |
|---|---|
| Data Collection Endpoint (DCE) | Receives HTTP POST from the Function App |
| `FunctionAppSample_CL` table | Custom log table in your Sentinel workspace |
| Data Collection Rule (DCR) | Maps the incoming stream to the table columns |
| Role assignment | Grants the App Registration `Monitoring Metrics Publisher` on the DCR |
| Application Insights | Function App monitoring, linked to your workspace |
| Storage Account | Required by the Azure Functions runtime |
| App Service Plan (Y1/Consumption) | Serverless — no cost when not running |
| Function App | Timer-triggered Python function (fires every 10 minutes) |

---

## Step 4 – Verify the Deployment

### Check the function loaded

Go to your Function App in the Azure Portal → **Functions**. You should see `AzureFunctionFunctionApp` listed. If no functions appear, check **Log stream** for startup errors.

### Manually trigger the function

The function runs automatically every 10 minutes. To trigger immediately:

**Portal:**
1. Function App → **Functions** → `AzureFunctionFunctionApp`
2. Click **Test/Run** → **Run**
3. Watch the **Logs** tab — look for `Successfully ingested 3 event(s)` within a few seconds

**PowerShell:**
```powershell
$key = az functionapp keys list --name <function-app-name> --resource-group <rg> --query masterKey -o tsv
Invoke-WebRequest `
  -Uri "https://<function-app-name>.azurewebsites.net/admin/functions/AzureFunctionFunctionApp" `
  -Method Post `
  -Headers @{"x-functions-key" = $key} `
  -ContentType "application/json" `
  -Body "{}" `
  -UseBasicParsing
```

### Verify data in Sentinel

In **Microsoft Sentinel → Logs**, run (allow ~5 minutes for ingestion lag):

```kql
FunctionAppSample_CL
| sort by TimeGenerated desc
| take 10
```

The connector status card in Sentinel will also flip to **Connected** once data has been received within the last 24 hours.

---

## Architecture – How It Works

```
Azure Function (Timer, every 10 min)
    │
    ├── ClientSecretCredential (Tenant/Client/Secret from App Settings)
    ├── LogsIngestionClient.upload() → POST to DCE endpoint
    │       Response: HTTP 204
    │
    └── DCE → DCR (stream mapping) → FunctionAppSample_CL
                                            │
                                            └── Microsoft Sentinel Logs
```

### Key App Settings (set automatically by the Function App ARM template)

| Setting | Value source |
|---|---|
| `TENANT_ID` | ARM parameter |
| `CLIENT_ID` | ARM parameter |
| `CLIENT_SECRET` | ARM parameter |
| `DCE_ENDPOINT` | Auto-resolved from DCE resource at deploy time via `reference()` |
| `DCR_ID` | Auto-resolved from DCR `immutableId` at deploy time via `reference()` |
| `STREAM_NAME` | `Custom-FunctionAppSample_CL` |
| `WEBSITE_RUN_FROM_PACKAGE` | URL to pre-built function zip on GitHub |

---

## Adapting This Template for Your Own Connector

1. **Modify `main.py`** — replace `build_sample_events()` with your actual data source API calls
2. **Update the table schema** in `azuredeploy_FunctionApp_API_FunctionApp.json` (`Microsoft.OperationalInsights/workspaces/tables`) to match your event fields
3. **Update `tableName` and `streamName`** variables in that ARM template
4. **Update the DCR `dataFlow`** column mappings to match your schema
5. **Update `requirements.txt`** with any extra Python packages your API client needs
6. **Rebuild the zip** (see below) and push to your GitHub fork
7. **Update `WEBSITE_RUN_FROM_PACKAGE`** in the ARM template to point to your new zip URL

### Rebuilding the zip

```powershell
$src     = "path\to\Data Connectors"
$staging = "$env:TEMP\fnapp_staging"
$pkgDir  = "$staging\.python_packages\lib\site-packages"

Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $pkgDir -Force

# Install packages
python -m pip install azure-functions==1.21.3 azure-identity==1.19.0 `
  azure-monitor-ingestion==1.0.4 azure-core==1.32.0 `
  --target $pkgDir --no-user

# Replace cryptography/cffi with Linux manylinux wheels (required — Function App runs Linux)
$wheelDir = "$env:TEMP\fnapp_wheels"
New-Item -ItemType Directory -Path $wheelDir -Force
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
Copy-Item "$src\AzureFunctionFunctionApp" "$staging\AzureFunctionFunctionApp" -Recurse -Force
Push-Location $staging
Compress-Archive -Path ".\*" -DestinationPath "$src\FunctionAppSample.zip" -Force
Pop-Location
```

Push the updated zip and restart the Function App:
```powershell
git add "Data Connectors/FunctionAppSample.zip"
git commit -m "Update function zip"
git push
az functionapp restart --name <function-app-name> --resource-group <rg>
```

> **Critical packaging rules:**
> - All Python packages must be pre-bundled inside the zip under `.python_packages/lib/site-packages/` — they are NOT auto-installed from `requirements.txt` when using `WEBSITE_RUN_FROM_PACKAGE` from a URL
> - `cryptography` and `cffi` **must** use Linux manylinux wheels — Windows `.pyd` builds will fail on the Linux runtime with an `ImportError`

---

## File Structure

```
Solutions/FunctionApp/
├── Package/
│   ├── mainTemplate.json          ← Step 2: Deploy this to install connector card in Sentinel
│   └── createUiDefinition.json
├── Data Connectors/
│   ├── azuredeploy_FunctionApp_API_FunctionApp.json  ← Step 3: Deployed via "Deploy to Azure" in connector UI
│   ├── FunctionApp_API_FunctionApp.json              ← Standalone connector UI definition
│   ├── FunctionAppSample.zip                         ← Pre-built function code + Linux packages
│   ├── host.json                                     ← Azure Functions host config
│   ├── requirements.txt                              ← Python dependencies
│   ├── proxies.json
│   ├── .funcignore
│   └── AzureFunctionFunctionApp/
│       ├── main.py                ← Timer trigger + DCE/DCR ingestion logic
│       └── function.json          ← Schedule: every 10 minutes
├── Data/
│   └── Solution_FunctionApp.json
├── ReleaseNotes.md
└── README.md
```

---

## Troubleshooting

### Connector card not appearing in Sentinel after Step 2
- Verify `mainTemplate.json` deployed without errors
- Confirm the `workspace` parameter matched your workspace name exactly (case-sensitive)
- Wait 1-2 minutes and refresh the Data Connectors blade

### Functions not showing in Function App after Step 3
- Check `WEBSITE_RUN_FROM_PACKAGE` in App Settings points to a publicly accessible URL
- Go to **Function App → Log stream** for startup errors

### `ModuleNotFoundError: No module named 'azure.identity'`
Python packages are not bundled in the zip. All packages must be pre-bundled under `.python_packages/lib/site-packages/` inside the zip. See [Rebuilding the zip](#rebuilding-the-zip).

### `ImportError: cannot import name 'x509' from cryptography`
`cryptography` was compiled for Windows but the runtime is Linux. Use Linux manylinux wheels. See [Rebuilding the zip](#rebuilding-the-zip).

### `SubscriptionIsOverQuotaForSku` on Function App deployment
No Consumption plan quota in the selected region. Deploy the resource group to **Central US**:
```powershell
az group create --name <rg> --location centralus
```

### Authentication errors from the Function App
- Verify `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` App Settings are correct
- Confirm the `Monitoring Metrics Publisher` role is assigned on the DCR to the App Registration Object ID:
```powershell
$dcrId = az monitor data-collection rule list -g <rg> --query "[0].id" -o tsv
az role assignment list --scope $dcrId --query "[].{role:roleDefinitionName,principal:principalId}" -o table
```

### Data not appearing in `FunctionAppSample_CL`
- Allow up to 5 minutes for ingestion lag after a successful function run
- Check the function **Invocations** tab for success/failure
- Confirm the function log shows `Successfully ingested 3 event(s) into stream 'Custom-FunctionAppSample_CL'`

---

## Resources

- [Azure Monitor Ingestion API](https://learn.microsoft.com/azure/azure-monitor/logs/logs-ingestion-api-overview)
- [Data Collection Rules overview](https://learn.microsoft.com/azure/azure-monitor/essentials/data-collection-rule-overview)
- [Azure Functions Python developer guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)
- [Microsoft Sentinel – Create custom data connectors](https://learn.microsoft.com/azure/sentinel/create-custom-connector)
- [Azure Functions pricing](https://azure.microsoft.com/pricing/details/functions/)
- [Azure Monitor pricing](https://azure.microsoft.com/pricing/details/monitor/)
