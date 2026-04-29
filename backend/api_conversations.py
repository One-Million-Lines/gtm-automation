"""Conversation + Decision Traces API — File 23.

Routes:
  GET    /threads                     list threads for project
  POST   /threads                     create thread manually
  GET    /threads/{id}                thread detail with message timeline
  PATCH  /threads/{id}                update status
  POST   /threads/{id}/messages       add manual message
  POST   /threads/{id}/draft-reply    force-draft a reply
  GET    /decision-traces             filter by run_id / lead_id / decision_type
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api_shared import pipeline_runner, repos
from services import conversation_service as svc

router = APIRouter(tags=["conversations"])

VALID_THREAD_STATUSES = {"open", "awaiting_reply", "replied", "closed", "bounced"}
VALID_DECISION_TYPES = {"score", "draft", "quality", "send", "reply", "tuning", "thread"}


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

class ThreadCreate(BaseModel):
    project_id: int
    icp_id: Optional[int] = None
    lead_id: Optional[int] = None
    contact_id: Optional[int] = None
    subject: Optional[str] = None
    status: str = "open"


class ThreadPatch(BaseModel):
    status: Optional[str] = None


class ManualMessageIn(BaseModel):
    direction: str = "out"
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Threads
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/threads")
def list_threads(
    project_id: int = Query(...),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    if status and status not in VALID_THREAD_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_THREAD_STATUSES)}")
    threads = svc.list_threads_for_project(
        repos, project_id, status=status, limit=limit
    )
    return {"count": len(threads), "data": threads}


@router.post("/threads", status_code=201)
def create_thread(body: ThreadCreate) -> dict:
    if body.status not in VALID_THREAD_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_THREAD_STATUSES)}")
    thread_id = repos.lead_threads.create({
        "project_id": body.project_id,
        "icp_id": body.icp_id,
        "lead_id": body.lead_id,
        "contact_id": body.contact_id,
        "subject": body.subject,
        "status": body.status,
        "message_count": 0,
    })
    thread = repos.lead_threads.get(thread_id)
    if thread is None:
        raise HTTPException(500, "Failed to create thread")
    return thread


@router.get("/threads/{thread_id}")
def get_thread(thread_id: int) -> dict:
    detail = svc.get_thread_detail(repos, thread_id)
    if detail is None:
        raise HTTPException(404, f"Thread {thread_id} not found")
    return detail


@router.patch("/threads/{thread_id}")
def patch_thread(thread_id: int, body: ThreadPatch) -> dict:
    if body.status is None:
        thread = repos.lead_threads.get(thread_id)
        if thread is None:
            raise HTTPException(404, f"Thread {thread_id} not found")
        return thread
    if body.status not in VALID_THREAD_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_THREAD_STATUSES)}")
    try:
        return svc.mark_status(repos, thread_id, body.status)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/threads/{thread_id}/messages", status_code=201)
def add_thread_message(thread_id: int, body: ManualMessageIn) -> dict:
    if body.direction not in {"out", "in"}:
        raise HTTPException(400, "direction must be 'out' or 'in'")
    thread = repos.lead_threads.get(thread_id)
    if thread is None:
        raise HTTPException(404, f"Thread {thread_id} not found")
    try:
        msg = svc.add_manual_message(
            repos, thread_id,
            direction=body.direction,
            subject=body.subject,
            body_text=body.body_text,
            body_html=body.body_html,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return msg


@router.post("/threads/{thread_id}/draft-reply", status_code=201)
def force_draft_reply(thread_id: int) -> dict:
    thread = repos.lead_threads.get(thread_id)
    if thread is None:
        raise HTTPException(404, f"Thread {thread_id} not found")

    # Force-run the drafter for this single thread by creating a one-shot run
    run_id = pipeline_runner.run_now(
        project_id=int(thread["project_id"]),
        icp_id=thread.get("icp_id"),
        run_type="reply_drafter",
        config={"thread_id": thread_id, "limit": 1},
        dry_run=False,
    )
    # Return latest thread message after the run
    messages = repos.lead_thread_messages.list_for_thread(thread_id, limit=1)
    latest = messages[-1] if messages else {}
    return {"run_id": run_id, "latest_message": latest}


# ──────────────────────────────────────────────────────────────────────────────
# Reconcile
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/threads/reconcile")
def reconcile_threads(project_id: int = Query(...)) -> dict:
    result = svc.rebuild_threads(repos, project_id=project_id)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Decision Traces
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/decision-traces")
def list_decision_traces(
    run_id: Optional[int] = Query(None),
    lead_id: Optional[int] = Query(None),
    contact_id: Optional[int] = Query(None),
    decision_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    if decision_type and decision_type not in VALID_DECISION_TYPES:
        raise HTTPException(400, f"decision_type must be one of {sorted(VALID_DECISION_TYPES)}")
    traces = repos.decision_traces.query(
        run_id=run_id,
        lead_id=lead_id,
        contact_id=contact_id,
        decision_type=decision_type,
        limit=limit,
    )
    return {"count": len(traces), "data": traces}


@router.get("/decision-traces/{trace_id}")
def get_decision_trace(trace_id: int) -> dict:
    trace = repos.decision_traces.get(trace_id)
    if trace is None:
        raise HTTPException(404, f"Decision trace {trace_id} not found")
    return trace
