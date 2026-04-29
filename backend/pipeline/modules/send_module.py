"""SendModule (File 15).

ctx.config:
    {
        "message_ids":  [int, ...],
        "limit":        200,
        "max_per_day":  50,
        "only_status":  ["approved"],
        "dry_run":      False,
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.send_service import DEFAULT_MAX_PER_DAY, run_send_batch


class SendModule(BaseModule):
    name = "SendModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        message_ids = cfg.get("message_ids") or None
        limit = int(cfg.get("limit") or 200)
        max_per_day = int(cfg.get("max_per_day") or DEFAULT_MAX_PER_DAY)

        result = run_send_batch(
            ctx.repos,
            project_id=int(ctx.project_id) if ctx.project_id and not message_ids else None,
            message_ids=[int(x) for x in message_ids] if message_ids else None,
            max_per_day=max_per_day,
            dry_run=ctx.dry_run,
            limit=limit,
        )

        log.info(
            "send_batch_done",
            scanned=result["scanned"],
            attempted=result["attempted"],
            sent=result["sent"],
            failed=result["failed"],
            skipped_quota=result["skipped_quota"],
            skipped_status=result["skipped_status"],
            sent_today=result["sent_today"],
            max_per_day=result["max_per_day"],
        )
        return ModuleResult.ok(
            input_count=result["scanned"],
            output_count=result["sent"],
            failed_count=result["failed"],
            message=(
                f"sent={result['sent']} failed={result['failed']} "
                f"skipped_quota={result['skipped_quota']} "
                f"skipped_status={result['skipped_status']}"
            ),
            data={
                "scanned": result["scanned"],
                "attempted": result["attempted"],
                "sent": result["sent"],
                "failed": result["failed"],
                "skipped_quota": result["skipped_quota"],
                "skipped_status": result["skipped_status"],
                "max_per_day": result["max_per_day"],
                "sent_today": result["sent_today"],
                "remaining": result["remaining"],
            },
        )
