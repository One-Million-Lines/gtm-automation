"""QualityControlModule (File 14).

ctx.config:
    {
        "message_ids":  [int, ...],
        "limit":        200,
        "only_missing": True,
        "only_status":  ["draft"],
        "min_score":    0.6,    # metric only — gate is enforced at approve API
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.quality_service import run_quality_batch


class QualityControlModule(BaseModule):
    name = "QualityControlModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        message_ids = cfg.get("message_ids") or None
        limit = int(cfg.get("limit") or 200)
        only_missing = bool(cfg.get("only_missing", True))
        only_status = tuple(cfg.get("only_status") or ("draft",))
        min_score = float(cfg.get("min_score") or 0.6)

        result = run_quality_batch(
            ctx.repos,
            project_id=int(ctx.project_id) if ctx.project_id and not message_ids else None,
            message_ids=[int(x) for x in message_ids] if message_ids else None,
            only_missing=only_missing,
            only_status=only_status,
            limit=limit,
            dry_run=ctx.dry_run,
        )

        below_min = sum(
            1 for it in result["items"] if float(it.get("score") or 0) < min_score
        )
        log.info(
            "quality_control_done",
            scanned=result["scanned"],
            checked=result["checked"],
            persisted=result["persisted"],
            passed=result["passed_count"],
            failed=result["failed_count"],
            below_min=below_min,
            min_score=min_score,
        )
        return ModuleResult.ok(
            input_count=result["scanned"],
            output_count=result["passed_count"],
            failed_count=result["failed_count"],
            message=(
                f"checked={result['checked']} passed={result['passed_count']} "
                f"failed={result['failed_count']} below_min={below_min}"
            ),
            data={
                "scanned": result["scanned"],
                "checked": result["checked"],
                "persisted": result["persisted"],
                "passed_count": result["passed_count"],
                "failed_count": result["failed_count"],
                "below_min": below_min,
                "min_score": min_score,
            },
        )
