"""Reply tracking endpoints (File 16).

Routes:
  POST /replies/ingest          (single payload OR {fake:true,...})
  POST /replies/poll            (run ingestor batch)
  GET  /outreach/{id}/replies
  GET  /replies?project_id=&intent=&limit=
  GET  /replies/{id}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.reply_classifier import REPLY_INTENTS
from services.reply_service import ingest_reply, run_reply_poll

router = APIRouter(tags=["replies"])


def _coerce_intent(value: str | None) -> str | None:
    if not value:
        return None
    s = value.lower().strip()
    if s not in REPLY_INTENTS:
        raise HTTPException(status_code=400, detail=f"unknown intent: {value}")
    return s


@router.post("/replies/ingest")
def ingest_reply_route(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    if not body:
        raise HTTPException(status_code=400, detail="empty payload")
    res = ingest_reply(repos, body, dry_run=bool(body.get("dry_run")))
    if not res.get("ok") and res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.post("/replies/poll")
def poll_replies_route(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    if project_id is not None and not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    return run_reply_poll(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        limit=int(body.get("limit") or 200),
        dry_run=bool(body.get("dry_run")),
    )


@router.get("/outreach/{message_id}/replies")
def get_outreach_replies(
    message_id: int,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    if not repos.outreach_messages.get(message_id):
        raise HTTPException(status_code=404, detail="message not found")
    history = repos.outreach_replies.history_for_message(message_id, limit=limit)
    latest = history[0] if history else None
    return {
        "message_id": int(message_id),
        "count": len(history),
        "latest": latest,
        "history": history,
    }


@router.get("/replies")
def list_replies(
    project_id: int = Query(..., ge=1),
    intent: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    intent_norm = _coerce_intent(intent)

    where = ["lc.project_id = ?"]
    params: list[Any] = [int(project_id)]
    if intent_norm:
        where.append("orep.intent = ?")
        params.append(intent_norm)

    sql = (
        "SELECT orep.id AS id, orep.outreach_message_id, orep.outreach_send_id, "
        "orep.provider, orep.message_id_external, orep.in_reply_to, "
        "orep.from_email, orep.from_name, orep.subject, orep.body, orep.body_html, "
        "orep.intent, orep.confidence, orep.classifier, orep.raw_response, "
        "orep.received_at, orep.created_at, "
        "om.subject AS message_subject, om.status AS message_status, om.lead_id, "
        "lc.priority_tier, lc.final_score, "
        "co.name AS company_name, co.domain AS company_domain, "
        "ct.full_name AS contact_name, ct.email AS contact_email "
        "FROM outreach_replies orep "
        "INNER JOIN outreach_messages om ON om.id = orep.outreach_message_id "
        "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
        "LEFT JOIN companies co ON co.id = lc.company_id "
        "LEFT JOIN contacts ct ON ct.id = lc.contact_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY orep.received_at DESC, orep.id DESC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.outreach_replies.storage.fetchall(sql, tuple(params))
    decoded = repos.outreach_replies._decode_many(rows)
    return {
        "project_id": int(project_id),
        "count": len(decoded),
        "filters": {"intent": intent_norm, "limit": limit},
        "data": decoded,
    }


@router.get("/replies/{reply_id}")
def get_reply(reply_id: int) -> dict:
    reply = repos.outreach_replies.get(int(reply_id))
    if not reply:
        raise HTTPException(status_code=404, detail="reply not found")
    msg = repos.outreach_messages.get(int(reply["outreach_message_id"])) if reply.get("outreach_message_id") else None
    send = repos.outreach_sends.get(int(reply["outreach_send_id"])) if reply.get("outreach_send_id") else None
    lead = (
        repos.lead_candidates.get(int(msg["lead_id"]))
        if msg and msg.get("lead_id") else None
    )
    return {
        "reply": reply,
        "message": msg,
        "send": send,
        "lead": lead,
    }
