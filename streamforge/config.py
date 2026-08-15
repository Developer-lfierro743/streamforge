"""StreamForge configuration — read secrets from env or a git-ignored file.

The real ``config.toml`` is git-ignored so your TMDB key is never committed.
A committed ``config.example.toml`` shows the expected shape.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_TMDB_KEY = "STREAMFORGE_TMDB_KEY"


def _load_toml(path: Path) -> dict:
    try:
        import tomllib

        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def tmdb_api_key(explicit: str = "") -> str:
    """Resolve the TMDB key: explicit arg > env var > config.toml."""
    if explicit:
        return explicit
    env = os.environ.get(ENV_TMDB_KEY, "").strip()
    if env:
        return env
    cfg = Path("config.toml")
    if cfg.exists():
        return _load_toml(cfg).get("tmdb", {}).get("api_key", "").strip()
    return ""


def has_tmdb_key(explicit: str = "") -> bool:
    return bool(tmdb_api_key(explicit))


def load_config(path: str = "config.toml") -> dict:
    """Parse ``config.toml`` (or any TOML file) into a dict; empty if missing."""
    from pathlib import Path

    p = Path(path)
    if p.exists():
        return _load_toml(p)
    return {}


def load_sources(path: str = "config.toml") -> list:
    """Read the ``[sources]`` table from ``config.toml`` as ``Source`` objects."""
    from .aggregate import load_sources as _build

    return _build(load_config(path))
