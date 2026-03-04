"""
Azure Function App – Sample Microsoft Sentinel Data Connector
Uses the Azure Monitor Ingestion API (DCE/DCR) to push sample JSON events
into a Microsoft Sentinel custom table on a timer schedule.

Required Application Settings (set in the Function App Configuration blade):
    TENANT_ID       – Azure AD Tenant ID
    CLIENT_ID       – App Registration (Service Principal) Client ID
    CLIENT_SECRET   – App Registration Client Secret
    DCE_ENDPOINT    – Data Collection Endpoint URL
                      e.g. https://my-dce-abcd.eastus-1.ingest.monitor.azure.com
    DCR_ID          – Data Collection Rule immutableId  (dcr-xxxxxxxxxxxxx)
    STREAM_NAME     – Stream name defined in the DCR  (e.g. Custom-FunctionAppSample_CL)
"""

import os
import logging
from datetime import datetime, timezone

import azure.functions as func
from azure.identity import ClientSecretCredential
from azure.monitor.ingestion import LogsIngestionClient
from azure.core.exceptions import HttpResponseError

# ---------------------------------------------------------------------------
# Read configuration from Application Settings
# ---------------------------------------------------------------------------
TENANT_ID     = os.environ["TENANT_ID"]
CLIENT_ID     = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
DCE_ENDPOINT  = os.environ["DCE_ENDPOINT"]
DCR_ID        = os.environ["DCR_ID"]
STREAM_NAME   = os.environ["STREAM_NAME"]


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
        logging.warning("Timer is running late!")

    logging.info("FunctionApp Sentinel connector starting at %s", utc_timestamp)

    # 1. Authenticate
    try:
        credential = ClientSecretCredential(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
        logging.info("Authentication credential created successfully.")
    except Exception as exc:
        logging.error("Failed to create Azure credential: %s", exc)
        raise

    # 2. Create ingestion client
    client = LogsIngestionClient(endpoint=DCE_ENDPOINT, credential=credential)

    # 3. Build sample events
    events = build_sample_events()
    logging.info("Prepared %d sample event(s) for ingestion.", len(events))

    # 4. Upload to Sentinel via DCE/DCR
    try:
        client.upload(rule_id=DCR_ID, stream_name=STREAM_NAME, logs=events)
        logging.info(
            "Successfully ingested %d event(s) into stream '%s'.",
            len(events),
            STREAM_NAME,
        )
    except HttpResponseError as exc:
        logging.error(
            "Azure Monitor Ingestion API error: %s\n"
            "Check that the App Registration has the 'Monitoring Metrics Publisher' "
            "role on the DCR, and that DCE_ENDPOINT / DCR_ID / STREAM_NAME are correct.",
            exc,
        )
        raise
    except Exception as exc:
        logging.error("Unexpected error during ingestion: %s", exc)
        raise

    logging.info("FunctionApp Sentinel connector finished at %s", utc_timestamp)
