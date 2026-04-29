"""Feedback + lifecycle endpoints (File 20)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.feedback_service import (
    ALLOWED_KINDS, ALLOWED_SOURCES, LIFECYCLE_STAGES,
    apply_unapplied_feedback, feedback_summary, record_feedback, transition_lead,
)

router = APIRouter(tags=["feedback"])


def _ensure_project(project_id: int) -> dict:
    proj = repos.projects.get(int(project_id))
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")
    return proj


def _ensure_lead(lead_id: int) -> dict:
    lead = repos.lead_candidates.get(int(lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


# ---------------------------------------------------------------------------
# Feedback endpoints
# ---------------------------------------------------------------------------
@router.post("/feedback")
def post_feedback(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    kind = body.get("kind")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    if not kind:
        raise HTTPException(status_code=400, detail="kind required")
    if kind not in ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {ALLOWED_KINDS}")
    source = body.get("source") or "human"
    if source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of {ALLOWED_SOURCES}")
    _ensure_project(int(project_id))
    if body.get("lead_id") is not None:
        _ensure_lead(int(body["lead_id"]))

    try:
        result = record_feedback(
            repos,
            project_id=int(project_id),
            kind=kind,
            source=source,
            lead_id=int(body["lead_id"]) if body.get("lead_id") is not None else None,
            icp_id=int(body["icp_id"]) if body.get("icp_id") is not None else None,
            outreach_message_id=(
                int(body["outreach_message_id"])
                if body.get("outreach_message_id") is not None else None
            ),
            variant_id=int(body["variant_id"]) if body.get("variant_id") is not None else None,
            payload=body.get("payload") if isinstance(body.get("payload"), dict) else None,
            weight=float(body.get("weight") or 1.0),
            auto_apply=bool(body.get("auto_apply", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.get("/feedback")
def get_feedback(
    project_id: int = Query(...),
    kind: str | None = Query(None),
    source: str | None = Query(None),
    applied: int | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    _ensure_project(int(project_id))
    if kind and kind not in ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {ALLOWED_KINDS}")
    if source and source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of {ALLOWED_SOURCES}")
    rows = repos.feedback_events.list_for_project(
        int(project_id), kind=kind, source=source, applied=applied, limit=int(limit),
    )
    return {"count": len(rows), "data": rows}


@router.get("/feedback/summary")
def get_feedback_summary(project_id: int = Query(...)) -> dict:
    _ensure_project(int(project_id))
    return feedback_summary(repos, int(project_id))


@router.get("/feedback/{event_id}")
def get_feedback_event(event_id: int) -> dict:
    ev = repos.feedback_events.get(int(event_id))
    if not ev:
        raise HTTPException(status_code=404, detail="feedback event not found")
    return ev


@router.post("/feedback/apply")
def post_feedback_apply(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    _ensure_project(int(project_id))
    return apply_unapplied_feedback(
        repos,
        project_id=int(project_id),
        limit=int(body.get("limit") or 200),
    )


# ---------------------------------------------------------------------------
# Lead lifecycle endpoints
# ---------------------------------------------------------------------------
@router.get("/leads/{lead_id}/lifecycle")
def get_lead_lifecycle(lead_id: int) -> dict:
    lead = _ensure_lead(int(lead_id))
    transitions = repos.lifecycle_transitions.list_for_lead(int(lead_id))
    return {
        "lead": lead,
        "lifecycle_stage": lead.get("lifecycle_stage") or "new",
        "transitions": transitions,
    }


@router.post("/leads/{lead_id}/transition")
def post_lead_transition(lead_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    to_status = body.get("to_status")
    if not to_status:
        raise HTTPException(status_code=400, detail="to_status required")
    if to_status not in LIFECYCLE_STAGES:
        raise HTTPException(status_code=400, detail=f"to_status must be one of {LIFECYCLE_STAGES}")
    _ensure_lead(int(lead_id))
    try:
        return transition_lead(
            repos,
            lead_id=int(lead_id),
            to_status=to_status,
            reason=body.get("reason"),
            source=body.get("source") or "human",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
