"""CompanyEnrichmentModule — fetch homepage + extract meta/tech + persist snapshot.

ctx.config:
    {
        "company_ids": [int, ...],   # optional explicit list
        "limit": 50,                  # default 50
        "only_missing": True          # skip companies that already have an enrichment row
    }
Scope: project_id (from ctx) is used when company_ids is not provided.
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.enrichment_service import enrich_companies_batch


class CompanyEnrichmentModule(BaseModule):
    name = "CompanyEnrichmentModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        company_ids = cfg.get("company_ids") or None
        limit = int(cfg.get("limit") or 50)
        only_missing = bool(cfg.get("only_missing", True))

        result = enrich_companies_batch(
            ctx.repos,
            project_id=int(ctx.project_id) if ctx.project_id and not company_ids else None,
            company_ids=company_ids,
            limit=limit,
            only_missing=only_missing,
            dry_run=ctx.dry_run,
        )

        log.info(
            "company_enrichment_done",
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
                # Trim heavy raw_data for run logs
                "samples": [
                    {k: v for k, v in r.items() if k not in ("snapshot",)}
                    for r in result["results"][:10]
                ],
            },
        )
