"""Quality control endpoints (File 14).

Routes:
  POST /outreach/{id}/quality-check
  POST /quality/run
  GET  /outreach/{id}/quality
  GET  /quality?project_id=&min_score=&passed=&limit=
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.outreach_generator import OUTREACH_STATUSES
from services.quality_service import (
    quality_check_for_message, run_quality_batch,
)

router = APIRouter(tags=["quality"])


def _coerce_only_status(value: Any) -> tuple[str, ...]:
    if value is None:
        return ("draft",)
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="only_status must be a list")
    out: list[str] = []
    for s in value:
        s_norm = str(s).lower().strip()
        if s_norm not in OUTREACH_STATUSES:
            raise HTTPException(status_code=400, detail=f"unknown status: {s}")
        out.append(s_norm)
    return tuple(out) if out else ("draft",)


@router.post("/outreach/{message_id}/quality-check")
def quality_check_route(message_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not repos.outreach_messages.get(message_id):
        raise HTTPException(status_code=404, detail="message not found")
    res = quality_check_for_message(
        repos, message_id, dry_run=bool(body.get("dry_run")),
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "quality check failed")
    return res


@router.post("/quality/run")
def quality_run_route(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    message_ids = body.get("message_ids")
    only_missing = bool(body.get("only_missing", True))
    only_status = _coerce_only_status(body.get("only_status"))
    dry_run = bool(body.get("dry_run"))
    limit = int(body.get("limit") or 200)

    if project_id is None and not message_ids:
        raise HTTPException(
            status_code=400,
            detail="provide project_id or message_ids",
        )
    if project_id is not None and not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if message_ids is not None and not isinstance(message_ids, list):
        raise HTTPException(status_code=400, detail="message_ids must be a list")

    return run_quality_batch(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        message_ids=[int(x) for x in message_ids] if message_ids else None,
        only_missing=only_missing,
        only_status=only_status,
        limit=limit,
        dry_run=dry_run,
    )


@router.get("/outreach/{message_id}/quality")
def get_outreach_quality(
    message_id: int,
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    if not repos.outreach_messages.get(message_id):
        raise HTTPException(status_code=404, detail="message not found")
    history = repos.quality_checks.history_for_message(message_id, limit=limit)
    latest = history[0] if history else None
    return {
        "message_id": int(message_id),
        "count": len(history),
        "latest": latest,
        "history": history,
    }


@router.get("/quality")
def list_quality(
    project_id: int = Query(..., ge=1),
    min_score: float | None = Query(None),
    passed: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")

    where = ["lc.project_id = ?"]
    params: list[Any] = [int(project_id)]
    if min_score is not None:
        where.append("qc.score >= ?")
        params.append(float(min_score))
    if passed is not None:
        where.append("qc.passed = ?")
        params.append(1 if passed else 0)

    sql = (
        "SELECT qc.id AS id, qc.outreach_message_id, qc.checker, qc.score, qc.passed, "
        "qc.rule_results, qc.created_at, "
        "om.subject, om.status AS message_status, om.lead_id, "
        "lc.priority_tier, lc.final_score, "
        "co.name AS company_name, co.domain AS company_domain, "
        "ct.full_name AS contact_name, ct.email AS contact_email "
        "FROM quality_checks qc "
        "INNER JOIN outreach_messages om ON om.id = qc.outreach_message_id "
        "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
        "LEFT JOIN companies co ON co.id = lc.company_id "
        "LEFT JOIN contacts ct ON ct.id = lc.contact_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY qc.created_at DESC, qc.id DESC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.quality_checks.storage.fetchall(sql, tuple(params))
    # Decode rule_results JSON for each row.
    decoded = repos.quality_checks._decode_many(rows)
    return {
        "project_id": int(project_id),
        "count": len(decoded),
        "filters": {"min_score": min_score, "passed": passed, "limit": limit},
        "data": decoded,
    }
