"""Lead scoring & listing endpoints (File 12).

Routes:
  POST /leads/{id}/score
  POST /scoring/run
  GET  /leads?project_id=&min_score=&tier=&limit=
  GET  /leads/{id}/scoring
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.lead_scorer import PRIORITY_TIERS
from services.lead_scoring_service import run_scoring_batch, score_lead_for

router = APIRouter(tags=["leads"])


def _coerce_tier(tier: str | None) -> str | None:
    if not tier:
        return None
    t = tier.upper().strip()
    if t not in PRIORITY_TIERS:
        raise HTTPException(status_code=400, detail=f"unknown tier: {tier}")
    return t


@router.post("/leads/{lead_id}/score")
def score_lead_route(lead_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not repos.lead_candidates.get(lead_id):
        raise HTTPException(status_code=404, detail="lead not found")
    return score_lead_for(
        repos, lead_id,
        dry_run=bool(body.get("dry_run")),
    )


@router.post("/scoring/run")
def run_scoring_route(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    icp_id = body.get("icp_id")
    lead_ids = body.get("lead_ids")
    only_missing = bool(body.get("only_missing", True))
    dry_run = bool(body.get("dry_run"))
    limit = int(body.get("limit") or 500)

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

    return run_scoring_batch(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        icp_id=int(icp_id) if icp_id is not None else None,
        lead_ids=[int(x) for x in lead_ids] if lead_ids else None,
        only_missing=only_missing,
        limit=limit,
        dry_run=dry_run,
    )


@router.get("/leads")
def list_leads(
    project_id: int = Query(..., ge=1),
    min_score: float | None = Query(None, ge=0.0, le=1.0),
    tier: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    tier_norm = _coerce_tier(tier)

    where = ["lc.project_id = ?"]
    params: list[Any] = [int(project_id)]
    if min_score is not None:
        where.append("COALESCE(lc.final_score, 0) >= ?")
        params.append(float(min_score))
    if tier_norm:
        where.append("lc.priority_tier = ?")
        params.append(tier_norm)
    sql = (
        "SELECT lc.id AS id, lc.project_id, lc.icp_id, lc.company_id, lc.contact_id, "
        "lc.lead_status, lc.icp_fit_score, lc.signal_score, lc.final_score, "
        "lc.priority_tier, lc.scored_at, lc.created_at, lc.updated_at, "
        "co.name AS company_name, co.domain AS company_domain, co.industry AS company_industry, "
        "ct.full_name AS contact_name, ct.job_title AS contact_title, ct.email AS contact_email "
        "FROM lead_candidates lc "
        "LEFT JOIN companies co ON co.id = lc.company_id "
        "LEFT JOIN contacts  ct ON ct.id = lc.contact_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY COALESCE(lc.final_score, 0) DESC, lc.id DESC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.lead_candidates.storage.fetchall(sql, tuple(params))
    return {
        "project_id": int(project_id),
        "count": len(rows),
        "filters": {"min_score": min_score, "tier": tier_norm, "limit": limit},
        "data": rows,
    }


@router.get("/leads/{lead_id}/scoring")
def get_lead_scoring(lead_id: int) -> dict:
    lead = repos.lead_candidates.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return {
        "lead_id": lead_id,
        "fit_score": lead.get("icp_fit_score"),
        "intent_score": lead.get("signal_score"),
        "combined_score": lead.get("final_score"),
        "priority_tier": lead.get("priority_tier"),
        "scored_at": lead.get("scored_at"),
        "lead_status": lead.get("lead_status"),
        "scoring_explanation": lead.get("scoring_explanation"),
    }
