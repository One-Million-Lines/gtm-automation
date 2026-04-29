"""Pipeline run endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from api_shared import pipeline_runner, repos

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class RunCreate(BaseModel):
    project_id: int
    icp_id: Optional[int] = None
    run_type: str
    config: Optional[dict] = None
    dry_run: bool = False


@router.post("/runs")
def create_run(body: RunCreate) -> dict:
    if not repos.projects.get(body.project_id):
        raise HTTPException(status_code=404, detail="project not found")
    if body.icp_id is not None and not repos.icps.get(body.icp_id):
        raise HTTPException(status_code=404, detail="icp not found")
    try:
        run_id = pipeline_runner.run_now(
            project_id=body.project_id,
            icp_id=body.icp_id,
            run_type=body.run_type,
            config=body.config,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"pipeline_run_id": run_id}


@router.get("/run-types")
def list_run_types() -> dict:
    return {"run_types": pipeline_runner.registry.known_run_types()}


@router.get("/runs")
def list_runs(project_id: int = Query(...), limit: int = Query(50, ge=1, le=500)) -> dict:
    return {"data": pipeline_runner.list_recent_runs(project_id, limit=limit)}


@router.get("/runs/{run_id}")
def get_run(run_id: int) -> dict:
    detail = pipeline_runner.get_run_detail(run_id)
    if not detail:
        raise HTTPException(status_code=404, detail="run not found")
    return detail
