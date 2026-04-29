"""Suppression endpoints — list / add / delete / bulk import / apply to leads."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.suppression_service import (
    VALID_TYPES, apply_suppression_to_leads, ingest_records, normalize_record,
)

router = APIRouter(prefix="/suppression", tags=["suppression"])


@router.get("")
def list_suppression(
    suppression_type: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict:
    if suppression_type and suppression_type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid suppression_type; allowed: {sorted(VALID_TYPES)}",
        )
    rows = repos.suppression.list_filtered(
        suppression_type=suppression_type, q=q, limit=limit, offset=offset,
    )
    return {
        "data": rows,
        "total": repos.suppression.count(
            {"suppression_type": suppression_type} if suppression_type else None
        ),
        "stats": repos.suppression.stats_by_type(),
    }


@router.get("/types")
def list_types() -> dict:
    return {"types": sorted(VALID_TYPES)}


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    row = repos.suppression.get(entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="suppression entry not found")
    return row


@router.post("")
def add_entry(body: dict[str, Any]) -> dict:
    norm = normalize_record(body)
    if not norm:
        raise HTTPException(
            status_code=400,
            detail="invalid suppression record; need valid suppression_type and value",
        )
    sid, action = repos.suppression.add(
        norm["suppression_type"], norm["value"],
        reason=norm.get("reason"), source=norm.get("source"),
    )
    row = repos.suppression.get(sid)
    return {"id": sid, "action": action, "entry": row}


@router.post("/import")
def bulk_import(body: dict[str, Any]) -> dict:
    records = body.get("records")
    if not isinstance(records, list):
        raise HTTPException(status_code=400, detail="records must be a list")
    return ingest_records(repos, records)


@router.delete("/{entry_id}")
def delete_entry(entry_id: int) -> dict:
    if not repos.suppression.get(entry_id):
        raise HTTPException(status_code=404, detail="suppression entry not found")
    repos.suppression.delete(entry_id)
    return {"deleted": entry_id}


@router.post("/apply")
def apply_to_leads(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    icp_id = body.get("icp_id")
    dry_run = bool(body.get("dry_run"))

    if project_id is not None and not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if icp_id is not None and not repos.icps.get(int(icp_id)):
        raise HTTPException(status_code=404, detail="icp not found")

    return apply_suppression_to_leads(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        icp_id=int(icp_id) if icp_id is not None else None,
        dry_run=dry_run,
    )
