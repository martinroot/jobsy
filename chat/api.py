"""Jobsy chat: real-time order execution with agent streaming."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from bridge.events import events as bridge_events
from bridge.artifacts import list_artifacts, artifact_path
from orders.api import get_order, update_status, record_usage


def chat_history(order_number: str, limit: int = 200) -> dict:
    """Return order state + recent events + artifacts for the chat UI."""
    order = get_order(order_number)
    if not order:
        return {"ok": False, "error": "order not found"}
    evs = bridge_events(order_number, limit=limit)
    arts = list_artifacts(order_number)
    return {
        "ok": True,
        "order": order,
        "events": evs,
        "artifacts": arts,
    }


def send_message(order_number: str, text: str) -> dict:
    """Send a user message to the order's agent (start or continue a run)."""
    from bridge.runtime import run as run_agent
    order = get_order(order_number)
    if not order:
        return {"ok": False, "error": "order not found"}
    if order["status"] == "done":
        return {"ok": False, "error": "order already completed"}
    state = run_agent(order_number, instruction=text)
    return {"ok": True, "state": state}


def get_artifact(order_number: str, artifact_id: str) -> Path | None:
    return artifact_path(order_number, artifact_id)
