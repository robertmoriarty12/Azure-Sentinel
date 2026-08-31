"""
CCF Observability Function App

Endpoints
---------
GET  /api/main              Mock data source that a CCF RestApiPoller connector polls.
                            Always validates X-API-Key against the current active key.

GET  /api/status            Read-only view of all active switches.

POST /api/switchapikey      Rotate the accepted API key (abc123 <-> abc321).
                            When the connector's key no longer matches, it receives HTTP 401.

POST /api/switchhttpstatus  Force /main to return a specific HTTP error.
                            Query param: ?code=<4xx|5xx>  (default 500)

POST /api/switchempty       Force /main to return HTTP 200 with an empty data array.
                            Simulates a healthy connector that ingests no records.

POST /api/switchlatency     Inject a sleep before /main responds.
                            Query param: ?delay_seconds=<int>  (default 70, capped at 230)

POST /api/switchpagination  Force /main to return hasNextPage=true up to page 20.
                            Connector pages beyond normal depth without advancing its checkpoint.

POST /api/revert            Reset all switches to defaults. /main returns real events
                            and accepts the primary key 'abc123'.
"""

import copy
import json
import logging
import random
import string
import time
from datetime import datetime, timedelta, timezone

import azure.functions as func

from state_manager import DEFAULT_STATE, get_state, save_state

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(body: dict | list, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, indent=2),
        status_code=status_code,
        mimetype="application/json",
    )


def _synthetic_events(count: int) -> list:
    """Generate synthetic network-log-style events for /main to return."""
    return [
        {
            "id": f"obs-{''.join(random.choices(string.hexdigits[:16], k=8))}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_ip": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
            "destination_ip": f"203.0.{random.randint(100,150)}.{random.randint(1,254)}",
            "action": random.choice(["ALLOW", "DENY", "DROP", "ALERT"]),
            "severity": random.choice(["informational", "low", "medium", "high", "critical"]),
            "protocol": random.choice(["TCP", "UDP", "ICMP"]),
            "bytes_transferred": random.randint(256, 65536),
            "message": "CCF Observability synthetic event",
        }
        for _ in range(count)
    ]


def _int_param(req: func.HttpRequest, name: str, default: int) -> int:
    """Read an integer from query params, then request body, falling back to default."""
    val = req.params.get(name)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    try:
        return int(req.get_json().get(name, default))
    except Exception:
        return default


# ---------------------------------------------------------------------------
# GET /api/main
# ---------------------------------------------------------------------------

@app.route(route="main", methods=["GET"])
def main(req: func.HttpRequest) -> func.HttpResponse:
    state = get_state()
    logging.info("main called | since=%s page=%s pageSize=%s",
                 req.params.get("since", "<absent>"),
                 req.params.get("page", "<absent>"),
                 req.params.get("pageSize", "<absent>"))

    # ── 1. API key validation (always enforced) ──────────────────────────────
    provided_key = req.headers.get("X-API-Key", "")
    if provided_key != state["apikey"]["active_key"]:
        return _json(
            {"status": "error", "message": "Unauthorized: invalid or missing API key"},
            status_code=401,
        )

    # ── 2. Force HTTP error ───────────────────────────────────────────────────
    if state["httpstatus"]["enabled"]:
        code = state["httpstatus"]["code"]
        return _json(
            {"status": "error", "message": f"Simulated HTTP {code} error (switchhttpstatus active)"},
            status_code=code,
        )

    # ── 3. Latency injection ─────────────────────────────────────────────────
    if state["latency"]["enabled"]:
        delay = state["latency"]["delay_seconds"]
        logging.info("Latency switch active — sleeping %ds", delay)
        time.sleep(delay)

    # ── 4. Empty payload ──────────────────────────────────────────────────────
    if state["empty"]["enabled"]:
        return _json({
            "status": "success",
            "data": [],
            "metadata": {"hasNextPage": False, "page": 1, "pageSize": 5, "total": 0},
        })

    # ── 5. Normal response (with optional pagination corruption) ──────────────
    page = max(1, int(req.params.get("page", 1)))
    page_size = min(max(1, int(req.params.get("pageSize", 5))), 100)

    # Threshold must exceed queryWindowInMin (1) so current windows aren't blocked.
    since_str = req.params.get("since", "")
    if since_str:
        try:
            since_dt = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - since_dt > timedelta(minutes=2):
                return _json({
                    "status": "success",
                    "data": [],
                    "metadata": {"hasNextPage": False, "page": page, "pageSize": page_size, "total": 0},
                })
        except (ValueError, TypeError):
            pass

    # Pagination switch: full page returned so CountBasedPaging keeps requesting next pages.
    if state["pagination"]["enabled"]:
        events = _synthetic_events(page_size)
        has_next = page < 20
        total = page_size * 20
    else:
        # Only page 1 returns data; page 2+ returns empty to hard-stop CCF pagination.
        events = _synthetic_events(page_size - 2) if page == 1 else []
        has_next = False
        total = len(events)

    return _json({
        "status": "success",
        "data": events,
        "metadata": {
            "hasNextPage": has_next,
            "page": page,
            "pageSize": page_size,
            "total": total,
        },
    })


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------

@app.route(route="status", methods=["GET"])
def status_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    state = get_state()
    return _json({
        "active_api_key": state["apikey"]["active_key"],
        "switches": {
            "httpstatus": state["httpstatus"],
            "empty": state["empty"],
            "latency": state["latency"],
            "pagination": state["pagination"],
        },
        "tip": "POST /api/revert to reset everything to defaults",
    })


# ---------------------------------------------------------------------------
# POST /api/switchapikey
# ---------------------------------------------------------------------------

@app.route(route="switchapikey", methods=["POST"])
def switch_api_key(req: func.HttpRequest) -> func.HttpResponse:
    state = get_state()
    ak = state["apikey"]
    previous = ak["active_key"]
    ak["active_key"] = previous[::-1]
    save_state(state)
    return _json({
        "message": f"API key reversed. /api/main now accepts '{ak['active_key']}'",
        "hint": (
            f"A connector configured with '{previous}' will now receive HTTP 401. "
            "Call this endpoint again to reverse back."
        ),
        "state": state,
    })


# ---------------------------------------------------------------------------
# POST /api/switchhttpstatus[?code=<int>]
# ---------------------------------------------------------------------------

@app.route(route="switchhttpstatus", methods=["POST"])
def switch_http_status(req: func.HttpRequest) -> func.HttpResponse:
    code = _int_param(req, "code", 500)
    if code not in range(400, 600):
        return _json({"error": "code must be an HTTP 4xx or 5xx value"}, status_code=400)
    state = get_state()
    state["httpstatus"]["enabled"] = True
    state["httpstatus"]["code"] = code
    save_state(state)
    return _json({
        "message": f"HTTP status switch ENABLED. /api/main returns HTTP {code} on every request.",
        "state": state,
    })


# ---------------------------------------------------------------------------
# POST /api/switchempty
# ---------------------------------------------------------------------------

@app.route(route="switchempty", methods=["POST"])
def switch_empty(req: func.HttpRequest) -> func.HttpResponse:
    state = get_state()
    state["empty"]["enabled"] = True
    save_state(state)
    return _json({
        "message": "Empty switch ENABLED. /api/main returns HTTP 200 with an empty data array.",
        "hint": "This simulates a connector that is reachable but ingesting zero records.",
        "state": state,
    })


# ---------------------------------------------------------------------------
# POST /api/switchlatency[?delay_seconds=<int>]
# ---------------------------------------------------------------------------

@app.route(route="switchlatency", methods=["POST"])
def switch_latency(req: func.HttpRequest) -> func.HttpResponse:
    delay = _int_param(req, "delay_seconds", 70)
    delay = max(1, min(delay, 230))  # cap at Function App HTTP trigger max
    state = get_state()
    state["latency"]["enabled"] = True
    state["latency"]["delay_seconds"] = delay
    save_state(state)
    return _json({
        "message": f"Latency switch ENABLED. /api/main sleeps {delay}s before responding.",
        "hint": (
            f"The CCF connector's timeoutInSeconds is 60 by default. "
            f"With a {delay}s delay it will time out and log an error."
        ),
        "state": state,
    })


# ---------------------------------------------------------------------------
# POST /api/switchpagination
# ---------------------------------------------------------------------------

@app.route(route="switchpagination", methods=["POST"])
def switch_pagination(req: func.HttpRequest) -> func.HttpResponse:
    state = get_state()
    state["pagination"]["enabled"] = True
    save_state(state)
    return _json({
        "message": "Pagination switch ENABLED. /api/main always returns hasNextPage=true.",
        "hint": (
            "The connector will page indefinitely. "
            "This can cause checkpoint stalls and high ingestion volume warnings."
        ),
        "state": state,
    })


# ---------------------------------------------------------------------------
# POST /api/revert
# ---------------------------------------------------------------------------

@app.route(route="revert", methods=["POST"])
def revert(req: func.HttpRequest) -> func.HttpResponse:
    clean = copy.deepcopy(DEFAULT_STATE)
    save_state(clean)
    return _json({
        "message": "All switches reverted. /api/main is operating normally.",
        "note": "Active API key reset to 'abc123'. All error switches disabled.",
        "state": clean,
    })
