# Varonis SaaS CCF Connector (Experimental)

⚠️ **IMPORTANT: This is an experimental connector that requires Varonis API modifications to function properly.**

## Overview

This directory contains a Codeless Connector Framework (CCF) implementation for Varonis SaaS. This connector demonstrates the intended CCF approach but cannot function without modifications to the Varonis API.

## Files

- **VaronisSaaS_PollingConfig.json** - REST API Poller configuration
- **VaronisSaaS_Tables.json** - Log Analytics table schema definition
- **VaronisSaaS_DCR.json** - Data Collection Rule with transform logic
- **VaronisSaaS_ConnectorDefinition.json** - Connector UI definition

## Known Limitations & Required API Changes

### 1. Authentication Flow Incompatibility

**Current Varonis Implementation:**
- Two-step authentication process
- POST to `/api/authentication/api_keys/token` with `x-api-key` header
- Custom grant type: `varonis_custom`
- Returns Bearer token for subsequent API calls

**CCF Requirement:**
- Standard OAuth2 `client_credentials` flow
- Direct bearer token issuance
- Standard token endpoint behavior

**Required Change:** Varonis must support standard OAuth2 client_credentials authentication.

### 2. Multi-Step Search API Pattern

**Current Varonis Implementation:**
1. POST to `/app/dataquery/api/search/v2/search` with complex JSON body
2. Receive search ID in response
3. Poll `/app/dataquery/api/search/{searchId}` endpoint
4. Handle 304/206 status codes (data not ready)
5. Retry up to 30 times with 1-second delays
6. Parse results when 200 OK received

**CCF Limitation:**
- Nested polling with `stepInfo` available but limited
- Async polling with retry logic (304/206 → 200) not natively supported
- Complex POST body structure requires workarounds

**Current Workaround:** Simplified configuration that assumes pre-configured search ID. Users must manually create and configure searches in Varonis, then provide the search ID as input parameter.

**Required Change:** Varonis should provide a direct alert retrieval endpoint that accepts time range parameters and returns alerts synchronously.

### 3. Search ID Parameter

**Current Implementation:**
The connector requires a `SearchId` parameter that users must obtain by:
1. Creating a search in Varonis UI
2. Noting the search ID from the URL
3. Providing it during connector configuration

**Ideal Solution:** Direct API endpoint like `/api/alerts?startTime={start}&endTime={end}&maxResults={limit}`

## Authentication Workaround

The current configuration uses OAuth2 as a workaround:

```json
"auth": {
  "type": "OAuth2",
  "ClientId": "sentinel-integration",
  "ClientSecret": "{{ApiKey}}",
  "GrantType": "client_credentials",
  "TokenEndpoint": "{{BaseUrl}}/api/authentication/api_keys/token",
  "TokenEndpointHeaders": {
    "x-api-key": "{{ApiKey}}",
    "varonis-integration": "Microsoft Sentinel"
  }
}
```

This configuration attempts to map Varonis's custom auth to OAuth2 but **will not work** without Varonis API changes.

## Schema

The connector ingests alerts into the `VaronisAlerts_CL` table with 33 fields including:

- **TimeGenerated** (datetime) - Ingestion timestamp
- **AlertId** (guid) - Unique alert identifier
- **ThreatDetectionPolicyName** (string) - Policy that triggered alert
- **AlertSeverity** (string) - High/Medium/Low
- **AlertCategory** (string) - Alert classification
- **UserNames** (dynamic) - Involved user accounts
- **DeviceNames** (dynamic) - Involved devices
- **Assets** (dynamic) - Accessed resources
- **ContainsMaliciousExternalIPs** (boolean) - External threat indicator
- **EventsCount** (int) - Number of related events
- And 23 additional fields for comprehensive alert context

## Data Collection Rule Transform

The DCR applies the following transformations:

```kql
source 
| extend TimeGenerated = now(), 
         AlertId = toguid(AlertId), 
         AlertTime = todatetime(AlertTime),
         EventsCount = toint(EventsCount),
         InitialEventTimeUTC = todatetime(InitialEventTimeUTC),
         AlertTimeUTC = todatetime(AlertTimeUTC),
         InitialEventTime = todatetime(InitialEventTime),
         IngestTime = todatetime(IngestTime)
| project TimeGenerated, AlertId, ThreatDetectionPolicyName, [... all 33 fields ...]
```

## Recommendations for Varonis

To enable full CCF compatibility, Varonis should implement:

1. **Standard OAuth2 Support**
   - Support standard `client_credentials` grant type
   - Accept client_id and client_secret in standard OAuth2 format
   - Return standard OAuth2 token response

2. **Direct Alert Endpoint**
   - Endpoint: `GET /api/v2/alerts`
   - Query parameters: `startTime`, `endTime`, `maxResults`, `severities`, `statuses`
   - Response: Direct JSON array of alerts (no multi-step search required)
   - Pagination: Standard Link header or next_token pattern

3. **Simplified Authentication**
   - Accept API key as Bearer token directly: `Authorization: Bearer {api_key}`
   - Or implement standard OAuth2 client credentials flow

## Testing

This connector **cannot be tested** in its current state without Varonis API modifications. It serves as:

1. A reference implementation for the intended CCF approach
2. Documentation of the gap between current Varonis API and CCF requirements
3. A starting point for collaboration with Varonis to enable CCF support

## Contact

For questions or to request Varonis API enhancements:
- **Varonis Support:** Contact your Varonis representative
- **Microsoft Sentinel:** Follow standard CCF connector development guidelines

## Version History

- **v1.0.0 (Experimental)** - Initial CCF implementation demonstrating intended approach with documented limitations