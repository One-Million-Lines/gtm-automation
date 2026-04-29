"""OutreachGenerationModule (File 13).

ctx.config:
    {
        "lead_ids":     [int, ...],
        "limit":        200,
        "min_tier":     "B",
        "only_missing": True,
        "channel":      "email",
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.outreach_service import run_outreach_batch


class OutreachGenerationModule(BaseModule):
    name = "OutreachGenerationModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        lead_ids = cfg.get("lead_ids") or None
        limit = int(cfg.get("limit") or 200)
        min_tier = str(cfg.get("min_tier") or "B").upper()
        only_missing = bool(cfg.get("only_missing", True))
        channel = str(cfg.get("channel") or "email")

        result = run_outreach_batch(
            ctx.repos,
            project_id=int(ctx.project_id) if ctx.project_id and not lead_ids else None,
            icp_id=int(ctx.icp_id) if ctx.icp_id else None,
            lead_ids=[int(x) for x in lead_ids] if lead_ids else None,
            min_tier=min_tier,
            only_missing=only_missing,
            limit=limit,
            channel=channel,
            dry_run=ctx.dry_run,
        )

        log.info(
            "outreach_generation_done",
            scanned=result["scanned"],
            generated=result["generated"],
            persisted=result["persisted"],
            failed=result["failed"],
            skipped_below_tier=result["skipped_below_tier"],
            skipped_existing=result["skipped_existing"],
            min_tier=result["min_tier"],
        )
        return ModuleResult.ok(
            input_count=result["scanned"],
            output_count=result["generated"],
            failed_count=result["failed"],
            message=(
                f"generated={result['generated']} persisted={result['persisted']} "
                f"skipped_below_tier={result['skipped_below_tier']} "
                f"skipped_existing={result['skipped_existing']} failed={result['failed']}"
            ),
            data={
                "scanned": result["scanned"],
                "generated": result["generated"],
                "persisted": result["persisted"],
                "failed": result["failed"],
                "skipped_below_tier": result["skipped_below_tier"],
                "skipped_existing": result["skipped_existing"],
                "min_tier": result["min_tier"],
            },
        )
