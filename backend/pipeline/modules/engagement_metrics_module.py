"""EngagementMetricsModule (File 17).

ctx.config:
    {
        "window_days": 30,
        "recompute":   True,
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.engagement_aggregator import compute_engagement


class EngagementMetricsModule(BaseModule):
    name = "EngagementMetricsModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        window_days = int(cfg.get("window_days") or 30)
        recompute = bool(cfg.get("recompute", True))

        if not ctx.project_id:
            return ModuleResult.ok(
                input_count=0, output_count=0, failed_count=0,
                message="no project_id, skipped",
                data={"skipped": True},
            )

        metrics = compute_engagement(
            ctx.repos,
            int(ctx.project_id),
            icp_id=int(ctx.icp_id) if ctx.icp_id else None,
            window_days=window_days,
            use_cache=not recompute,
        )

        scanned = int(metrics.get("sent_count") or 0)
        log.info(
            "engagement_metrics_done",
            sent=scanned,
            replied=metrics.get("replied_count"),
            reply_rate=metrics.get("reply_rate"),
            window_days=window_days,
            from_cache=metrics.get("from_cache"),
        )
        return ModuleResult.ok(
            input_count=scanned,
            output_count=1,
            failed_count=0,
            message=(
                f"sent={metrics.get('sent_count')} "
                f"replied={metrics.get('replied_count')} "
                f"reply_rate={metrics.get('reply_rate')}"
            ),
            data={
                "metrics_summary": {
                    "sent_count": metrics.get("sent_count"),
                    "sent_window": metrics.get("sent_window"),
                    "replied_count": metrics.get("replied_count"),
                    "reply_rate": metrics.get("reply_rate"),
                    "positive_reply_rate": metrics.get("positive_reply_rate"),
                    "bounce_rate": metrics.get("bounce_rate"),
                    "unsubscribe_rate": metrics.get("unsubscribe_rate"),
                    "by_intent": metrics.get("by_intent"),
                    "from_cache": metrics.get("from_cache"),
                },
            },
        )
