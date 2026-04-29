"""Reusable misc helpers (lite version of vtutils/misc.py)."""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def get_project_root() -> str:
    """Returns absolute path of backend/ (parent of this vtutils folder)."""
    return str(Path(__file__).parent.parent)


def str2bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "on", "y", "t")
    if isinstance(v, (int, float)):
        return bool(v)
    return False


def now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def make_json_serializable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_serializable(v) for v in obj]
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception:
            return obj.hex()
    return obj


def dict_chain_access(data: Any, *keys: str) -> Any:
    for k in keys:
        if not isinstance(data, dict) or k not in data:
            return None
        data = data[k]
    return data


def to_json(value: Any) -> str | None:
    """Serialize a value to JSON for SQLite TEXT storage."""
    if value is None:
        return None
    return json.dumps(make_json_serializable(value), ensure_ascii=False)


def from_json(value: Any) -> Any:
    """Parse JSON-stored TEXT back to value. Pass-through if not a string."""
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


_DOMAIN_RE = re.compile(r"[^a-z0-9.\-]")


def normalize_domain(value: str | None) -> str | None:
    """Extract and normalize a domain from a URL or raw string. Lowercase, no www, no path."""
    if not value:
        return None
    s = value.strip().lower()
    if "://" not in s:
        s = "http://" + s
    try:
        host = urlparse(s).hostname or ""
    except Exception:
        host = ""
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    host = _DOMAIN_RE.sub("", host)
    return host or None


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    s = value.strip().lower()
    return s if "@" in s else None


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower())
    return s.strip("-")


def resolve_project_file_path(file_path: str | None) -> str | None:
    """Resolve a project-relative path to absolute. Used by GenerativeLLM for GOOGLE_SA."""
    if not file_path:
        return None
    p = Path(file_path)
    if p.is_absolute():
        return str(p)
    return str(Path(get_project_root()) / file_path)
