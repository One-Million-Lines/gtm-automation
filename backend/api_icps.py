"""ICP CRUD + lifecycle endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.icp_service import ICPService

router = APIRouter(prefix="/icps", tags=["icps"])

_service = ICPService(repos)


def _get_or_404(icp_id: int) -> dict:
    icp = repos.icps.get(icp_id)
    if not icp:
        raise HTTPException(status_code=404, detail="icp not found")
    return icp


@router.get("")
def list_icps(
    project_id: int = Query(...),
    status: str | None = Query(None),
) -> dict:
    return {"data": repos.icps.find_for_project(project_id, status=status)}


@router.post("", status_code=201)
def create_icp(body: dict[str, Any]) -> dict:
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    if not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    try:
        icp_id = _service.create(int(project_id), body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return repos.icps.get(icp_id) or {"id": icp_id}


@router.get("/{icp_id}")
def get_icp(icp_id: int) -> dict:
    return _get_or_404(icp_id)


@router.patch("/{icp_id}")
def update_icp(icp_id: int, body: dict[str, Any]) -> dict:
    _get_or_404(icp_id)
    try:
        _service.update(icp_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return repos.icps.get(icp_id) or {}


@router.post("/{icp_id}/activate")
def activate_icp(icp_id: int) -> dict:
    _get_or_404(icp_id)
    repos.icps.activate(icp_id)
    return repos.icps.get(icp_id) or {}


@router.post("/{icp_id}/archive")
def archive_icp(icp_id: int) -> dict:
    _get_or_404(icp_id)
    repos.icps.archive(icp_id)
    return repos.icps.get(icp_id) or {}


@router.post("/{icp_id}/clone")
def clone_icp(icp_id: int, body: dict[str, Any] | None = None) -> dict:
    src = _get_or_404(icp_id)
    new_name = (body or {}).get("name") or f"{src['name']} (copy)"
    new_id = repos.icps.clone(icp_id, new_name)
    return repos.icps.get(new_id) or {"id": new_id}


@router.get("/{icp_id}/summary")
def icp_summary(icp_id: int) -> dict:
    _get_or_404(icp_id)
    return _service.summary_for_dashboard(icp_id)
