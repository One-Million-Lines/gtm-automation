"""Company endpoints — list, detail (with sources), and synchronous ingest."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.company_discovery_service import ingest_records

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
def list_companies(
    project_id: int = Query(...),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    # Companies aren't directly scoped to a project; we filter via lead_candidates.
    rows = repos.icps.storage.fetchall(
        "SELECT DISTINCT c.* FROM companies c "
        "JOIN lead_candidates lc ON lc.company_id = c.id "
        "WHERE lc.project_id = ? "
        + ("AND c.status = ? " if status else "")
        + "ORDER BY c.id DESC LIMIT ?",
        ((project_id, status, limit) if status else (project_id, limit)),
    )
    decoded = repos.companies._decode_many(rows)  # noqa: SLF001
    return {"data": decoded}


@router.get("/{company_id}")
def get_company(company_id: int) -> dict:
    company = repos.companies.get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    sources = repos.company_sources.find(
        {"company_id": company_id}, order_by="discovered_at DESC, id DESC"
    )
    return {"company": company, "sources": sources}


@router.post("/ingest")
def ingest_companies(body: dict[str, Any]) -> dict:
    project_id = body.get("project_id")
    icp_id = body.get("icp_id")
    source_name = (body.get("source_name") or "").strip()
    records = body.get("records")

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    if not source_name:
        raise HTTPException(status_code=400, detail="source_name is required")
    if not isinstance(records, list):
        raise HTTPException(status_code=400, detail="records must be a list")
    if not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if icp_id is not None and not repos.icps.get(int(icp_id)):
        raise HTTPException(status_code=404, detail="icp not found")

    summary = ingest_records(
        repos,
        project_id=int(project_id),
        icp_id=int(icp_id) if icp_id is not None else None,
        source_name=source_name,
        source_type=body.get("source_type") or source_name,
        records=records,
    )
    return summary
