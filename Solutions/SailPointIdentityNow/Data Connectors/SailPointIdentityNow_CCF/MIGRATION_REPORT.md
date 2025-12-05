# SailPoint IdentityNow CCF Connector - Migration Report

## Migration Summary

**Connector Name**: SailPoint IdentityNow  
**Migration Date**: December 4, 2024  
**Source**: Azure Function App (`SearchEvent/__init__.py`)  
**Target**: Codeless Connector Framework (CCF)  
**Status**: ✅ Complete

---

## Migration Details

### 1. Source Analysis

**Function App Location**: `Solutions/SailPointIdentityNow/Data Connectors/SearchEvent/__init__.py`

**Key Findings**:
- **API Endpoint**: `https://{tenant}.api.identitynow.com/v2025/search/events`
- **Authentication**: OAuth2 client_credentials flow
- **Pagination**: Offset-based with `limit` and `offset` parameters (250 events per page)
- **Rate Limiting**: 1 request per second
- **Time Window**: 5-minute polling intervals
- **Response Format**: JSON array under `$.events` path

### 2. CCF Components Created

#### Polling Configuration (`SailPointIdentityNow_PollingConfig.json`)
- **Authentication**: OAuth2 client_credentials
  - Token Endpoint: `https://{{TenantId}}.api.identitynow.com/oauth/token`
  - Client ID and Secret from user input
  - **Note**: Removed forbidden `TokenEndpointQueryParameters` (Azure handles OAuth2 params automatically)
- **Request Configuration**:
  - HTTP Method: POST
  - Query Parameters: Dynamic time window with offset pagination
  - Rate Limit: 1 QPS
  - Timeout: 120 seconds (2 minutes)
- **Pagination**: Offset-based
  - Page Size: 250
  - Offset Parameter: `offset`
- **Data Extraction**: `$.events` JSON path

#### Table Schema (`SailPointIdentityNow_Tables.json`)
- **Table Name**: `SailPointIDNEvents_CL`
- **Columns** (18 fields):
  - TimeGenerated (datetime) - Required
  - Org (string)
  - Pod (string)
  - Created (datetime)
  - EventId (string)
  - Action (string)
  - EventType (string)
  - IpAddress (string)
  - Operation (string)
  - Status (string)
  - TechnicalName (string)
  - EventName (string)
  - Synced (datetime)
  - RecordType (string)
  - Actor (dynamic)
  - Target (dynamic)
  - Attributes (dynamic)
  - Objects (dynamic)

#### DCR Configuration (`SailPointIdentityNow_DCR.json`)
- **Stream**: `Custom-SailPointIDNEvents_CL`
- **Transform**: Comprehensive KQL mapping with:
  - Datetime conversions for timestamps
  - String extractions for simple fields
  - Dynamic type preservation for complex objects (Actor, Target, Attributes, Objects)
  - Explicit TimeGenerated setting
- **Destination**: Log Analytics workspace via template parameters

#### Connector Definition (`SailPointIdentityNow_ConnectorDefinition.json`)
- **Title**: "SailPoint IdentityNow (Serverless)"
- **Publisher**: "SailPoint Technologies"
- **Connectivity**: HasDataConnectors validation
- **User Inputs**:
  - Tenant ID (text)
  - Client ID (text)
  - Client Secret (password)
- **Monitoring**: 2-week data ingestion graph
- **Sample Queries**: Basic event selection and filtering examples

### 3. Key Decisions

**OAuth2 Configuration**:
- Initially included `TokenEndpointQueryParameters` with OAuth2 parameters
- **Fixed**: Removed parameters as Azure automatically constructs OAuth2 token requests
- This prevents "Invalid Token Endpoint query parameters" deployment errors

**API Domain**:
- Corrected from `identitynow-demo.com` to production `identitynow.com`
- Token endpoint and API endpoint both use production domain

**Schema Approach**:
- Single table with 18 columns
- Preserved complex objects (Actor, Target, Attributes, Objects) as dynamic type
- All timestamp fields converted to datetime for better querying

**Pagination Strategy**:
- Offset-based pagination matches function app implementation
- 250 events per page for efficient data transfer
- Respects API rate limits (1 QPS)

### 4. Deployment Fixes Applied

**Issue 1**: OAuth2 Token Endpoint Query Parameters
- **Error**: "Invalid Token Endpoint query parameters"
- **Root Cause**: Manual specification of OAuth2 parameters conflicts with Azure's automatic handling
- **Fix**: Removed `TokenEndpointQueryParameters` object entirely
- **Commit**: `2c89c83c73`

**Issue 2**: Domain Name
- **Problem**: Used demo domain instead of production
- **Fix**: Changed all endpoints from `identitynow-demo.com` to `identitynow.com`
- **Commit**: `2c89c83c73`

### 5. Validation Results

✅ **Authentication Block**: OAuth2 client_credentials properly configured  
✅ **Request Block**: API endpoint, method, and parameters validated  
✅ **Response Block**: JSON path extraction configured  
✅ **DCR Config**: Stream name follows naming convention  
✅ **Table Schema**: All required columns present, naming conventions followed  
✅ **DCR Transform**: KQL uses supported operations only, sets TimeGenerated  
✅ **Connector Definition**: All required fields present, UI controls aligned  
✅ **Parameter Consistency**: Template and user parameters properly distinguished  

### 6. Template Parameters Used

**Auto-Provided** (no UI controls):
- `{{location}}` - Azure region
- `{{workspaceResourceId}}` - Full workspace ARM ID
- `{{workspaceId}}` - Workspace GUID
- `{{dataCollectionEndpoint}}` - DCE URL
- `{{dataCollectionRuleImmutableId}}` - DCR immutable ID

**User-Provided** (UI controls created):
- `{{TenantId}}` - SailPoint tenant identifier
- `{{ClientId}}` - OAuth2 application client ID
- `{{ClientSecret}}` - OAuth2 application secret

### 7. Known Limitations

- OAuth2 scope not explicitly configured (relies on default scopes)
- No advanced filtering capabilities in UI (users must use KQL post-ingestion)
- Single table approach may not be optimal if event types diverge significantly in future API versions

### 8. Testing Recommendations

1. **Authentication**: Verify OAuth2 token acquisition with test tenant
2. **Data Ingestion**: Confirm events flowing to `SailPointIDNEvents_CL` table
3. **Pagination**: Test with >250 events to validate offset pagination
4. **Rate Limiting**: Monitor for 429 errors if API rate limits change
5. **Field Mapping**: Validate all 18 columns populate correctly
6. **Dynamic Fields**: Check Actor, Target, Attributes, Objects preserve JSON structure

### 9. Migration Artifacts

**Files Created**:
1. `SailPointIdentityNow_PollingConfig.json` - REST API Poller configuration
2. `SailPointIdentityNow_Tables.json` - Log Analytics table schema
3. `SailPointIdentityNow_DCR.json` - Data Collection Rule with transforms
4. `SailPointIdentityNow_ConnectorDefinition.json` - UI definition and metadata

**Files Modified**:
1. `Solution_SailpointIdentityNow.json` - Added CCF connector reference to Data Connectors array

### 10. Deployment Notes

- Connector deployed to user's fork: `https://github.com/robertmoriarty12/Azure-Sentinel.git`
- Branch: `ccf/sailpoint-identitynow`
- Commits:
  - `f052cd25a3` - Initial CCF connector migration
  - `c43ad62bbe` - OAuth2 configuration fix

---

## Conclusion

The SailPoint IdentityNow connector has been successfully migrated from Azure Function App to CCF format. The connector uses OAuth2 client_credentials authentication, offset-based pagination, and ingests events into a single Log Analytics table with 18 columns including dynamic fields for complex objects.

**Deployment Issue Resolved**: OAuth2 token endpoint parameters were removed to comply with Azure's automatic OAuth2 handling, resolving deployment errors.

**Next Steps**:
1. Test connector deployment in Azure Sentinel
2. Verify data ingestion and field mapping
3. Submit pull request to Azure-Sentinel repository if validation successful