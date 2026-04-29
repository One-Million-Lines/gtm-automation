"""LeadScoringModule (File 12) — score lead_candidates for a project / ICP.

ctx.config:
    {
        "lead_ids":     [int, ...],
        "limit":        500,
        "only_missing": True,
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.lead_scoring_service import run_scoring_batch


class LeadScoringModule(BaseModule):
    name = "LeadScoringModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        lead_ids = cfg.get("lead_ids") or None
        limit = int(cfg.get("limit") or 500)
        only_missing = bool(cfg.get("only_missing", True))

        result = run_scoring_batch(
            ctx.repos,
            project_id=int(ctx.project_id) if ctx.project_id and not lead_ids else None,
            icp_id=int(ctx.icp_id) if ctx.icp_id else None,
            lead_ids=[int(x) for x in lead_ids] if lead_ids else None,
            only_missing=only_missing,
            limit=limit,
            dry_run=ctx.dry_run,
        )

        log.info(
            "lead_scoring_done",
            scanned=result["scanned"],
            scored=result["scored"],
            persisted=result["persisted"],
            failed=result["failed"],
            tier_counts=result["tier_counts"],
        )

        return ModuleResult.ok(
            input_count=result["scanned"],
            output_count=result["scored"],
            failed_count=result["failed"],
            message=(
                f"scored={result['scored']} persisted={result['persisted']} "
                f"failed={result['failed']} tiers={result['tier_counts']}"
            ),
            data={
                "scanned": result["scanned"],
                "scored": result["scored"],
                "persisted": result["persisted"],
                "failed": result["failed"],
                "tier_counts": result["tier_counts"],
            },
        )
