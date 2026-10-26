"""Order artifact registration and link rewriting for jobsy."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from bridge.config import orders_dir


def _order_dir(order_number: str) -> Path:
    d = orders_dir() / order_number
    d.mkdir(parents=True, exist_ok=True)
    return d


def _artifacts_path(order_number: str) -> Path:
    return _order_dir(order_number) / "artifacts.json"


def _load_artifacts(order_number: str) -> list[dict]:
    p = _artifacts_path(order_number)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_artifacts(order_number: str, items: list[dict]) -> None:
    p = _artifacts_path(order_number)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def register(order_number: str, files: list[Path]) -> list[dict]:
    """Register produced files as order artifacts."""
    items = _load_artifacts(order_number)
    for f in files:
        if not f.is_file():
            continue
        mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        artifact_id = str(uuid.uuid4())
        entry = {
            "artifact_id": artifact_id,
            "order_number": order_number,
            "filename": f.name,
            "mime": mime,
            "size_bytes": f.stat().st_size,
            "path": str(f),
            "created_at": __import__("time").strftime(
                "%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        }
        items.append(entry)
    _save_artifacts(order_number, items)
    return items


def list_artifacts(order_number: str) -> list[dict]:
    return _load_artifacts(order_number)


def rewrite_links(text: str, order_number: str,
                  artifacts: list[dict]) -> str:
    """Replace sandbox links in the agent answer with public artifact URLs."""
    if not artifacts:
        return text
    by_name = {a["filename"]: a for a in artifacts}
    import re
    pattern = re.compile(r"\(sandbox([^)]*)\)")

    def repl(match):
        inner = match.group(1)
        name = inner.strip("/").split("/")[-1]
        a = by_name.get(name)
        if a:
            return f"(/api/orders/{order_number}/artifacts/{a['artifact_id']})"
        return match.group(0)

    return pattern.sub(repl, text)


def artifact_path(order_number: str, artifact_id: str) -> Path | None:
    for a in _load_artifacts(order_number):
        if a["artifact_id"] == artifact_id:
            return Path(a["path"])
    return None
