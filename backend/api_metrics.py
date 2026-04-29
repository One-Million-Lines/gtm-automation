"""Engagement metrics + campaign dashboard endpoints (File 17).

Routes:
  GET  /metrics/campaign?project_id=&icp_id=&window_days=&recompute=
  GET  /metrics/series?project_id=&window_days=
  GET  /metrics/funnel?project_id=&icp_id=
  POST /metrics/recompute  body {project_id, icp_id?, window_days?}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.engagement_aggregator import compute_engagement

router = APIRouter(tags=["metrics"])


def _ensure_project(project_id: int) -> None:
    if not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")


@router.get("/metrics/campaign")
def get_campaign_metrics(
    project_id: int = Query(..., ge=1),
    icp_id: int | None = Query(None, ge=1),
    window_days: int = Query(30, ge=1, le=365),
    recompute: bool = Query(False),
) -> dict:
    _ensure_project(project_id)
    return compute_engagement(
        repos,
        int(project_id),
        icp_id=int(icp_id) if icp_id else None,
        window_days=int(window_days),
        use_cache=not recompute,
    )


@router.get("/metrics/series")
def get_metrics_series(
    project_id: int = Query(..., ge=1),
    icp_id: int | None = Query(None, ge=1),
    window_days: int = Query(30, ge=1, le=365),
) -> dict:
    _ensure_project(project_id)
    metrics = compute_engagement(
        repos,
        int(project_id),
        icp_id=int(icp_id) if icp_id else None,
        window_days=int(window_days),
        use_cache=True,
    )
    return {
        "project_id": int(project_id),
        "icp_id": int(icp_id) if icp_id else None,
        "window_days": int(window_days),
        "series": metrics.get("daily_series") or [],
    }


@router.get("/metrics/funnel")
def get_metrics_funnel(
    project_id: int = Query(..., ge=1),
    icp_id: int | None = Query(None, ge=1),
    window_days: int = Query(30, ge=1, le=365),
) -> dict:
    _ensure_project(project_id)
    metrics = compute_engagement(
        repos,
        int(project_id),
        icp_id=int(icp_id) if icp_id else None,
        window_days=int(window_days),
        use_cache=True,
    )
    return {
        "project_id": int(project_id),
        "icp_id": int(icp_id) if icp_id else None,
        "funnel": metrics.get("funnel") or {},
    }


@router.post("/metrics/recompute")
def post_metrics_recompute(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    if project_id is None:
        raise HTTPException(status_code=400, detail="project_id required")
    _ensure_project(int(project_id))
    icp_id = body.get("icp_id")
    window_days = int(body.get("window_days") or 30)
    metrics = compute_engagement(
        repos,
        int(project_id),
        icp_id=int(icp_id) if icp_id else None,
        window_days=window_days,
        use_cache=False,
    )
    return {
        "ok": True,
        "project_id": int(project_id),
        "icp_id": int(icp_id) if icp_id else None,
        "window_days": window_days,
        "computed_at": metrics.get("computed_at"),
        "metrics": metrics,
    }
