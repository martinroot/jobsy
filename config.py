"""Jobsy configuration."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("JOBSTY_DATA_DIR", "/var/lib/jobsy/data"))
ORDERS_DIR = DATA_DIR / "orders"
WORKSPACE_DIR = DATA_DIR / "workspace"
LOGS_DIR = DATA_DIR / "logs"

DAGI_BASE_URL = os.getenv("DAGI_BASE_URL", "http://127.0.0.1:8791")
DAGI_WEB_TOKEN = os.getenv("DAGI_WEB_TOKEN", "")

HOST = os.getenv("JOBSTY_HOST", "0.0.0.0")
PORT = int(os.getenv("JOBSTY_PORT", "8000"))
DEBUG = os.getenv("JOBSTY_DEBUG", "0") == "1"

SECRET_KEY = os.getenv("JOBSTY_SECRET_KEY", "dev-secret-change-me")

for d in (DATA_DIR, ORDERS_DIR, WORKSPACE_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)
