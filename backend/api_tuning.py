"""Scoring weight tuning endpoints (File 21)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.weight_tuner_service import (
    approve_revision, baseline_weights_for_icp, diff_weights, propose_revision,
    reject_revision, revision_summary, rollback_to, run_tuning_for_project,
)

router = APIRouter(tags=["tuning"])


def _ensure_icp(icp_id: int) -> dict:
    icp = repos.icps.get(int(icp_id))
    if not icp:
        raise HTTPException(status_code=404, detail="icp not found")
    return icp


def _ensure_revision(rev_id: int) -> dict:
    rev = repos.scoring_weight_revisions.get(int(rev_id))
    if not rev:
        raise HTTPException(status_code=404, detail="revision not found")
    return rev


# ---------------------------------------------------------------------------
# Read-only endpoints
# ---------------------------------------------------------------------------
@router.get("/icps/{icp_id}/scoring/weights")
def get_icp_weights(icp_id: int) -> dict:
    _ensure_icp(int(icp_id))
    return revision_summary(repos, int(icp_id))


@router.get("/icps/{icp_id}/scoring/revisions")
def list_icp_revisions(
    icp_id: int,
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    _ensure_icp(int(icp_id))
    rows = repos.scoring_weight_revisions.list_for_icp(
        int(icp_id), limit=int(limit),
    )
    return {"count": len(rows), "data": rows}


@router.get("/scoring/revisions/{rev_id}")
def get_revision_detail(rev_id: int) -> dict:
    rev = _ensure_revision(int(rev_id))
    baseline = rev.get("baseline_weights") or baseline_weights_for_icp(repos, int(rev["icp_id"]))
    proposed = rev.get("proposed_weights") or {}
    return {
        "revision": rev,
        "diff": diff_weights(baseline, proposed),
    }


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
@router.post("/icps/{icp_id}/scoring/propose")
def post_propose(icp_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    _ensure_icp(int(icp_id))
    try:
        return propose_revision(
            repos,
            icp_id=int(icp_id),
            project_id=int(project_id),
            notes=body.get("notes"),
            created_by=body.get("created_by") or "manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/scoring/revisions/{rev_id}/approve")
def post_approve(rev_id: int) -> dict:
    _ensure_revision(int(rev_id))
    try:
        return approve_revision(repos, int(rev_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/scoring/revisions/{rev_id}/reject")
def post_reject(rev_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    _ensure_revision(int(rev_id))
    try:
        return reject_revision(repos, int(rev_id), reason=body.get("reason"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/scoring/revisions/{rev_id}/rollback")
def post_rollback(rev_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    _ensure_revision(int(rev_id))
    try:
        return rollback_to(
            repos, int(rev_id),
            created_by=body.get("created_by") or "manual",
            notes=body.get("notes"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/scoring/tuning/run")
def post_run(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    try:
        return run_tuning_for_project(
            repos,
            project_id=int(project_id),
            icp_ids=body.get("icp_ids"),
            auto_promote=bool(body.get("auto_promote", False)),
            confidence_threshold=float(body.get("confidence_threshold", 0.7)),
            notes=body.get("notes"),
            created_by=body.get("created_by") or "manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
