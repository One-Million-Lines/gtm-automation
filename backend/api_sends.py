"""Send queue endpoints (File 15).

Routes:
  POST /outreach/{message_id}/send
  POST /sends/run
  GET  /outreach/{message_id}/sends
  GET  /sends?project_id=&status=&limit=
  GET  /sends/quota?project_id=&max_per_day=
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.email_sender import SEND_STATUSES
from services.send_service import (
    DEFAULT_MAX_PER_DAY, run_send_batch, send_for_message,
)

router = APIRouter(tags=["sends"])


def _coerce_status(value: str | None) -> str | None:
    if not value:
        return None
    s = value.lower().strip()
    if s not in SEND_STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status: {value}")
    return s


def _project_for_message(message_id: int) -> int | None:
    msg = repos.outreach_messages.get(int(message_id))
    if not msg or not msg.get("lead_id"):
        return None
    lead = repos.lead_candidates.get(int(msg["lead_id"]))
    return int(lead["project_id"]) if lead else None


@router.post("/outreach/{message_id}/send")
def send_outreach_route(message_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    msg = repos.outreach_messages.get(int(message_id))
    if not msg:
        raise HTTPException(status_code=404, detail="message not found")
    if (msg.get("status") or "").lower() != "approved":
        raise HTTPException(status_code=400, detail="message_not_approved")

    max_per_day_raw = body.get("max_per_day")
    max_per_day = int(max_per_day_raw) if max_per_day_raw is not None else DEFAULT_MAX_PER_DAY
    project_id = _project_for_message(message_id)
    if project_id is not None:
        sent_today = repos.outreach_sends.count_sent_today(project_id)
        if sent_today >= max_per_day and not bool(body.get("dry_run")):
            raise HTTPException(status_code=400, detail="daily_quota_exceeded")

    res = send_for_message(
        repos, message_id,
        dry_run=bool(body.get("dry_run")),
        max_per_day=max_per_day,
        enforce_quota=True,
    )
    if not res.get("ok") and res.get("error") in ("message_not_approved", "daily_quota_exceeded"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.post("/sends/run")
def sends_run_route(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    message_ids = body.get("message_ids")
    max_per_day = int(body.get("max_per_day") or DEFAULT_MAX_PER_DAY)
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

    return run_send_batch(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        message_ids=[int(x) for x in message_ids] if message_ids else None,
        max_per_day=max_per_day,
        dry_run=dry_run,
        limit=limit,
    )


@router.get("/outreach/{message_id}/sends")
def get_outreach_sends(
    message_id: int,
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    if not repos.outreach_messages.get(message_id):
        raise HTTPException(status_code=404, detail="message not found")
    history = repos.outreach_sends.history_for_message(message_id, limit=limit)
    latest = history[0] if history else None
    return {
        "message_id": int(message_id),
        "count": len(history),
        "latest": latest,
        "history": history,
    }


@router.get("/sends")
def list_sends(
    project_id: int = Query(..., ge=1),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    status_norm = _coerce_status(status)

    where = ["lc.project_id = ?"]
    params: list[Any] = [int(project_id)]
    if status_norm:
        where.append("os.status = ?")
        params.append(status_norm)

    sql = (
        "SELECT os.id AS id, os.outreach_message_id, os.provider, "
        "os.message_id_external, os.status, os.attempted_at, os.sent_at, "
        "os.error_message, os.raw_response, "
        "om.subject, om.status AS message_status, om.lead_id, "
        "lc.priority_tier, lc.final_score, "
        "co.name AS company_name, co.domain AS company_domain, "
        "ct.full_name AS contact_name, ct.email AS contact_email "
        "FROM outreach_sends os "
        "INNER JOIN outreach_messages om ON om.id = os.outreach_message_id "
        "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
        "LEFT JOIN companies co ON co.id = lc.company_id "
        "LEFT JOIN contacts ct ON ct.id = lc.contact_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY os.attempted_at DESC, os.id DESC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.outreach_sends.storage.fetchall(sql, tuple(params))
    decoded = repos.outreach_sends._decode_many(rows)
    return {
        "project_id": int(project_id),
        "count": len(decoded),
        "filters": {"status": status_norm, "limit": limit},
        "data": decoded,
    }


@router.get("/sends/quota")
def get_sends_quota(
    project_id: int = Query(..., ge=1),
    max_per_day: int = Query(DEFAULT_MAX_PER_DAY, ge=1, le=10000),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    sent_today = repos.outreach_sends.count_sent_today(int(project_id))
    return {
        "project_id": int(project_id),
        "sent_today": int(sent_today),
        "max_per_day": int(max_per_day),
        "remaining": max(0, int(max_per_day) - int(sent_today)),
    }
