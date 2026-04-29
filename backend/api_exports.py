"""Lead export endpoints (File 19)."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from api_shared import repos
from services.export_service import (
    ALLOWED_DESTINATIONS, ALLOWED_FORMATS, delivery_summary, redeliver, run_export,
)

router = APIRouter(tags=["exports"])


def _ensure_export(export_id: int) -> dict:
    exp = repos.lead_exports.get(int(export_id))
    if not exp:
        raise HTTPException(status_code=404, detail="export not found")
    return exp


@router.post("/exports")
def post_export(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    name = (body.get("name") or "").strip()
    destination = body.get("destination") or "filesystem"
    format_ = body.get("format") or "csv"
    icp_id = body.get("icp_id")
    filters = body.get("filters")

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    if destination not in ALLOWED_DESTINATIONS:
        raise HTTPException(status_code=400, detail=f"destination must be one of {ALLOWED_DESTINATIONS}")
    if format_ not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"format must be one of {ALLOWED_FORMATS}")
    if not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if icp_id is not None and not repos.icps.get(int(icp_id)):
        raise HTTPException(status_code=404, detail="icp not found")
    if filters is not None and not isinstance(filters, dict):
        raise HTTPException(status_code=400, detail="filters must be an object")

    try:
        result = run_export(
            repos,
            project_id=int(project_id),
            icp_id=int(icp_id) if icp_id is not None else None,
            name=name,
            destination=destination,
            format=format_,
            filters=filters,
            dry_run=bool(body.get("dry_run", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.get("/exports")
def list_exports(
    project_id: int = Query(..., ge=1),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    rows = repos.lead_exports.list_for_project(project_id, status=status, limit=limit)
    return {"data": rows, "count": len(rows)}


@router.get("/exports/{export_id}")
def get_export(export_id: int) -> dict:
    exp = _ensure_export(export_id)
    item_count = repos.lead_export_items.count_for_export(int(export_id))
    summary = delivery_summary(repos, int(export_id))
    return {"export": exp, "item_count": item_count, "summary": summary}


@router.get("/exports/{export_id}/items")
def list_export_items(
    export_id: int,
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    _ensure_export(export_id)
    items = repos.lead_export_items.list_for_export(int(export_id), limit=limit)
    return {"data": items, "count": len(items)}


@router.get("/exports/{export_id}/download")
def download_export(export_id: int):
    exp = _ensure_export(export_id)
    path = exp.get("artifact_path")
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="artifact not available")
    fmt = exp.get("format") or "csv"
    media = "text/csv" if fmt == "csv" else "application/json"
    filename = f"export-{exp['id']}.{fmt}"
    return FileResponse(path, media_type=media, filename=filename)


@router.post("/exports/{export_id}/redeliver")
def post_redeliver(export_id: int) -> dict:
    _ensure_export(export_id)
    try:
        return redeliver(repos, int(export_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
