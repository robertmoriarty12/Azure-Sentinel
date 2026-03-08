# Microsoft Sentinel – Function App Data Connector Accelerator

This repository is an **ISV accelerator** for building and publishing a Microsoft Sentinel data connector using an **Azure Function** and the **Azure Monitor Ingestion API** (DCE/DCR). It provides a fully working end-to-end template — including the ARM deployment, Python function code, and Sentinel connector UI definition — that you can deploy as-is to validate the pattern, then adapt for your own data source.

---

## Overview

The accelerator follows the **standard two-ARM-template pattern** used by all Microsoft Sentinel solutions:

| Deployment | What it does | Template |
|---|---|---|
| **1 – Connector card** | Installs your connector UI into Sentinel Data Connectors | `FunctionApp/Package/mainTemplate.json` |
| **2 – Function App** | Deploys the Function App, DCE, DCR, Key Vault, and custom log table | `FunctionApp/Data Connectors/azuredeploy_FunctionApp_API_FunctionApp.json` |

```
Log Analytics Workspace + Microsoft Sentinel
    │
    └── Deploy mainTemplate.json  →  connector card appears in Data Connectors
            │
            └── Open connector → Deploy to Azure  →  Function App + DCE + DCR + Key Vault
                    │
                    └── Assign Monitoring Metrics Publisher on DCR
                            │
                            └── Function App runs every 10 min → data lands in FunctionAppSample_CL
```

---

## Scenario 1 – Test As-Is (No Code Changes)

Follow these steps to deploy the accelerator exactly as-is to verify the full ingestion pipeline end-to-end before customizing it for your data source.

---

### Prerequisites

- An Azure subscription with permission to create resource groups, register applications in Microsoft Entra ID, and assign RBAC roles
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (optional, for CLI-based deployments)
- [Git](https://git-scm.com/)

---

### Step 1 – Clone the Repositories

You need both the Azure Sentinel repository (for the packaging toolchain) and this accelerator.

```powershell
git clone https://github.com/Azure/Azure-Sentinel.git
git clone https://github.com/robertmoriarty12/Sentinel-Ingestion-Accelerator-Function-App.git
```

Copy the accelerator solution folder into the Azure Sentinel solutions directory:

```powershell
Copy-Item "Sentinel-Ingestion-Accelerator-Function-App\FunctionApp" `
          "Azure-Sentinel\Solutions\FunctionApp" -Recurse -Force
```

> **Note:** This copy step places your solution where the Sentinel packaging tools expect it. If you are submitting a PR to the official Azure Sentinel repository, this is where your solution folder will live permanently.

---

### Step 2 – Deploy a Log Analytics Workspace and Enable Microsoft Sentinel

If you do not already have a Sentinel workspace:

1. In the [Azure Portal](https://portal.azure.com), search for **Microsoft Sentinel** and click **Create**
2. Click **Create a new workspace**, fill in workspace name, resource group, and region, then click **Review + Create**
3. Once the workspace is created, click **Add** to enable Microsoft Sentinel on it

Note the following — you will need them later:

| Value | Where to find it |
|---|---|
| **Workspace name** | Log Analytics workspace → Overview |
| **Workspace Resource ID** | Log Analytics workspace → Properties → Resource ID |
| **Region** | Log Analytics workspace → Overview |

> **Region tip:** Deploy all resources to the same region. If you hit `SubscriptionIsOverQuotaForSku` errors in East US, try **Central US**.

---

### Step 3 – Deploy the Connector (mainTemplate.json)

This step installs the **"Function App Sample"** connector card into your Sentinel **Data Connectors** gallery. It does not deploy the Function App itself.

#### Option A – Azure Portal

1. In the Azure Portal, search for **"Deploy a custom template"** and select it
2. Click **Build your own template in the editor**
3. Paste the contents of [`FunctionApp/Package/mainTemplate.json`](FunctionApp/Package/mainTemplate.json) and click **Save**
4. Fill in the parameters:

| Parameter | Value |
|---|---|
| `workspace` | Your Log Analytics workspace name from Step 2 |
| `workspace-location` | Azure region of your workspace (e.g. `centralus`) |

5. Deploy to the **same resource group** as your Sentinel workspace

#### Option B – Azure CLI

```powershell
az deployment group create `
  --resource-group <your-sentinel-rg> `
  --template-file "Azure-Sentinel\Solutions\FunctionApp\Package\mainTemplate.json" `
  --parameters workspace="<your-workspace-name>" "workspace-location"="centralus"
```

#### Verify

Go to **Microsoft Sentinel → Data Connectors** and search for **"Function App Sample (Ingestion API)"**. The connector card should appear within 1–2 minutes.

---

### Step 4 – Create an Azure AD App Registration

The Function App uses a service principal to authenticate to Azure Monitor and push data into Sentinel.

1. In the Azure Portal, go to **Microsoft Entra ID → App registrations → New registration**
2. Enter a name (e.g. `FunctionApp-Sentinel-Connector`) and click **Register**
3. Under **Certificates & secrets → Client secrets → New client secret**, create a secret — copy the **Value** immediately (it is only shown once)
4. From the App Registration **Overview** page, note:

| Value | ARM parameter |
|---|---|
| Directory (tenant) ID | `TenantId` |
| Application (client) ID | `ClientId` |
| Client secret value | `ClientSecret` |

---

### Step 5 – Assign Key Vault Secrets Officer to the Deploying User

The Function App ARM template creates an Azure Key Vault and writes the `ClientSecret` into it. The deploying user or service principal must have the **Key Vault Secrets Officer** role (or **Key Vault Administrator**) on the target resource group or subscription **before** deployment — without it the deployment will fail with an authorization error when writing the secret.

1. In the Azure Portal, navigate to the **resource group** you plan to deploy into
2. Go to **Access control (IAM) → Add role assignment**
3. Select **Key Vault Secrets Officer**
4. Under **Members**, select the user or service principal that will run the deployment
5. Click **Review + assign**

---

### Step 6 – Deploy the Function App via the Connector Card

1. In **Microsoft Sentinel → Data Connectors**, find **"Function App Sample (Ingestion API)"** and click **Open connector page**
2. Follow **STEP 1** (already done in Step 4 above)
3. Under **STEP 2 – Deploy the Azure Function App**, click **Deploy to Azure**
4. Fill in the parameters:

| Parameter | Description |
|---|---|
| `WorkspaceName` | Log Analytics workspace name from Step 2 |
| `TenantId` | Tenant ID from Step 4 |
| `ClientId` | Client ID from Step 4 |
| `ClientSecret` | Client secret value from Step 4 |
| `AppInsightsWorkspaceResourceID` | Full Resource ID from Step 2 |
| `FunctionAppLocation` | Azure region (e.g. `centralus`). Can differ from RG location. |

5. Click **Review + create** and wait for deployment to complete (~3–5 minutes)

---

### Step 7 – Assign Monitoring Metrics Publisher on the Data Collection Rule

After the Function App deployment completes, grant the App Registration permission to ingest data into Sentinel.

1. In the Azure Portal, navigate to the **Data Collection Rule** created by the deployment (search by name in the resource group from Step 6, or find it in the deployment outputs)
2. Go to **Access control (IAM) → Add role assignment**
3. Select **Monitoring Metrics Publisher**
4. Under **Members**, choose **User, group, or service principal** and select the App Registration from Step 4
5. Click **Review + assign**

> **Critical:** This role must be assigned **directly on the Data Collection Rule resource** — assigning it at the resource group or subscription scope will **not work** and will result in a `403 Forbidden` error when the Function App attempts to ingest data. Wait **5–10 minutes** for RBAC propagation before testing.

---

### Step 8 – Verify Data Ingestion

The Function App runs automatically on a timer every 10 minutes. To verify data is flowing:

#### Check the function loaded

In the Azure Portal, go to your **Function App → Functions**. You should see `AzureFunctionFunctionApp` listed.

#### Manually trigger the function (optional)

1. Function App → **Functions** → `AzureFunctionFunctionApp`
2. Click **Test/Run → Run**
3. Watch the **Logs** tab — look for `Successfully ingested N event(s)`

#### Query Sentinel Logs

In **Microsoft Sentinel → Logs**, run:

```kql
FunctionAppSample_CL
| sort by TimeGenerated desc
| take 10
```

Allow **5–10 minutes** for ingestion lag after the function runs. Once data appears the connector status card in Sentinel will flip to **Connected**.

---

## Scenario 2 – Customize for Your Data Source

> Coming soon — covers modifying `main.py`, updating the table schema, rebuilding the zip, and adapting the connector UI for your product.

---

## Repository Structure

```
FunctionApp/
├── Data/
│   └── Solution_FunctionApp.json          # Solution metadata for Sentinel packaging tool
├── Data Connectors/
│   ├── FunctionApp_API_FunctionApp.json   # Connector UI definition (source — edit this)
│   ├── azuredeploy_FunctionApp_API_FunctionApp.json  # Function App ARM template
│   ├── AzureFunctionFunctionApp/
│   │   ├── main.py                        # Python function — replace with your API logic
│   │   └── function.json                  # Timer trigger config (every 10 min)
│   ├── FunctionAppSample.zip              # Pre-built deployment package
│   ├── host.json
│   ├── requirements.txt
│   └── proxies.json
├── Package/
│   ├── mainTemplate.json                  # Generated by packaging tool — do not edit directly
│   ├── 3.0.0.zip                          # Solution package
│   ├── createUiDefinition.json
│   └── testParameters.json
├── SolutionMetadata.json
├── README.md
└── ReleaseNotes.md
```

> **Important:** Never edit `Package/mainTemplate.json` directly. Always edit `Data Connectors/FunctionApp_API_FunctionApp.json` and re-run the packaging tool.

---

## Architecture

```
Azure Function (Timer, every 10 min)
    │
    ├── Reads CLIENT_SECRET via Key Vault reference (no plain-text secrets)
    ├── ClientSecretCredential → token for https://monitor.azure.com
    ├── LogsIngestionClient.upload() → POST to DCE endpoint
    │       HTTP 204 (success)
    │
    └── DCE → DCR (stream mapping) → FunctionAppSample_CL
                                            │
                                            └── Microsoft Sentinel Logs
```

### Key App Settings (set automatically by ARM template)

| Setting | Source |
|---|---|
| `TENANT_ID` | ARM parameter |
| `CLIENT_ID` | ARM parameter |
| `CLIENT_SECRET` | Key Vault reference — resolved at runtime by managed identity |
| `DCE_ENDPOINT` | Auto-resolved from DCE resource via ARM `reference()` |
| `DCR_ID` | Auto-resolved from DCR `immutableId` via ARM `reference()` |
| `STREAM_NAME` | `Custom-FunctionAppSample_CL` |

