"""ExportModule — pipeline wrapper around services.export_service.run_export."""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.export_service import run_export


class ExportModule(BaseModule):
    name: str = "ExportModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        cfg = ctx.config or {}
        name = cfg.get("name") or f"pipeline-export-{ctx.pipeline_run_id}"
        destination = cfg.get("destination", "filesystem")
        format_ = cfg.get("format", "csv")
        filters = cfg.get("filters")
        dry_run = bool(cfg.get("dry_run", ctx.dry_run))

        try:
            result = run_export(
                ctx.repos,
                project_id=ctx.project_id,
                icp_id=ctx.icp_id,
                name=name,
                destination=destination,
                format=format_,
                filters=filters,
                dry_run=dry_run,
            )
        except ValueError as exc:
            return ModuleResult.fail(str(exc))

        delivery = result.get("delivery") or {}
        export = result.get("export") or {}
        return ModuleResult.ok(
            input_count=result.get("row_count", 0),
            output_count=result.get("row_count", 0),
            message=f"export id={export.get('id')} status={export.get('status')}",
            data={
                "export_id": export.get("id"),
                "status": export.get("status"),
                "row_count": result.get("row_count", 0),
                "artifact_path": result.get("artifact_path"),
                "artifact_size_bytes": result.get("artifact_size_bytes"),
                "delivery": delivery,
            },
        )
