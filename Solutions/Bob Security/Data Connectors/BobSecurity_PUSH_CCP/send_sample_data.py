"""Send three sample Unified Agent Risk records to Microsoft Sentinel.

Install dependencies:
    python -m pip install azure-identity azure-monitor-ingestion

Set these environment variables before running:
    AZURE_TENANT_ID
    AZURE_CLIENT_ID
    AZURE_CLIENT_SECRET
    DATA_COLLECTION_ENDPOINT
    LOGS_DCR_RULE_ID
    LOGS_DCR_STREAM_NAME

The tenant ID is used only for OAuth authentication. TenantId is reserved and
is not included in the uploaded records.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from azure.identity import ClientSecretCredential
from azure.monitor.ingestion import LogsIngestionClient


def utc_timestamp(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def create_samples():
    now = datetime.now(timezone.utc)
    event_suffix = f"{now:%Y%m%d%H%M%S}"

    # Required fields
    required = {
        "PartnerSchemaVersion": "1.0.0",
        "EventSchema": "AlertEvent",
        "EventSchemaVersion": "0.1",
        "EventType": "Alert",
        "EventSubType": "Threat",
        "SignalCategory": "RuntimeRisk",
        "EventCount": 1,
        "EventUid": f"urn:uuid:{uuid4()}",
        "EventOriginalUid": f"BOB-ALERT-{event_suffix}-01",
        "EventVendor": "Bob Security",
        "EventProduct": "Bob Security",
        "EventStartTime": utc_timestamp(now - timedelta(minutes=10)),
        "EventEndTime": utc_timestamp(now - timedelta(minutes=5)),
        "SourceUpdatedTime": utc_timestamp(now - timedelta(minutes=1)),
        "AlertName": "Unauthorized payment-export tool invocation",
        "EventMessage": (
            "Finance agent invoked ExportPayments outside its approved workflow."
        ),
        "EventSeverity": "High",
        "AlertStatus": "Active",
        "DetectionId": "bob.runtime.unauthorized_tool",
        "RiskLevel": "High",
        "EntityType": "Agent",
        "EntityId": str(uuid4()),
        "EntityIdType": "EntraObjectId",
    }
    required["RawData"] = required.copy()

    # Required and recommended fields
    required_and_recommended = required.copy()
    required_and_recommended.update(
        {
            "EventUid": f"urn:uuid:{uuid4()}",
            "EventOriginalUid": f"BOB-ALERT-{event_suffix}-02",
            "EntityId": str(uuid4()),
            "AlertStatusChangedTime": utc_timestamp(now - timedelta(minutes=2)),
            "EventOriginalSeverity": "Critical",
            "AlertOriginalStatus": "Open",
            "RuleName": "Unauthorized tool invocation",
            "RuleDescription": (
                "Detects tools used outside the approved workflow."
            ),
            "DetectionMethod": "BehavioralAnalytics",
            "ThreatCategory": "CredentialAccess",
            "ThreatConfidence": 87,
            "AttackTactics": "CredentialAccess",
            "AttackTechniques": "T1555",
            "EntityOriginalId": "agent-98421",
            "EntityOriginalIdType": "PartnerAgentId",
            "EntityName": "finance-reconciliation-agent",
            "IdentityType": "AgentIdentity",
            "AgentName": "Finance Reconciliation Agent",
            "AgentPlatform": "MicrosoftCopilotStudio",
            "AgentResourceUri": "https://agents.contoso.example/finance",
            "UserId": str(uuid4()),
            "UserIdType": "EntraObjectId",
            "Username": "alexw@contoso.example",
            "UsernameType": "UPN",
            "DvcId": str(uuid4()),
            "DvcIdType": "EntraDeviceId",
            "EventSessionId": f"session-{event_suffix}-02",
        }
    )
    required_and_recommended.pop("RawData")
    required_and_recommended["RawData"] = required_and_recommended.copy()

    # Required, recommended, and optional fields
    complete = required_and_recommended.copy()
    complete.update(
        {
            "EventUid": f"urn:uuid:{uuid4()}",
            "EventOriginalUid": f"BOB-ALERT-{event_suffix}-03",
            "EntityId": str(uuid4()),
            "UserId": str(uuid4()),
            "DvcId": str(uuid4()),
            "EventSessionId": f"session-{event_suffix}-03",
            "AlertStatusReason": "Tool access revoked by administrator",
            "AlertVerdict": "True positive",
            "ThreatRiskLevel": 92,
            "AttackRemediationSteps": (
                "Disable the tool, rotate the delegated credential, and review "
                "related sessions."
            ),
            "AgentBlueprintId": "blueprint-finance-v3",
            "ActorUserId": str(uuid4()),
            "ActorUserIdType": "EntraObjectId",
            "ActorUsername": "jamie@contoso.example",
            "SrcIpAddr": "203.0.113.42",
            "DvcMDEid": "mde-2fd89c41",
            "DvcEntraId": str(uuid4()),
            "ToolId": "tool-payments-export",
            "ToolName": "ExportPayments",
            "ToolDescription": "Exports payment records.",
            "ToolArguments": {
                "dateRange": "2026-Q3",
                "destination": "[REDACTED]",
            },
            "ResourceId": "storage://finance-reports/q3",
            "ResourceType": "StorageAccount",
            "ResourceName": "finance-reports",
            "DataClassification": "Regulated PII",
            "EventOriginalRequestDetails": "[REDACTED] Export Q3 payments",
            "EventOriginalResultDetails": "Blocked by agent policy",
            "EventReportUrl": (
                "https://bobsecurity.com/alerts/"
                f"{event_suffix}-03"
            ),
            "AdditionalFields": {
                "policyId": "POL-417",
                "region": "us",
            },
        }
    )
    complete.pop("RawData")
    complete["RawData"] = complete.copy()

    return [
        ("required", required),
        ("required and recommended", required_and_recommended),
        ("required, recommended, and optional", complete),
    ]


def main():
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    client = LogsIngestionClient(
        endpoint=os.environ["DATA_COLLECTION_ENDPOINT"],
        credential=credential,
    )

    try:
        for sample_name, record in create_samples():
            client.upload(
                rule_id=os.environ["LOGS_DCR_RULE_ID"],
                stream_name=os.environ["LOGS_DCR_STREAM_NAME"],
                logs=[record],
            )
            print(
                f"Uploaded {sample_name} sample "
                f"(EventUid={record['EventUid']})."
            )
    finally:
        client.close()
        credential.close()


if __name__ == "__main__":
    main()
