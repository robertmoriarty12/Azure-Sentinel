"""
Blob-backed state manager for CCF Observability switches.

State is a single JSON blob in the 'ccf-observability' container.
On first access the container and blob are created with DEFAULT_STATE.
"""

import copy
import json
import logging
import os

from azure.storage.blob import BlobClient, BlobServiceClient

DEFAULT_STATE: dict = {
    "apikey": {
        # /main always validates X-API-Key against active_key.
        # /switchapikey reverses active_key (e.g. abc123 -> 321cba).
        "active_key": "abc123",
    },
    "httpstatus": {
        "enabled": False,
        "code": 500,
    },
    "empty": {
        "enabled": False,
    },
    "latency": {
        "enabled": False,
        "delay_seconds": 70,  # exceeds the connector's default 60s timeout
    },
    "pagination": {
        "enabled": False,
    },
}

_CONTAINER = "ccf-observability"
_BLOB_NAME = "switch-state.json"


def _blob_client() -> BlobClient:
    conn_str = os.environ["AzureWebJobsStorage"]
    svc = BlobServiceClient.from_connection_string(conn_str)
    container = svc.get_container_client(_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass  # container already exists
    return container.get_blob_client(_BLOB_NAME)


def get_state() -> dict:
    """Return current switch state, falling back to DEFAULT_STATE on any error."""
    try:
        data = _blob_client().download_blob().readall()
        return json.loads(data)
    except Exception:
        logging.warning("State blob missing or unreadable — returning defaults.")
        return copy.deepcopy(DEFAULT_STATE)


def save_state(state: dict) -> None:
    """Persist switch state to blob storage."""
    _blob_client().upload_blob(json.dumps(state, indent=2), overwrite=True)
