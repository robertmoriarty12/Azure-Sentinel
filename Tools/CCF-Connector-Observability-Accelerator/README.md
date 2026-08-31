# CCF Observability — Connector Diagnostics Lab

A lab environment for testing the **Connector Diagnostics Agent in Microsoft Security Copilot** (private preview, Aug 2026). It provides a controllable mock REST API and a fully configured CCF RestApiPoller connector. Use the switch endpoints to inject specific connector errors on demand, then trigger the Diagnostics Agent to observe how it surfaces and explains each one.

Deploy this Function App, point a CCF RestApiPoller connector at `/api/main`, and use the switch endpoints to inject specific error conditions on demand. Then open the connector in Sentinel and trigger the Diagnostics Agent to observe how it surfaces and explains each error.

---

## GitHub Copilot Quick Deploy

### Before You Start

| Requirement | Details |
|---|---|
| **VS Code** | With the [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat) extension installed and signed in |
| **Azure CLI** | Installed and logged in (`az login`). [Install guide](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) |
| **Azure subscription** | With Contributor role on the resource groups where the Function App and Sentinel workspace will be deployed |
| **Microsoft Sentinel workspace** | Existing, or the agent will create one. [Quickstart](https://learn.microsoft.com/en-us/azure/sentinel/quickstart-onboard) |
| **Sentinel health monitoring enabled** | Required so the Diagnostics Agent has data to analyse. [Enable health monitoring](https://learn.microsoft.com/en-us/azure/sentinel/enable-monitoring) |
| **Security Copilot SCUs provisioned** | Required to run the Diagnostics Agent. [Set up Copilot capacity](https://learn.microsoft.com/en-us/copilot/security/get-started-security-copilot) |
| **This repo cloned locally** | Agent reads `agent-instructions.md` from `Tools/CCF-Connector-Observability-Accelerator/` and deploys the ARM template from `Data Connectors/CCFObservability_CCF/CCFObservability_ArmTemplate.json` — [browse on GitHub](https://github.com/Azure/Azure-Sentinel/tree/master/Tools/CCF-Connector-Observability-Accelerator) |

**What gets deployed:**

- **Azure Function App** — the controllable mock API with all error-injection switch endpoints
- **Log Analytics workspace** — new or existing; Sentinel is enabled on it
- **CCF connector** — `RestApiPoller` connector definition and solution registered in Sentinel
- **`CCFObservabilityEvents_CL` table** — custom Log Analytics table for ingested synthetic events
- **DCR** — Data Collection Rule with KQL transform, provisioned when you click Connect

Paste the following into **GitHub Copilot Chat** in VS Code (Agent mode):

```
Load and follow the deployment instructions at Tools/CCF-Connector-Observability-Accelerator/agent-instructions.md. Let's deploy the CCF Observability lab.
```

The agent collects all required values, generating names you haven't specified, then deploys end-to-end and verifies data is flowing into `CCFObservabilityEvents_CL`. The only manual step is clicking **Connect** once in the Sentinel portal.

> Full agent instructions: [`agent-instructions.md`](./agent-instructions.md)

---

## Architecture

```
Sentinel CCF connector  ──GET /api/main──►  Function App (/api/main)
                                                   │
                                            reads switch state
                                                   │
                                            Azure Blob Storage
                                            (switch-state.json)
                                                   ▲
                              POST /api/switch*  ──┘
```

State is persisted in a blob (`ccf-observability/switch-state.json`) so it survives Function App restarts and scale-out.

---

## Endpoints

### Data endpoint (what the CCF connector calls)

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/main` | Mock data source. Returns synthetic network-log events. Always validates `X-API-Key`. Behavior changes based on active switches. |

### Control endpoints (what you call manually)

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/status` | Read current switch state (non-destructive). |
| `POST` | `/api/switchapikey` | Reverse the accepted API key string (`abc123` → `321cba` → `abc123` → …). A connector using the previous key receives **HTTP 401**. |
| `POST` | `/api/switchhttpstatus?code=<int>` | Force `/api/main` to return any 4xx/5xx. Default: 500. Try `429` (rate-limited), `401` (auth), `503` (unavailable). |
| `POST` | `/api/switchempty` | Force `/api/main` to return **HTTP 200 with an empty data array**. Simulates a healthy connector ingesting no records. |
| `POST` | `/api/switchlatency?delay_seconds=<int>` | Inject a sleep before `/api/main` responds. Default: 70s. Since the connector's `timeoutInSeconds` is 60, this triggers a timeout error. |
| `POST` | `/api/switchpagination` | Force `/api/main` to always return `hasNextPage: true`. The connector pages indefinitely, never advancing its checkpoint. |
| `POST` | `/api/revert` | **Reset everything.** All switches off, API key back to `abc123`. |

> **Switches are independent and additive.** You can enable `switchlatency` and `switchhttpstatus` simultaneously to combine error conditions.

---

## Default state

| Setting | Default value |
|---------|---------------|
| Accepted API key | `abc123` |
| HTTP status override | disabled |
| Empty response | disabled |
| Latency injection | disabled |
| Pagination corruption | disabled |

---

## Quick start

### 1. Deploy the Function App

> **Deployed:** `https://ccf-observability.azurewebsites.net` (centralus, rg-ccf-observability)

```bash
# Create resources
az group create -n rg-ccf-observability -l centralus
az storage account create -n stccfobs -g rg-ccf-observability --sku Standard_LRS
az functionapp create \
  -n ccf-observability \
  -g rg-ccf-observability \
  --consumption-plan-location centralus \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --storage-account stccfobs \
  --os-type Linux

# Deploy code
cd FunctionApp
func azure functionapp publish ccf-observability
```

### 2. Deploy the CCF connector *(manual)*

> **This step must be completed manually.** Fill in the template variables in
> `Data Connectors/CCFObservability_CCF/CCFObservability_PollerConfig.json`,
> then deploy the DCR and connector through the Azure portal or ARM.

| Variable | Where to get it |
|----------|-----------------|
| `{{location}}` | Azure region, e.g. `centralus` |
| `{{BaseUrl}}` | `https://ccf-observability.azurewebsites.net` |
| `{{dataCollectionEndpoint}}` | Your DCE endpoint URI (created with the DCR) |
| `{{dataCollectionRuleImmutableId}}` | Immutable ID from `CCFObservability_DCR.json` deployment output |
| `{{ApiKey}}` | `abc123` (default; rotate with `/api/switchapikey`) |

Deploy via ARM:
```bash
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.SecurityInsights/dataConnectors/CCFObservabilityConnector?api-version=2023-02-01-preview" \
  --body @"Data Connectors/CCFObservability_CCF/CCFObservability_PollerConfig.json"
```

### 3. Inject errors and observe

```bash
BASE=https://ccf-observability.azurewebsites.net  # deployed to centralus

# Check current state
curl $BASE/api/status

# Rotate API key → connector gets 401
curl -X POST $BASE/api/switchapikey

# Force 429 Too Many Requests
curl -X POST "$BASE/api/switchhttpstatus?code=429"

# Force empty ingestion
curl -X POST $BASE/api/switchempty

# Force timeout (70s sleep, connector timeout is 60s)
curl -X POST $BASE/api/switchlatency

# Break pagination
curl -X POST $BASE/api/switchpagination

# Revert everything
curl -X POST $BASE/api/revert
```

After each switch, open **Sentinel → Data Connectors → CCF Observability Connector → Data connector diagnostics** and observe how the Diagnostics Agent surfaces and explains the induced error.

---

## Enabling the Diagnostics Agent

The **Data Connector Diagnostics Agent** is a private preview feature in Microsoft Security Copilot (Aug 2026). Complete the steps below before running diagnostics against the CCF Observability connector.

### Prerequisites

| Requirement | Notes |
|---|---|
| **Microsoft Sentinel workspace** | Commercial clouds only — US Gov, China Gov, and other sovereign clouds are out of scope |
| **Microsoft Sentinel Contributor role** | Required on the workspace |
| **Sentinel health monitoring enabled** | Populates the `SentinelHealth` table the Diagnostics Agent queries. [Enable health monitoring](https://learn.microsoft.com/en-us/azure/sentinel/enable-monitoring) |
| **Security Copilot with active SCUs** | SCU consumption incurs charges during testing. [Set up Copilot capacity](https://learn.microsoft.com/en-us/copilot/security/get-started-security-copilot) |
| **Private preview sign-up** | [Fill out the sign-up form](https://forms.cloud.microsoft/r/RBS8LuTrnt) before proceeding |

### Workflow

1. **Enable prerequisites** — provision SCU capacity and enable Sentinel health monitoring (both required before data flows)
2. **Deploy and connect** — deploy the Function App, register the connector, click Connect
3. **Verify data** — confirm `CCFObservabilityEvents_CL` is receiving records
4. **Inject an error** — use a switch endpoint (e.g. `switchhttpstatus?code=429`) to force a specific connector error
5. **Run diagnostics** — open **Data connector diagnostics** in the connector page; Security Copilot surfaces the error with remediation steps
6. **Revert and repeat** — call `/api/revert` and try another switch

---

## Local development

```bash
cd FunctionApp
cp local.settings.json.example local.settings.json
# Edit local.settings.json: set AzureWebJobsStorage to a real connection string
# or install Azurite and use UseDevelopmentStorage=true

pip install -r requirements.txt
func start
```

---

## Observability test matrix

| Switch | Expected connector error | Diagnostics Agent should surface |
|--------|--------------------------|----------------------------------|
| `switchapikey` | HTTP 401 | Invalid / expired API key |
| `switchhttpstatus?code=429` | HTTP 429 | Rate-limited; backoff recommended |
| `switchhttpstatus?code=500` | HTTP 500 | Source API internal error |
| `switchhttpstatus?code=503` | HTTP 503 | Source API unavailable |
| `switchempty` | No ingestion gap (healthy 200) | Connector healthy but no data flowing |
| `switchlatency` | Timeout | Request timed out; check source latency |
| `switchpagination` | Stalled checkpoint / high volume | Pagination loop detected |

---

## File structure

```
CCF-Connector-Observability-Accelerator/
├── FunctionApp/
│   ├── function_app.py          # All HTTP function endpoints
│   ├── state_manager.py         # Blob-backed switch state
│   ├── host.json
│   ├── local.settings.json.example
│   └── requirements.txt
├── Data Connectors/
│   └── CCFObservability_CCF/
│       ├── CCFObservability_ArmTemplate.json
│       ├── CCFObservability_ConnectorDefinition.json
│       ├── CCFObservability_DCR.json
│       ├── CCFObservability_PollerConfig.json
│       └── CCFObservability_Table.json
├── Data/
│   └── Solution_CCFObservability.json
├── agent-instructions.md
├── README.md
├── ReleaseNotes.md
└── SolutionMetadata.json
```

> **GitHub:** [Azure/Azure-Sentinel → Tools/CCF-Connector-Observability-Accelerator](https://github.com/Azure/Azure-Sentinel/tree/master/Tools/CCF-Connector-Observability-Accelerator)
