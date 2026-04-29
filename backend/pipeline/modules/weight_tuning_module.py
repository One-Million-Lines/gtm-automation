"""WeightTuningModule — pipeline wrapper around weight_tuner_service.run_tuning_for_project."""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.weight_tuner_service import run_tuning_for_project


class WeightTuningModule(BaseModule):
    name: str = "WeightTuningModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        cfg = ctx.config or {}
        icp_ids = cfg.get("icp_ids")
        if icp_ids is None and ctx.icp_id:
            icp_ids = [ctx.icp_id]
        auto_promote = bool(cfg.get("auto_promote", False))
        confidence_threshold = float(cfg.get("confidence_threshold", 0.7))
        notes = cfg.get("notes")
        created_by = cfg.get("created_by") or "pipeline:weight_tuning"

        try:
            result = run_tuning_for_project(
                ctx.repos,
                project_id=ctx.project_id,
                icp_ids=icp_ids,
                auto_promote=auto_promote,
                confidence_threshold=confidence_threshold,
                notes=notes,
                created_by=created_by,
            )
        except ValueError as exc:
            return ModuleResult.fail(str(exc))

        return ModuleResult.ok(
            input_count=int(result.get("proposed_count", 0)),
            output_count=int(result.get("promoted_count", 0)),
            message=(
                f"proposed={result.get('proposed_count',0)} "
                f"promoted={result.get('promoted_count',0)} "
                f"skipped={result.get('skipped_count',0)} "
                f"auto_promote={result.get('auto_promote')}"
            ),
            data=result,
        )
