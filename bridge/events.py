"""Job event emission for jobsy chat.

Events are written to the order's events.jsonl and can be streamed over
WebSocket to the frontend chat.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from bridge.config import orders_dir


def _events_path(order_number: str) -> Path:
    d = orders_dir() / order_number
    d.mkdir(parents=True, exist_ok=True)
    return d / "events.jsonl"


def emit(order_number: str, event_type: str, label: str,
         data: dict[str, Any] | None = None,
         visibility: str = "public", source: str = "jobsy") -> None:
    """Append a job event to the order's event log."""
    event = {
        "id": f"{event_type}-{int(time.time() * 1000)}",
        "event_type": event_type,
        "label": label,
        "data": data or {},
        "visibility": visibility,
        "source": source,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    p = _events_path(order_number)
    with p.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def events(order_number: str, after: int = 0, limit: int = 200) -> list[dict]:
    """Return job events for an order, optionally after a given id index."""
    p = _events_path(order_number)
    if not p.exists():
        return []
    rows = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if after:
        rows = [r for r in rows if str(r.get("id", "")) != str(after)]
    return rows[-limit:]
