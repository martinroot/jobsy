"""Jobsy order model: freelance exchange orders assigned to agents."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from bridge.config import orders_dir


def _order_dir(order_number: str) -> Path:
    d = orders_dir() / order_number
    d.mkdir(parents=True, exist_ok=True)
    return d


def _order_path(order_number: str) -> Path:
    return _order_dir(order_number) / "order.json"


def create_order(slug: str, title: str, description: str,
                 customer_id: str | None = None,
                 price_rub: float | None = None,
                 metadata: dict | None = None) -> dict:
    """Create a new order (chat) from a freelance exchange listing."""
    number = f"ORD-{uuid.uuid4().hex[:12]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    order = {
        "number": number,
        "slug": slug,
        "title": title,
        "description": description,
        "customer_id": customer_id,
        "price_rub": price_rub,
        "status": "new",           # new -> assigned -> running -> done/failed
        "agent_id": None,
        "template": slug,
        "metadata": metadata or {},
        "created_at": now,
        "updated_at": now,
        "assigned_at": None,
        "started_at": None,
        "finished_at": None,
        "spent_rub": 0.0,
        "tokens": 0,
    }
    _order_dir(order_number=number).mkdir(parents=True, exist_ok=True)
    _order_path(number).write_text(
        json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
    return order


def get_order(order_number: str) -> dict | None:
    p = _order_path(order_number)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_orders(status: str | None = None, limit: int = 100) -> list[dict]:
    rows: list[dict] = []
    for d in orders_dir().iterdir():
        if not d.is_dir():
            continue
        p = d / "order.json"
        if not p.exists():
            continue
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
            if status is None or o.get("status") == status:
                rows.append(o)
        except Exception:
            continue
    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return rows[:limit]


def assign_agent(order_number: str, agent_id: str,
                 agent_name: str | None = None) -> dict | None:
    """Assign a pre-trained agent to an order (chat)."""
    order = get_order(order_number)
    if not order:
        return None
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    order["agent_id"] = agent_id
    order["agent_name"] = agent_name or agent_id
    order["status"] = "assigned"
    order["assigned_at"] = now
    order["updated_at"] = now
    _order_path(order_number).write_text(
        json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
    return order


def update_status(order_number: str, status: str,
                  error: str | None = None) -> dict | None:
    order = get_order(order_number)
    if not order:
        return None
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    order["status"] = status
    order["updated_at"] = now
    if status == "running" and not order.get("started_at"):
        order["started_at"] = now
    if status in ("done", "failed"):
        order["finished_at"] = now
    if error is not None:
        order["error"] = error
    _order_path(order_number).write_text(
        json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
    return order


def record_usage(order_number: str, tokens: int, spent_rub: float) -> None:
    order = get_order(order_number)
    if not order:
        return
    order["tokens"] = int(order.get("tokens", 0)) + int(tokens)
    order["spent_rub"] = round(float(order.get("spent_rub", 0)) + float(spent_rub), 4)
    order["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _order_path(order_number).write_text(
        json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")


def set_order(order_number: str, order: dict) -> None:
    """Persist a full order state (used by the bridge run loop)."""
    _order_path(order_number).write_text(
        json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
