"""Outreach experiments / A/B testing endpoints (File 18)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.experiment_service import (
    create_experiment, declare_winner, pause_experiment,
    score_experiment, start_experiment,
)

router = APIRouter(tags=["experiments"])


def _ensure_experiment(experiment_id: int) -> dict:
    exp = repos.outreach_experiments.get(int(experiment_id))
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    return exp


@router.post("/experiments")
def post_experiment(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    name = (body.get("name") or "").strip()
    variants = body.get("variants") or []
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    if not isinstance(variants, list) or not variants:
        raise HTTPException(status_code=400, detail="at least one variant required")
    if not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    try:
        exp = create_experiment(
            repos,
            project_id=int(project_id),
            icp_id=int(body["icp_id"]) if body.get("icp_id") else None,
            name=name,
            variants=variants,
            hypothesis=body.get("hypothesis"),
            allocation=str(body.get("allocation") or "hash"),
            primary_metric=str(body.get("primary_metric") or "positive_reply_rate"),
            min_sample_size=int(body.get("min_sample_size") or 30),
            confidence_level=float(body.get("confidence_level") or 0.95),
            config=body.get("config") or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return exp


@router.get("/experiments")
def list_experiments(
    project_id: int = Query(..., ge=1),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    if not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if status and status not in ("draft", "running", "paused", "completed", "archived"):
        raise HTTPException(status_code=400, detail="invalid status")
    rows = repos.outreach_experiments.list_for_project(
        int(project_id), status=status, limit=int(limit),
    )
    for r in rows:
        r["variant_count"] = repos.outreach_variants.count(
            {"experiment_id": int(r["id"])},
        )
    return {"count": len(rows), "data": rows}


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: int) -> dict:
    exp = _ensure_experiment(experiment_id)
    variants = repos.outreach_variants.list_for_experiment(int(experiment_id))
    assignments_count = repos.lead_variant_assignments.count(
        {"experiment_id": int(experiment_id)},
    )
    try:
        score = score_experiment(repos, int(experiment_id))
    except Exception as e:
        score = {"error": str(e)}
    return {
        "experiment": exp,
        "variants": variants,
        "assignments_count": assignments_count,
        "score": score,
    }


@router.post("/experiments/{experiment_id}/start")
def post_start(experiment_id: int) -> dict:
    _ensure_experiment(experiment_id)
    return start_experiment(repos, int(experiment_id))


@router.post("/experiments/{experiment_id}/pause")
def post_pause(experiment_id: int) -> dict:
    _ensure_experiment(experiment_id)
    return pause_experiment(repos, int(experiment_id))


@router.post("/experiments/{experiment_id}/score")
def post_score(experiment_id: int) -> dict:
    _ensure_experiment(experiment_id)
    return score_experiment(repos, int(experiment_id))


@router.post("/experiments/{experiment_id}/declare")
def post_declare(experiment_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    variant_id = body.get("variant_id")
    if not variant_id:
        raise HTTPException(status_code=400, detail="variant_id required")
    _ensure_experiment(experiment_id)
    try:
        return declare_winner(repos, int(experiment_id), int(variant_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
