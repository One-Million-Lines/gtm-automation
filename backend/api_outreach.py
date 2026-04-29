"""Outreach generation endpoints (File 13).

Routes:
  POST /leads/{id}/outreach/generate
  POST /outreach/run
  GET  /leads/{id}/outreach
  GET  /outreach?project_id=&status=&min_tier=&limit=
  POST /outreach/{id}/approve
  POST /outreach/{id}/edit
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.outreach_generator import (
    OUTREACH_CHANNELS, OUTREACH_STATUSES, PRIORITY_TIER_ORDER, tier_meets_min,
)
from services.outreach_service import (
    approve_message, edit_message, generate_outreach_for, run_outreach_batch,
)

router = APIRouter(tags=["outreach"])


def _coerce_min_tier(min_tier: str | None) -> str:
    if not min_tier:
        return "B"
    t = min_tier.upper().strip()
    if t not in PRIORITY_TIER_ORDER:
        raise HTTPException(status_code=400, detail=f"unknown min_tier: {min_tier}")
    return t


def _coerce_status(status: str | None) -> str | None:
    if not status:
        return None
    s = status.lower().strip()
    if s not in OUTREACH_STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status: {status}")
    return s


def _coerce_channel(channel: str | None) -> str:
    if not channel:
        return "email"
    c = channel.lower().strip()
    if c not in OUTREACH_CHANNELS:
        raise HTTPException(status_code=400, detail=f"unknown channel: {channel}")
    return c


@router.post("/leads/{lead_id}/outreach/generate")
def generate_outreach_route(lead_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not repos.lead_candidates.get(lead_id):
        raise HTTPException(status_code=404, detail="lead not found")
    channel = _coerce_channel(body.get("channel"))
    return generate_outreach_for(
        repos, lead_id,
        channel=channel,
        dry_run=bool(body.get("dry_run")),
    )


@router.post("/outreach/run")
def run_outreach_route(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    icp_id = body.get("icp_id")
    lead_ids = body.get("lead_ids")
    only_missing = bool(body.get("only_missing", True))
    dry_run = bool(body.get("dry_run"))
    limit = int(body.get("limit") or 200)
    min_tier = _coerce_min_tier(body.get("min_tier"))
    channel = _coerce_channel(body.get("channel"))

    if project_id is None and icp_id is None and not lead_ids:
        raise HTTPException(
            status_code=400,
            detail="provide project_id, icp_id, or lead_ids",
        )
    if project_id is not None and not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if icp_id is not None and not repos.icps.get(int(icp_id)):
        raise HTTPException(status_code=404, detail="icp not found")
    if lead_ids is not None and not isinstance(lead_ids, list):
        raise HTTPException(status_code=400, detail="lead_ids must be a list")

    return run_outreach_batch(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        icp_id=int(icp_id) if icp_id is not None else None,
        lead_ids=[int(x) for x in lead_ids] if lead_ids else None,
        min_tier=min_tier,
        only_missing=only_missing,
        limit=limit,
        channel=channel,
        dry_run=dry_run,
    )


@router.get("/leads/{lead_id}/outreach")
def get_lead_outreach(lead_id: int, limit: int = Query(20, ge=1, le=200)) -> dict:
    if not repos.lead_candidates.get(lead_id):
        raise HTTPException(status_code=404, detail="lead not found")
    history = repos.outreach_messages.history_for_lead(lead_id, limit=limit)
    latest = history[0] if history else None
    return {
        "lead_id": int(lead_id),
        "count": len(history),
        "latest": latest,
        "history": history,
    }


@router.get("/outreach")
def list_outreach(
    project_id: int = Query(..., ge=1),
    status: str | None = Query(None),
    min_tier: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    status_norm = _coerce_status(status)
    min_tier_norm = _coerce_min_tier(min_tier) if min_tier else None

    where = ["lc.project_id = ?"]
    params: list[Any] = [int(project_id)]
    if status_norm:
        where.append("om.status = ?")
        params.append(status_norm)
    if min_tier_norm:
        allowed = [t for t in ("A", "B", "C", "D") if tier_meets_min(t, min_tier_norm)]
        placeholders = ",".join(["?"] * len(allowed))
        where.append(f"lc.priority_tier IN ({placeholders})")
        params.extend(allowed)

    sql = (
        "SELECT om.id AS id, om.lead_id, om.channel, om.subject, om.body, om.body_html, "
        "om.status, om.model, om.prompt_tokens, om.completion_tokens, "
        "om.generated_at, om.approved_at, om.sent_at, "
        "lc.priority_tier, lc.final_score, "
        "co.name AS company_name, co.domain AS company_domain, "
        "ct.full_name AS contact_name, ct.job_title AS contact_title, ct.email AS contact_email "
        "FROM outreach_messages om "
        "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
        "LEFT JOIN companies co ON co.id = lc.company_id "
        "LEFT JOIN contacts ct ON ct.id = lc.contact_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY om.generated_at DESC, om.id DESC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.outreach_messages.storage.fetchall(sql, tuple(params))
    return {
        "project_id": int(project_id),
        "count": len(rows),
        "filters": {"status": status_norm, "min_tier": min_tier_norm, "limit": limit},
        "data": rows,
    }


@router.post("/outreach/{message_id}/approve")
def approve_outreach_route(
    message_id: int,
    body: dict[str, Any] | None = None,
) -> dict:
    body = body or {}
    force = bool(body.get("force"))
    if not repos.outreach_messages.get(message_id):
        raise HTTPException(status_code=404, detail="message not found")
    if not force:
        latest_qc = repos.quality_checks.latest_for_message(message_id)
        if not latest_qc:
            raise HTTPException(status_code=400, detail="quality_check_required")
        if not int(latest_qc.get("passed") or 0):
            raise HTTPException(status_code=400, detail="quality_check_failed")
    res = approve_message(repos, message_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "approve failed")
    res["forced"] = force
    return res


@router.post("/outreach/{message_id}/edit")
def edit_outreach_route(message_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not repos.outreach_messages.get(message_id):
        raise HTTPException(status_code=404, detail="message not found")
    subject = body.get("subject")
    body_text = body.get("body")
    body_html = body.get("body_html")
    if subject is None and body_text is None and body_html is None:
        raise HTTPException(status_code=400, detail="provide subject, body, or body_html")
    res = edit_message(
        repos, message_id, subject=subject, body=body_text, body_html=body_html
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "edit failed")
    return res
