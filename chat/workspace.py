"""Order workspace management for jobsy.

Each order has an isolated workspace where the agent reads inputs and
writes deliverables.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from bridge.config import orders_dir, workspace_dir


def order_workspace_root(order_number: str) -> Path:
    root = orders_dir() / order_number
    root.mkdir(parents=True, exist_ok=True)
    return root


def order_inputs_dir(order_number: str) -> Path:
    d = order_workspace_root(order_number) / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def order_outputs_dir(order_number: str) -> Path:
    d = order_workspace_root(order_number) / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stage_input(order_number: str, filename: str, data: bytes) -> Path:
    d = order_inputs_dir(order_number)
    p = d / filename
    p.write_bytes(data)
    return p


def list_inputs(order_number: str) -> list[dict[str, Any]]:
    d = order_inputs_dir(order_number)
    items = []
    for f in sorted(d.iterdir()):
        if f.is_file():
            items.append({"name": f.name, "size": f.stat().st_size})
    return items
