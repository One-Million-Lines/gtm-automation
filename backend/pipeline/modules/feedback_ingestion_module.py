"""FeedbackIngestionModule — pipeline wrapper around services.feedback_service.run_ingestion."""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.feedback_service import run_ingestion


class FeedbackIngestionModule(BaseModule):
    name: str = "FeedbackIngestionModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        cfg = ctx.config or {}
        include_replies = bool(cfg.get("include_replies", True))
        include_exports = bool(cfg.get("include_exports", True))
        dry_run = bool(cfg.get("dry_run", ctx.dry_run))

        try:
            result = run_ingestion(
                ctx.repos,
                project_id=ctx.project_id,
                include_replies=include_replies,
                include_exports=include_exports,
                dry_run=dry_run,
            )
        except ValueError as exc:
            return ModuleResult.fail(str(exc))

        apply = result.get("apply") or {}
        total = int(result.get("reply_events", 0)) + int(result.get("export_events", 0))
        return ModuleResult.ok(
            input_count=total,
            output_count=int(apply.get("applied", 0)),
            message=(
                f"reply_events={result.get('reply_events',0)} "
                f"export_events={result.get('export_events',0)} "
                f"applied={apply.get('applied',0)} "
                f"transitions={len(apply.get('transitions') or [])}"
            ),
            data={
                "reply_events": result.get("reply_events", 0),
                "export_events": result.get("export_events", 0),
                "apply": apply,
            },
        )
