"""Contact enrichment endpoints.

Routes:
  POST  /contacts/{id}/enrich            - enrich a single contact
  GET   /contacts/{id}/enrichment        - latest snapshot + history
  POST  /enrichment/contacts/run         - batch enrich
  POST  /enrichment/contacts/import      - upsert + enrich CSV/records
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.contact_enrichment_service import (
    enrich_contact, enrich_contacts_batch,
    import_enriched_contacts, parse_enriched_csv,
)

router = APIRouter(tags=["enrichment"])


def _personas_for_icp(icp_id: int | None) -> list[str] | None:
    if not icp_id:
        return None
    icp = repos.icps.get(int(icp_id))
    if not icp:
        return None
    tp = icp.get("target_personas")
    return tp if isinstance(tp, list) else None


@router.post("/contacts/{contact_id}/enrich")
def enrich_one_contact(contact_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not repos.contacts.get(contact_id):
        raise HTTPException(status_code=404, detail="contact not found")
    res = enrich_contact(
        repos, contact_id=contact_id,
        target_personas=_personas_for_icp(body.get("icp_id")),
        dry_run=bool(body.get("dry_run")),
        source="live",
    )
    if res.get("skipped"):
        err = res.get("error")
        if err == "contact_missing_email":
            raise HTTPException(status_code=400, detail=err)
    return res


@router.get("/contacts/{contact_id}/enrichment")
def get_contact_enrichment(contact_id: int, limit: int = Query(10, ge=1, le=100)) -> dict:
    if not repos.contacts.get(contact_id):
        raise HTTPException(status_code=404, detail="contact not found")
    rows = repos.contact_enrichment.find(
        {"contact_id": contact_id}, order_by="created_at DESC, id DESC", limit=limit,
    )
    return {
        "contact_id": contact_id,
        "latest": rows[0] if rows else None,
        "history": rows,
        "count": len(rows),
    }


@router.post("/enrichment/contacts/run")
def run_contacts_batch(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    company_id = body.get("company_id")
    contact_ids = body.get("contact_ids")
    limit = int(body.get("limit") or 100)
    only_missing = bool(body.get("only_missing", True))
    dry_run = bool(body.get("dry_run"))

    if project_id is None and company_id is None and not contact_ids:
        raise HTTPException(
            status_code=400,
            detail="provide project_id, company_id, or contact_ids",
        )
    if project_id is not None and not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if company_id is not None and not repos.companies.get(int(company_id)):
        raise HTTPException(status_code=404, detail="company not found")
    if contact_ids is not None and not isinstance(contact_ids, list):
        raise HTTPException(status_code=400, detail="contact_ids must be a list")

    return enrich_contacts_batch(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        company_id=int(company_id) if company_id is not None else None,
        contact_ids=[int(x) for x in contact_ids] if contact_ids else None,
        limit=limit,
        only_missing=only_missing,
        target_personas=_personas_for_icp(body.get("icp_id")),
        dry_run=dry_run,
        source="api",
    )


@router.post("/enrichment/contacts/import")
def import_contacts(body: dict[str, Any]) -> dict:
    project_id = body.get("project_id")
    icp_id = body.get("icp_id")
    csv_text = body.get("csv")
    records = body.get("records")
    source_name = (body.get("source_name") or "csv_import").strip()

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    if not icp_id:
        raise HTTPException(status_code=400, detail="icp_id is required")
    if not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if not repos.icps.get(int(icp_id)):
        raise HTTPException(status_code=404, detail="icp not found")

    if csv_text and not records:
        records = parse_enriched_csv(csv_text)
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=400, detail="provide csv (string) or records (list)")

    return import_enriched_contacts(
        repos,
        project_id=int(project_id),
        icp_id=int(icp_id),
        records=records,
        source_name=source_name,
        target_personas=_personas_for_icp(icp_id),
    )
