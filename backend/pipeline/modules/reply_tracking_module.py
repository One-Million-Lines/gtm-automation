"""ReplyTrackingModule (File 16).

ctx.config:
    {
        "limit":   200,
        "dry_run": False,
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.reply_service import run_reply_poll


class ReplyTrackingModule(BaseModule):
    name = "ReplyTrackingModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        limit = int(cfg.get("limit") or 200)

        result = run_reply_poll(
            ctx.repos,
            project_id=int(ctx.project_id) if ctx.project_id else None,
            limit=limit,
            dry_run=ctx.dry_run,
        )

        log.info(
            "reply_poll_done",
            scanned=result["scanned"],
            ingested=result["ingested"],
            suppressed=result["suppressed"],
            by_intent=result["by_intent"],
        )
        return ModuleResult.ok(
            input_count=result["scanned"],
            output_count=result["ingested"],
            failed_count=result["scanned"] - result["ingested"],
            message=(
                f"ingested={result['ingested']} "
                f"suppressed={result['suppressed']} "
                f"intents={result['by_intent']}"
            ),
            data={
                "scanned": result["scanned"],
                "ingested": result["ingested"],
                "suppressed": result["suppressed"],
                "by_intent": result["by_intent"],
            },
        )
