"""Jobsy agent templates (pre-trained agents)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml optional
    yaml = None


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def list_templates() -> list[dict[str, Any]]:
    """List all agent templates (pre-trained agents)."""
    out: list[dict[str, Any]] = []
    d = _templates_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.yaml")):
        data: dict[str, Any] = {}
        if yaml:
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        out.append({
            "id": data.get("slug") or f.stem,
            "name": data.get("title") or f.stem,
            "slug": data.get("slug") or f.stem,
            "title": data.get("title") or f.stem,
            "category": data.get("category", ""),
            "description": data.get("description", ""),
            "price_rub": float(data.get("price_rub") or 0),
            "unit": data.get("unit", "задача"),
            "margin": float(data.get("margin") or 0),
            "system_prompt": data.get("system_prompt", ""),
            "inputs": list(data.get("inputs") or []),
            "optional": list(data.get("optional") or []),
            "tools": list((data.get("tools") or {}).get("allow") or []),
            "skills": list(data.get("skills") or []),
            "source": f.name,
        })
    return out


def get_template(slug: str) -> dict[str, Any] | None:
    for t in list_templates():
        if t["slug"] == slug:
            return t
    return None
