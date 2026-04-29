"""Suppression pipeline module.

Applies the current suppression list to lead_candidates for the active project/icp.
Optionally also imports new suppression entries first via ctx.config['records'].

ctx.config:
    {
        "records": [ {suppression_type, value, reason?, source?}, ... ],   # optional
        "scope": "icp" | "project" | "all"                                  # default "project"
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.suppression_service import apply_suppression_to_leads, ingest_records


class SuppressionModule(BaseModule):
    name = "SuppressionModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        records = cfg.get("records") or []
        scope = (cfg.get("scope") or "project").lower()

        ingest_summary = {"input": 0, "created": 0, "existing": 0, "skipped": 0, "invalid": 0}
        if isinstance(records, list) and records and not ctx.dry_run:
            ingest_summary = ingest_records(ctx.repos, records)

        project_id = int(ctx.project_id) if scope in ("project", "icp") else None
        icp_id = int(ctx.icp_id) if (scope == "icp" and ctx.icp_id) else None

        result = apply_suppression_to_leads(
            ctx.repos,
            project_id=project_id,
            icp_id=icp_id,
            dry_run=ctx.dry_run,
        )

        log.info(
            "suppression_done",
            scanned=result["scanned"],
            suppressed=result["suppressed"],
            by_reason=result["by_reason"],
            ingested=ingest_summary,
        )

        return ModuleResult.ok(
            input_count=result["scanned"],
            output_count=result["suppressed"],
            message=(
                f"suppressed={result['suppressed']} scanned={result['scanned']} "
                f"ingested={ingest_summary.get('created', 0)}"
            ),
            data={
                "scope": scope,
                "ingested": ingest_summary,
                **result,
            },
        )
