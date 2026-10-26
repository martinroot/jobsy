"""Run a jobsy order on a Dagi core agent.

An order is a chat. The bridge keeps one Dagi session per order, sends the
user instruction, waits for the run to finish, copies produced files into the
order workspace, and persists token usage. The agent runs until delivery
(status done) or until it needs more info (status needinfo).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator

from ..core.state import StateStore  # noqa: F401  (kept for type reference)
from bridge.config import (
    base_url,
    headers,
    jobsy_data_dir,
    orders_dir,
    workspace_dir,
    RUN_TIMEOUT,
    STREAM_TIMEOUT,
    DELTA_CHARS,
    DELTA_SECONDS,
)

log = logging.getLogger("jobsy.bridge")

DEFAULT_BASE_URL = "http://127.0.0.1:8791"


def _request(method: str, path: str, payload: dict | None = None,
             timeout: int = 120) -> tuple[int, Any]:
    url = base_url() + path
    data = None
    hdrs = headers()
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"error": raw[:400]}
        return error.code, body
    except Exception as exc:
        return 502, {"error": str(exc)}


def _stream_events(run_id: str, after: int = 0) -> Iterator[dict[str, Any]]:
    """Read the run event stream of the Dagi core.

    Events are replayed by id, so a late-joining stream still receives the
    whole run.
    """
    url = f"{base_url()}/api/runs/{run_id}/events?after={int(after)}"
    request = urllib.request.Request(url, headers=headers())
    try:
        with urllib.request.urlopen(request, timeout=STREAM_TIMEOUT) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    event = json.loads(payload)
                except Exception:
                    continue
                if isinstance(event, dict):
                    yield event
    except Exception:
        return


def _template(slug: str) -> dict | None:
    status, data = _request("GET", "/api/templates")
    if status >= 400:
        return None
    return next((item for item in (data.get("templates") or [])
                 if item.get("name") == slug), None)


def _session_path(order_number: str) -> Path:
    p = orders_dir() / order_number / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_state(order_number: str) -> dict:
    p = _session_path(order_number)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(order_number: str, state: dict) -> None:
    p = _session_path(order_number)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _session_id_for(order_number: str) -> int | None:
    state = _load_state(order_number)
    value = (state.get("runtime_dagi") or {}).get("session_id")
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _save_session(order_number: str, session_id: int) -> None:
    state = _load_state(order_number)
    runtime = dict(state.get("runtime_dagi") or {})
    runtime["session_id"] = session_id
    _save_state(order_number, {**state, "runtime_dagi": runtime})


def _session_workspace(session_id: int) -> str:
    status, snapshot = _request("GET", f"/api/sessions/{session_id}")
    if status >= 400:
        return ""
    return str((snapshot.get("session") or {}).get("workspace") or "")


def _copy_artifacts(order_number: str, session_id: int, workspace: str = "") -> list[str]:
    """Copy files the Dagi run produced into the jobsy order workspace."""
    root = workspace_dir()
    source = root / workspace if workspace else root / "sessions" / str(session_id)
    if not source.is_dir():
        return []
    target = orders_dir() / order_number / "out"
    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for item in sorted(source.rglob("*")):
        if not item.is_file():
            continue
        if item.name in copied:
            continue
        destination = target / item.name
        try:
            shutil.copy2(item, destination)
            copied.append(item.name)
        except OSError:
            continue
    return copied


def _publish(order_number: str, files: list[Path], text: str) -> tuple[list[dict], str]:
    """Register produced files as order artifacts and rewrite links."""
    from bridge.artifacts import register, rewrite_links
    artifacts = register(order_number, files)
    return artifacts, rewrite_links(text, order_number, artifacts)


def _usage_log_entry(usage: dict, provider_calls: list[dict], run_id: str,
                     run_info: dict | None = None) -> dict | None:
    """Normalize Dagi usage into the jobsy order meter log entry."""
    try:
        input_tokens = max(0, int(usage.get("input_tokens") or 0))
        output_tokens = max(0, int(usage.get("output_tokens") or 0))
    except (TypeError, ValueError):
        input_tokens = output_tokens = 0
    model = next((str(row.get("model") or "").strip() for row in provider_calls
                  if isinstance(row, dict) and row.get("model")), "")
    cost = usage.get("cost_usd")
    if not (input_tokens or output_tokens or cost is not None):
        return None
    row = {"type": "step", "model": model, "tok_in": input_tokens,
           "tok_out": output_tokens, "status": "done", "backend": "dagi",
           "run_id": str(run_id)}
    if cost is not None:
        row["cost_usd"] = str(cost)
        row["cost_basis"] = "model-rate-estimate"
    for key in ("cache_read_tokens", "cached_tokens", "cache_write_tokens"):
        if usage.get(key) is not None:
            try:
                row[key] = max(0, int(usage.get(key) or 0))
            except (TypeError, ValueError):
                pass
    info = run_info if isinstance(run_info, dict) else {}
    started_at = info.get("started_at")
    finished_at = info.get("finished_at")
    if started_at:
        row["started_at"] = str(started_at)
    if finished_at:
        row["finished_at"] = str(finished_at)
    try:
        duration = float(info.get("duration_seconds")) \
            if info.get("duration_seconds") is not None else None
        if duration is None and started_at and finished_at:
            from datetime import datetime, timezone
            start_dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            finish_dt = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if finish_dt.tzinfo is None:
                finish_dt = finish_dt.replace(tzinfo=timezone.utc)
            duration = (finish_dt - start_dt).total_seconds()
        if duration is not None and duration >= 0:
            row["duration_seconds"] = round(duration, 3)
    except (TypeError, ValueError, OverflowError):
        pass
    return row


def _append_usage_log(order_number: str, run_id: str, usage: dict,
                      provider_calls: list[dict],
                      run_info: dict | None = None) -> None:
    row = _usage_log_entry(usage, provider_calls, run_id, run_info)
    if row is None:
        return
    log_path = orders_dir() / order_number / "log.jsonl"
    if log_path.exists():
        try:
            for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]:
                item = json.loads(line)
                if item.get("backend") == "dagi" and item.get("run_id") == str(run_id):
                    return
        except Exception:
            pass
    row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _looks_like_question(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if stripped.rstrip().endswith(("?", "？")):
        return True
    lowered = stripped.lower()
    return any(lowered.startswith(p) for p in (
        "уточните", "нужны", "какой ", "какая ", "какие ", "кто ", "пришлите",
        "чтобы продолжить", "чтобы собрать", "не хватает", "уточнить",
    ))


class _DeltaPump:
    """Batch text deltas from the run into order chat events."""

    SANDBOX_LINK = re.compile(r"\(sandbox[^)]*\)")
    OPEN_LINK = re.compile(r"\(sandbox[^)]*$")

    def __init__(self, order_number: str, session_id: int = 0, workspace: str = ""):
        self.order_number = order_number
        self.session_id = session_id
        self.workspace = workspace
        self.buffer: list[str] = []
        self.last_flush = time.time()
        self.published: dict[str, str] = {}
        self.artifacts: list[dict[str, Any]] = []
        self.pending: str = ""

    def add(self, text: str) -> None:
        if not text:
            return
        self.pending += text
        self.maybe_flush()

    def maybe_flush(self, force: bool = False) -> None:
        text = self.pending
        if not text:
            return
        if not force:
            match = self.OPEN_LINK.search(text)
            if match:
                head = text[:match.start()]
                self.pending = text[match.start():]
                if head:
                    self._emit(head)
                return
            if len(text) < DELTA_CHARS and (time.time() - self.last_flush) < DELTA_SECONDS:
                return
        self.pending = ""
        self._emit(text)

    def _emit(self, text: str) -> None:
        if not text:
            return
        self.last_flush = time.time()
        try:
            from bridge.events import emit
            emit(self.order_number, "runtime.text", "",
                 {"text": self._rewrite(text)}, visibility="public", source="dagi")
        except Exception:
            pass

    def _rewrite(self, text: str) -> str:
        if "sandbox" not in text:
            return text
        return self.SANDBOX_LINK.sub("", text)

    def flush(self) -> None:
        self.maybe_flush(force=True)


def run(order_number: str, instruction: str | None = None,
        continuation: bool = False) -> dict:
    """Execute the order on a Dagi agent and return the order state."""
    state = _load_state(order_number)
    order = state.get("order") or {}
    slug = str(order.get("slug") or "")
    if not slug:
        raise RuntimeError("order has no agent slug")

    template = _template(slug)
    if template is None:
        raise RuntimeError(f"no Dagi template for agent {slug}")

    session_id = _session_id_for(order_number)
    if session_id is None:
        status, clone = _request("POST",
                                 f"/api/templates/{template['id']}/clone", {})
        if status >= 400:
            raise RuntimeError(f"clone failed: {clone.get('error')}")
        clone = clone.get("clone") or clone
        session_id = int(clone.get("session_id") or 0)
        if not session_id:
            raise RuntimeError("clone returned no session")
        _save_session(order_number, session_id)

    text = str(instruction or order.get("description")
               or order.get("title") or "").strip()
    if not text:
        text = str(template.get("task") or "")

    state = _load_state(order_number)
    run_started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    runtime_meta = dict(state.get("runtime_dagi") or {})
    runtime_meta["current_started_at"] = run_started_at
    _save_state(order_number, {**state, "status": "running",
                               "progress": 10, "runtime_dagi": runtime_meta})

    try:
        from bridge.events import emit
        emit(order_number, "runtime.started", "Агент начал работу",
             {"runtime": "dagi", "session_id": session_id},
             visibility="public", source="dagi")
    except Exception:
        pass

    status, started = _request("POST",
                               f"/api/sessions/{session_id}/runs",
                               {"message": text})
    if status >= 400:
        message = f"Dagi run failed: {started.get('error')}"
        failed_state = _load_state(order_number)
        failed_runtime = dict(failed_state.get("runtime_dagi") or {})
        failed_runtime["current_started_at"] = ""
        _save_state(order_number, {**failed_state, "status": "failed",
                                   "error": message,
                                   "runtime_dagi": failed_runtime})
        return _load_state(order_number)

    run_id = (started.get("run") or started).get("run_id")
    deadline = time.time() + RUN_TIMEOUT
    final = ""
    run_status = "running"
    usage: dict = {}
    pump = _DeltaPump(order_number, session_id, _session_workspace(session_id))

    for event in _stream_events(run_id):
        kind = str(event.get("kind") or "")
        if kind == "text":
            delta = str(event.get("text") or "")
            if delta:
                final += delta
                pump.add(delta)
        elif kind == "tool_call":
            tool = str(event.get("tool_name") or "")
            if tool:
                try:
                    from bridge.events import emit
                    emit(order_number, "runtime.tool", tool,
                         {"tool": tool, "runtime": "dagi"},
                         visibility="public", source="dagi")
                except Exception:
                    pass
        elif kind == "error":
            try:
                from bridge.events import emit
                emit(order_number, "job.failed", "Агент столкнулся с ошибкой",
                     {"error": str(event.get("error") or event.get("text") or "")},
                     visibility="public", source="dagi")
            except Exception:
                pass
        elif kind == "done":
            run_status = str(event.get("status") or "completed")
            break
        if time.time() > deadline:
            run_status = "timeout"
            break
    pump.flush()

    if not final or run_status == "timeout":
        status, snapshot = _request("GET", f"/api/sessions/{session_id}")
        if status < 400:
            answers = [item for item in (snapshot.get("messages") or [])
                       if item.get("role") == "assistant"]
            if answers:
                final = str(answers[-1].get("content") or "") or final
            runs = snapshot.get("runs") or []
            row = next((item for item in runs if item.get("run_id") == run_id),
                       runs[-1] if runs else {})
            if row:
                run_status = str(row.get("status") or run_status)

    status, detail = _request("GET", f"/api/runs/{run_id}")
    if status < 400:
        usage = detail.get("usage") or {}
        provider_calls = detail.get("provider_calls") or []
        try:
            _append_usage_log(order_number, run_id, usage, provider_calls,
                              detail.get("run") or {})
        except Exception:
            log.exception("could not persist Dagi token usage for %s", order_number)

    workspace = ""
    status, snapshot = _request("GET", f"/api/sessions/{session_id}")
    if status < 400:
        workspace = str((snapshot.get("session") or {}).get("workspace") or "")

    artifacts = _copy_artifacts(order_number, session_id, workspace)
    produced = [orders_dir() / order_number / "out" / name for name in artifacts]
    artifact_rows, final = _publish(order_number, produced, final)
    pump.flush()

    asks = not artifacts and _looks_like_question(final)
    if asks:
        text = final.strip()
        _save_state(order_number, {
            **_load_state(order_number),
            "status": "needinfo",
            "progress": 40,
            "clarify_question": text,
            "final": "",
            "runtime_dagi": {
                **_session_block(order_number),
                "current_started_at": "",
                "session_id": session_id,
                "run_id": run_id,
                "artifacts": artifacts,
                "artifact_ids": [row.get("artifact_id") for row in artifact_rows],
                "cost_usd": usage.get("cost_usd"),
            },
        })
        try:
            from bridge.events import emit
            emit(order_number, "runtime.waiting", text, {"runtime": "dagi"},
                 visibility="public", source="dagi")
        except Exception:
            pass
    elif run_status == "completed" and final.strip():
        _save_state(order_number, {
            **_load_state(order_number),
            "status": "done",
            "progress": 100,
            "final": final,
            "runtime_dagi": {
                **_session_block(order_number),
                "current_started_at": "",
                "session_id": session_id,
                "run_id": run_id,
                "artifacts": artifacts,
                "artifact_ids": [row.get("artifact_id") for row in artifact_rows],
                "cost_usd": usage.get("cost_usd"),
            },
        })
        try:
            from bridge.events import emit
            emit(order_number, "job.completed", "Готово",
                 {"runtime": "dagi", "artifacts": artifacts},
                 visibility="public", source="dagi")
        except Exception:
            pass
    else:
        message = final.strip() or "Dagi run did not finish"
        _save_state(order_number, {
            **_load_state(order_number),
            "status": "blocked" if run_status != "failed" else "failed",
            "error": message if run_status == "failed" else "",
            "runtime_dagi": {
                **_session_block(order_number),
                "current_started_at": "",
                "session_id": session_id,
                "run_id": run_id,
                "run_status": run_status,
            },
        })
    return _load_state(order_number)


def _session_block(order_number: str) -> dict:
    state = _load_state(order_number)
    return dict(state.get("runtime_dagi") or {})
