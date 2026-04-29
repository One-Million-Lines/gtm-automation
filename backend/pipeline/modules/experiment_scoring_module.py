"""ExperimentScoringModule (File 18).

ctx.config:
    {
        "experiment_id": int|None,   # if None, score all 'running' for project
        "auto_declare":  bool        # default False
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.experiment_service import declare_winner, score_experiment


class ExperimentScoringModule(BaseModule):
    name = "ExperimentScoringModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        exp_id = cfg.get("experiment_id")
        auto_declare = bool(cfg.get("auto_declare", False))

        if exp_id is not None:
            target_ids = [int(exp_id)]
        else:
            if not ctx.project_id:
                return ModuleResult.ok(
                    input_count=0, output_count=0, failed_count=0,
                    message="no project_id and no experiment_id, skipped",
                    data={"skipped": True},
                )
            running = ctx.repos.outreach_experiments.list_for_project(
                int(ctx.project_id), status="running",
            )
            target_ids = [int(r["id"]) for r in running]

        scored: list[dict] = []
        declared: list[int] = []
        failed = 0
        for tid in target_ids:
            try:
                payload = score_experiment(ctx.repos, tid)
                scored.append({
                    "experiment_id": tid,
                    "leader_variant_id": payload.get("leader_variant_id"),
                    "ready_to_declare": payload.get("ready_to_declare"),
                    "by_variant_count": len(payload.get("by_variant") or []),
                })
                if auto_declare and payload.get("ready_to_declare") and payload.get("leader_variant_id"):
                    declare_winner(ctx.repos, tid, int(payload["leader_variant_id"]))
                    declared.append(tid)
            except Exception as e:
                log.error("experiment_scoring_failed", experiment_id=tid, exc=str(e))
                failed += 1

        log.info(
            "experiment_scoring_done",
            scored=len(scored), declared=len(declared), failed=failed,
        )
        return ModuleResult.ok(
            input_count=len(target_ids),
            output_count=len(scored),
            failed_count=failed,
            message=f"scored={len(scored)} declared={len(declared)} failed={failed}",
            data={
                "scored": scored,
                "declared_experiment_ids": declared,
                "auto_declare": auto_declare,
            },
        )
