"""Signal extraction endpoints.

Routes:
  POST /companies/{id}/signals/extract
  POST /contacts/{id}/signals/extract
  POST /signals/run                         - batch
  GET  /companies/{id}/signals?type=&limit=
  GET  /contacts/{id}/signals?limit=
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.signal_extraction_service import (
    extract_company_signals_for, extract_contact_signals_for, run_signals_batch,
)
from services.signal_provider import SIGNAL_TYPES

router = APIRouter(tags=["signals"])


def _coerce_signal_types(raw: Any) -> list[str] | None:
    if not raw:
        return None
    if isinstance(raw, str):
        items = [s.strip() for s in raw.split(",") if s.strip()]
    elif isinstance(raw, list):
        items = [str(s).strip() for s in raw if str(s).strip()]
    else:
        return None
    bad = [s for s in items if s not in SIGNAL_TYPES]
    if bad:
        raise HTTPException(status_code=400, detail=f"unknown signal_type(s): {bad}")
    return items or None


@router.post("/companies/{company_id}/signals/extract")
def extract_company_signals_route(company_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not repos.companies.get(company_id):
        raise HTTPException(status_code=404, detail="company not found")
    return extract_company_signals_for(
        repos, company_id,
        icp_id=body.get("icp_id"),
        signal_types=_coerce_signal_types(body.get("signal_types")),
        only_missing=bool(body.get("only_missing")),
        dry_run=bool(body.get("dry_run")),
        detected_by="live",
    )


@router.post("/contacts/{contact_id}/signals/extract")
def extract_contact_signals_route(contact_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not repos.contacts.get(contact_id):
        raise HTTPException(status_code=404, detail="contact not found")
    return extract_contact_signals_for(
        repos, contact_id,
        icp_id=body.get("icp_id"),
        signal_types=_coerce_signal_types(body.get("signal_types")),
        only_missing=bool(body.get("only_missing")),
        dry_run=bool(body.get("dry_run")),
        detected_by="live",
    )


@router.post("/signals/run")
def run_signals_route(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    company_id = body.get("company_id")
    company_ids = body.get("company_ids")
    contact_ids = body.get("contact_ids")
    icp_id = body.get("icp_id")
    limit = int(body.get("limit") or 100)
    only_missing = bool(body.get("only_missing", True))
    dry_run = bool(body.get("dry_run"))
    signal_types = _coerce_signal_types(body.get("signal_types"))

    if (project_id is None and company_id is None
            and not company_ids and not contact_ids):
        raise HTTPException(
            status_code=400,
            detail="provide project_id, company_id, company_ids, or contact_ids",
        )
    if project_id is not None and not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if company_id is not None and not repos.companies.get(int(company_id)):
        raise HTTPException(status_code=404, detail="company not found")
    if company_ids is not None and not isinstance(company_ids, list):
        raise HTTPException(status_code=400, detail="company_ids must be a list")
    if contact_ids is not None and not isinstance(contact_ids, list):
        raise HTTPException(status_code=400, detail="contact_ids must be a list")

    return run_signals_batch(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        company_id=int(company_id) if company_id is not None else None,
        company_ids=[int(x) for x in company_ids] if company_ids else None,
        contact_ids=[int(x) for x in contact_ids] if contact_ids else None,
        signal_types=signal_types,
        icp_id=int(icp_id) if icp_id else None,
        limit=limit,
        only_missing=only_missing,
        dry_run=dry_run,
        detected_by="api",
    )


@router.get("/companies/{company_id}/signals")
def list_company_signals(
    company_id: int,
    type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    if not repos.companies.get(company_id):
        raise HTTPException(status_code=404, detail="company not found")
    q: dict[str, Any] = {"company_id": company_id}
    if type:
        if type not in SIGNAL_TYPES:
            raise HTTPException(status_code=400, detail=f"unknown signal_type: {type}")
        q["signal_type"] = type
    rows = repos.signals.find(q, order_by="created_at DESC, id DESC", limit=limit)
    return {"company_id": company_id, "count": len(rows), "data": rows}


@router.get("/contacts/{contact_id}/signals")
def list_contact_signals(
    contact_id: int,
    type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    if not repos.contacts.get(contact_id):
        raise HTTPException(status_code=404, detail="contact not found")
    q: dict[str, Any] = {"contact_id": contact_id}
    if type:
        if type not in SIGNAL_TYPES:
            raise HTTPException(status_code=400, detail=f"unknown signal_type: {type}")
        q["signal_type"] = type
    rows = repos.signals.find(q, order_by="created_at DESC, id DESC", limit=limit)
    return {"contact_id": contact_id, "count": len(rows), "data": rows}
