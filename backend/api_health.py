"""Health check endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from api_shared import storage, vtlog, APP_ENV

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict:
    try:
        row = storage.fetchone("SELECT 1 AS ok")
        db_ok = bool(row and row.get("ok") == 1)
    except Exception as e:
        vtlog.error("health_db_fail", exc=str(e))
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "env": APP_ENV}


@router.get("/db")
def health_db() -> dict:
    version = storage.get_one("schema_meta", {"key": "version"})
    return {"db_path": storage.db_path, "schema_version": version["value"] if version else None}
