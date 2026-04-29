"""Contact endpoints — list (project-scoped via lead_candidates), detail, ingest."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.contact_discovery_service import ingest_contact_records

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("")
def list_contacts(
    project_id: int = Query(...),
    company_id: int | None = Query(None),
    role: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> dict:
    if not repos.projects.get(project_id):
        raise HTTPException(status_code=404, detail="project not found")

    sql = (
        "SELECT DISTINCT c.* FROM contacts c "
        "JOIN lead_candidates lc ON lc.contact_id = c.id "
        "WHERE lc.project_id = ? "
    )
    params: list[Any] = [project_id]
    if company_id:
        sql += "AND c.company_id = ? "
        params.append(int(company_id))
    if role:
        sql += "AND c.normalized_role = ? "
        params.append(role)
    sql += "ORDER BY c.id DESC LIMIT ?"
    params.append(int(limit))

    rows = repos.contacts.storage.fetchall(sql, tuple(params))
    decoded = repos.contacts._decode_many(rows)  # noqa: SLF001
    return {"data": decoded}


@router.get("/{contact_id}")
def get_contact(contact_id: int) -> dict:
    contact = repos.contacts.get(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="contact not found")
    sources = repos.contact_sources.find(
        {"contact_id": contact_id}, order_by="discovered_at DESC, id DESC"
    )
    leads = repos.lead_candidates.find(
        {"contact_id": contact_id}, order_by="id DESC"
    )
    return {"contact": contact, "sources": sources, "leads": leads}


@router.post("/ingest")
def ingest_contacts(body: dict[str, Any]) -> dict:
    project_id = body.get("project_id")
    icp_id = body.get("icp_id")
    source_name = (body.get("source_name") or "").strip()
    records = body.get("records")

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    if icp_id is None:
        raise HTTPException(status_code=400, detail="icp_id is required")
    if not source_name:
        raise HTTPException(status_code=400, detail="source_name is required")
    if not isinstance(records, list):
        raise HTTPException(status_code=400, detail="records must be a list")
    if not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    icp = repos.icps.get(int(icp_id))
    if not icp:
        raise HTTPException(status_code=404, detail="icp not found")

    target_personas = icp.get("target_personas") if isinstance(icp.get("target_personas"), list) else None

    summary = ingest_contact_records(
        repos,
        project_id=int(project_id),
        icp_id=int(icp_id),
        source_name=source_name,
        source_type=body.get("source_type") or source_name,
        records=records,
        target_personas=target_personas,
    )
    return summary
