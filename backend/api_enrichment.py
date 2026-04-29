"""Company enrichment endpoints.

Routes:
  POST   /companies/{id}/enrich          - enrich a single company (synchronous)
  GET    /companies/{id}/enrichment      - latest snapshot + history
  POST   /enrichment/companies/run       - batch enrich (project-scoped or explicit ids)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_shared import repos
from services.enrichment_service import enrich_companies_batch, enrich_company

router = APIRouter(tags=["enrichment"])


@router.post("/companies/{company_id}/enrich")
def enrich_one(company_id: int, body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    if not repos.companies.get(company_id):
        raise HTTPException(status_code=404, detail="company not found")
    res = enrich_company(repos, company_id=company_id, dry_run=bool(body.get("dry_run")))
    if res.get("skipped"):
        # Map known errors to 4xx
        err = res.get("error")
        if err == "company_missing_domain":
            raise HTTPException(status_code=400, detail=err)
    return res


@router.get("/companies/{company_id}/enrichment")
def get_enrichment(company_id: int, limit: int = Query(10, ge=1, le=100)) -> dict:
    if not repos.companies.get(company_id):
        raise HTTPException(status_code=404, detail="company not found")
    rows = repos.company_enrichment.find(
        {"company_id": company_id}, order_by="created_at DESC, id DESC", limit=limit,
    )
    return {
        "company_id": company_id,
        "latest": rows[0] if rows else None,
        "history": rows,
        "count": len(rows),
    }


@router.post("/enrichment/companies/run")
def run_batch(body: dict[str, Any] | None = None) -> dict:
    body = body or {}
    project_id = body.get("project_id")
    company_ids = body.get("company_ids")
    limit = int(body.get("limit") or 50)
    only_missing = bool(body.get("only_missing", True))
    dry_run = bool(body.get("dry_run"))

    if project_id is None and not company_ids:
        raise HTTPException(status_code=400, detail="provide project_id or company_ids")
    if project_id is not None and not repos.projects.get(int(project_id)):
        raise HTTPException(status_code=404, detail="project not found")
    if company_ids is not None and not isinstance(company_ids, list):
        raise HTTPException(status_code=400, detail="company_ids must be a list")

    return enrich_companies_batch(
        repos,
        project_id=int(project_id) if project_id is not None else None,
        company_ids=[int(x) for x in company_ids] if company_ids else None,
        limit=limit,
        only_missing=only_missing,
        dry_run=dry_run,
    )
