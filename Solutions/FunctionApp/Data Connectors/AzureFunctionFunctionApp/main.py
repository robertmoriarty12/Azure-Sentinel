"""
Azure Function App – Sample Microsoft Sentinel Data Connector
Uses the Azure Monitor Ingestion API (DCE/DCR) to push sample JSON events
into a Microsoft Sentinel custom table on a timer schedule.

Application Settings (automatically configured by the ARM template deployment):
    TENANT_ID       – Azure AD Tenant ID
    CLIENT_ID       – App Registration (Service Principal) Client ID
    CLIENT_SECRET   – App Registration Client Secret
    DCE_ENDPOINT    – Data Collection Endpoint logs-ingestion URL (set from DCE resource)
    DCR_ID          – Data Collection Rule immutableId (set from DCR resource)
    STREAM_NAME     – Stream name defined in the DCR  (e.g. Custom-FunctionAppSample_CL)
"""

import os
import logging
from datetime import datetime, timezone

import azure.functions as func
from azure.identity import ClientSecretCredential
from azure.monitor.ingestion import LogsIngestionClient
from azure.core.exceptions import HttpResponseError, ClientAuthenticationError

# ---------------------------------------------------------------------------
# Read configuration from Application Settings at module level.
# os.environ.get() is used so the module loads cleanly even if a setting is
# temporarily absent; missing values will surface as errors at invocation time.
# ---------------------------------------------------------------------------
TENANT_ID     = os.environ.get("TENANT_ID")
CLIENT_ID     = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
DCE_ENDPOINT  = os.environ.get("DCE_ENDPOINT")
DCR_ID        = os.environ.get("DCR_ID")
STREAM_NAME   = os.environ.get("STREAM_NAME")

logs_starts_with = "FunctionAppSample"
function_name    = "main"


def build_sample_events() -> list[dict]:
    """
    Build a small batch of sample events that will be ingested into Sentinel.
    Customise the fields to match your real-world data schema.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        {
            "TimeGenerated": now,
            "EventType":     "Informational",
            "Message":       "Sample informational event from Azure Function connector",
            "Severity":      "Informational",
            "Source":        "FunctionAppSample",
            "Category":      "Network",
            "SrcIpAddr":     "10.0.0.1",
            "DstIpAddr":     "10.0.0.2",
            "SrcPort":       12345,
            "DstPort":       443,
            "Action":        "Allow",
            "CustomField1":  "Value1",
            "CustomField2":  100,
        },
        {
            "TimeGenerated": now,
            "EventType":     "Alert",
            "Message":       "Sample alert event from Azure Function connector",
            "Severity":      "Medium",
            "Source":        "FunctionAppSample",
            "Category":      "Authentication",
            "SrcIpAddr":     "192.168.1.50",
            "DstIpAddr":     "10.0.0.5",
            "SrcPort":       54321,
            "DstPort":       22,
            "Action":        "Deny",
            "CustomField1":  "Value2",
            "CustomField2":  200,
        },
        {
            "TimeGenerated": now,
            "EventType":     "Warning",
            "Message":       "Sample warning event from Azure Function connector",
            "Severity":      "Low",
            "Source":        "FunctionAppSample",
            "Category":      "System",
            "SrcIpAddr":     "172.16.0.10",
            "DstIpAddr":     "10.0.0.1",
            "SrcPort":       8080,
            "DstPort":       80,
            "Action":        "Allow",
            "CustomField1":  "Value3",
            "CustomField2":  300,
        },
    ]


def main(mytimer: func.TimerRequest) -> None:
    """Entry point for the timer-triggered Azure Function."""
    utc_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if mytimer.past_due:
        logging.warning(f"{logs_starts_with} {function_name}: Timer is running late!")

    logging.info(f"{logs_starts_with} {function_name}: Connector starting at {utc_timestamp}")

    # 1. Build sample events
    events = build_sample_events()
    logging.info(f"{logs_starts_with} {function_name}: Prepared {len(events)} sample event(s) for ingestion.")

    # 2. Create credential and ingestion client per-invocation (Tenable pattern).
    #    This ensures fresh tokens on each run and clean error handling.
    try:
        creds = ClientSecretCredential(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
        ingestion_client = LogsIngestionClient(endpoint=DCE_ENDPOINT, credential=creds)
    except Exception as exc:
        logging.error(
            f"{logs_starts_with} {function_name}: Failed to create Azure credential or client. "
            f"Check TENANT_ID, CLIENT_ID, CLIENT_SECRET, DCE_ENDPOINT. Error: {exc}"
        )
        raise

    # 3. Upload to Sentinel via DCE/DCR
    try:
        ingestion_client.upload(rule_id=DCR_ID, stream_name=STREAM_NAME, logs=events)
        logging.info(
            f"{logs_starts_with} {function_name}: Successfully ingested {len(events)} event(s) "
            f"into stream '{STREAM_NAME}'."
        )
    except ClientAuthenticationError as exc:
        logging.error(
            f"{logs_starts_with} {function_name}: Authentication failed — check that CLIENT_ID / "
            f"CLIENT_SECRET / TENANT_ID are correct and the App Registration has the "
            f"'Monitoring Metrics Publisher' role on the DCR. Error: {exc}"
        )
        raise
    except HttpResponseError as exc:
        logging.error(
            f"{logs_starts_with} {function_name}: HTTP error from Azure Monitor Ingestion API. "
            f"Check DCE_ENDPOINT, DCR_ID, and STREAM_NAME. Error: {exc}"
        )
        raise
    except Exception as exc:
        logging.error(
            f"{logs_starts_with} {function_name}: Unexpected error during ingestion. Error: {exc}"
        )
        raise

    logging.info(f"{logs_starts_with} {function_name}: Connector finished at {utc_timestamp}")
