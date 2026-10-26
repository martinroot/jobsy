"""Bridge configuration: Dagi core connection and jobsy paths."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:8791"
RUN_TIMEOUT = 900
STREAM_TIMEOUT = 900
POLL_SECONDS = 1.5
DELTA_CHARS = 48
DELTA_SECONDS = 0.12


def base_url() -> str:
    return os.getenv("DAGI_ADMIN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def service_token() -> str:
    return os.getenv("DAGI_WEB_TOKEN", "").strip()


def headers() -> dict[str, str]:
    h = {"Accept": "application/json"}
    t = service_token()
    if t:
        h["Authorization"] = "Bearer " + t
    return h


def jobsy_data_dir() -> Path:
    return Path(os.getenv("JOBSTY_DATA_DIR", "/var/lib/jobsy/data"))


def orders_dir() -> Path:
    d = jobsy_data_dir() / "orders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def workspace_dir() -> Path:
    d = jobsy_data_dir() / "workspace"
    d.mkdir(parents=True, exist_ok=True)
    return d
