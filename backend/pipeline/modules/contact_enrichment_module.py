"""ContactEnrichmentModule — validate emails + persist snapshot.

ctx.config:
    {
        "contact_ids": [int, ...],   # optional explicit list
        "company_id": int,           # optional company scope
        "limit": 100,                 # default 100
        "only_missing": True,
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.contact_enrichment_service import enrich_contacts_batch


class ContactEnrichmentModule(BaseModule):
    name = "ContactEnrichmentModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        contact_ids = cfg.get("contact_ids") or None
        company_id = cfg.get("company_id")
        limit = int(cfg.get("limit") or 100)
        only_missing = bool(cfg.get("only_missing", True))

        # Pull target personas from the active ICP if available.
        target_personas: list[str] | None = None
        if ctx.icp_id:
            icp = ctx.repos.icps.get(int(ctx.icp_id))
            if icp and isinstance(icp.get("target_personas"), list):
                target_personas = icp["target_personas"]

        result = enrich_contacts_batch(
            ctx.repos,
            project_id=int(ctx.project_id) if ctx.project_id and not contact_ids and company_id is None else None,
            company_id=int(company_id) if company_id is not None else None,
            contact_ids=contact_ids,
            limit=limit,
            only_missing=only_missing,
            target_personas=target_personas,
            dry_run=ctx.dry_run,
            source="pipeline",
        )

        log.info(
            "contact_enrichment_done",
            scanned=result["scanned"],
            enriched=result["enriched"],
            skipped=result["skipped"],
            failed=result["failed"],
        )

        return ModuleResult.ok(
            input_count=result["scanned"],
            output_count=result["enriched"],
            failed_count=result["failed"],
            message=(
                f"enriched={result['enriched']}/{result['scanned']} "
                f"skipped={result['skipped']} failed={result['failed']}"
            ),
            data={
                "scanned": result["scanned"],
                "enriched": result["enriched"],
                "skipped": result["skipped"],
                "failed": result["failed"],
                "samples": [
                    {k: v for k, v in r.items() if k not in ("snapshot",)}
                    for r in result["results"][:10]
                ],
            },
        )
