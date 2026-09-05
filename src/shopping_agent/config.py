"""Tiny zero-dependency .env loader.

Reads a project-root `.env` into os.environ (without overriding variables that
are already set), so secrets like SEARCHAPI_API_KEY stay out of the code and
out of git (.env is git-ignored). No python-dotenv dependency.
"""

from __future__ import annotations

import os
from pathlib import Path

_loaded = False


def load_env() -> None:
    """Load KEY=VALUE lines from the project-root .env once. Idempotent."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    env_path = Path(__file__).resolve().parents[2] / ".env"
    try:
        text = env_path.read_text()
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)  # don't override an explicit env var


def searchapi_key() -> str | None:
    """The SearchAPI key if configured (env var or .env), else None."""
    load_env()
    return os.getenv("SEARCHAPI_API_KEY") or None
