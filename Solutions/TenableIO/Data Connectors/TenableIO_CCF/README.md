# ⚠️ Tenable.io CCF Connector - CRITICAL LIMITATIONS

## 🔴 WARNING: THIS CONNECTOR WILL NOT FUNCTION PROPERLY

This CCF (Codeless Connector Format) connector for Tenable.io has **fundamental architectural limitations** that prevent it from working correctly. It was created per explicit request despite technical incompatibility.

---

## Why This Connector Cannot Work

### Tenable Export API Architecture
Tenable.io uses an **asynchronous export job system**:

1. **POST** `/vulns/export` → Creates export job, returns UUID
2. **GET** `/vulns/export/{uuid}/status` → Poll until status = "FINISHED" (takes minutes/hours)
3. **GET** `/vulns/export/{uuid}/chunks/{id}` → Download data chunks

### CCF REST API Poller Limitations
CCF is designed for **synchronous paginated APIs**:
- Cannot create jobs then poll different endpoints
- Cannot handle multi-step async workflows
- Cannot iterate over dynamically discovered chunks
- No state persistence between polling cycles

---

## Known Issues

### ❌ Export Jobs Never Complete
- CCF POST creates export job but **never waits for completion**
- Status endpoint shows "PROCESSING" indefinitely
- No mechanism to retry status checks until "FINISHED"

### ❌ No Data Collection
- Even if export completes, CCF doesn't know chunk IDs
- Cannot iterate over `chunks_available` array
- Chunk download requires export UUID from previous step

### ❌ No Error Handling
- No retry logic for failed jobs
- No cleanup of stuck export jobs
- No chunking for large payloads (30MB limit)

### ❌ Performance Issues
- Creates new export job every polling cycle
- Cannot process chunks in parallel
- No queue-based distribution

---

## Recommended Solution

**USE THE EXISTING AZURE DURABLE FUNCTIONS CONNECTOR**

The current Function App implementation at [`../`](../):
- ✅ Properly handles async export jobs
- ✅ Polls status until completion
- ✅ Downloads all chunks reliably
- ✅ Partitions data into <30MB sub-chunks
- ✅ Implements retry logic and error handling
- ✅ Provides state management and cleanup

---

## Files in This Directory

- **README.md** (this file) - Critical limitation documentation
- **TenableIO_PollingConfig.json** - Non-functional polling configurations
- **TenableIO_Tables.json** - Table schema definitions
- **TenableIO_DCR.json** - Data collection rule (minimal)
- **TenableIO_ConnectorDefinition.json** - UI definition only

**All files are placeholders and do not provide working data collection.**

---

## Alternative Approaches

1. **Keep Function App** (Recommended) - Current implementation is optimal
2. **Request Tenable API Changes** - Ask for synchronous list endpoints:
   - `GET /api/3/vulnerabilities?limit=1000&offset=0`
   - `GET /api/3/assets?limit=1000&cursor={token}`
3. **Hybrid Solution** - Function App for data + CCF for UI only

---

## Technical Details

**Authentication**: API Key (Access Key + Secret Key)
**Base URL**: `https://cloud.tenable.com`
**Data Types**: Assets (`Tenable_IO_Assets_CL`), Vulnerabilities (`Tenable_IO_Vuln_CL`)

**Export API Endpoints**:
- POST `/assets/export`
- POST `/vulns/export`
- GET `/{type}/export/{uuid}/status`
- GET `/{type}/export/{uuid}/chunks/{id}`

**Why Each Endpoint Fails in CCF**:
- POST export: Creates job but CCF moves to next step immediately
- GET status: CCF polls once, doesn't retry until "FINISHED"
- GET chunks: CCF doesn't know chunk IDs, can't iterate dynamically

---

## Support

For functional Tenable.io data collection, please use the Azure Durable Functions connector located in the parent directory.

**Created**: 2026-01-11  
**Status**: Non-functional by design  
**Maintenance**: Documentation only