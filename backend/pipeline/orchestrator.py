"""PipelineOrchestrator: runs a list of modules and tracks the run row."""
from __future__ import annotations

from typing import Sequence

from pipeline.context import PipelineContext
from pipeline.module import PipelineModule
from repositories import RepoRegistry


class PipelineOrchestrator:
    def __init__(self, repos: RepoRegistry, vtlog) -> None:
        self.repos = repos
        self.vtlog = vtlog

    def run(
        self,
        *,
        project_id: int,
        icp_id: int | None,
        run_type: str,
        modules: Sequence[PipelineModule],
        config: dict | None = None,
        dry_run: bool = False,
    ) -> int:
        config = config or {}
        stop_on_failure = bool(config.get("stop_on_failure", False))

        run_id = self.repos.pipeline_runs.start(project_id, icp_id, run_type, config)
        self.vtlog.info("pipeline_run_started", run_id=run_id, run_type=run_type, modules=len(modules))

        ctx = PipelineContext(
            project_id=project_id,
            icp_id=icp_id,
            pipeline_run_id=run_id,
            repos=self.repos,
            vtlog=self.vtlog,
            config=config,
            dry_run=dry_run,
        )

        total_processed = 0
        total_created = 0
        total_failed = 0
        any_success = False
        any_failure = False
        last_error: str | None = None

        for module in modules:
            result = module.run(ctx)  # BaseModule.run never raises
            total_processed += result.input_count
            total_created += result.output_count
            total_failed += result.failed_count
            if result.success:
                any_success = True
            else:
                any_failure = True
                last_error = result.message
                if stop_on_failure:
                    self.vtlog.info("pipeline_stopped_on_failure", run_id=run_id, module=module.name)
                    break

        if any_failure and any_success:
            status = "partially_completed"
        elif any_failure:
            status = "failed"
        else:
            status = "completed"

        self.repos.pipeline_runs.finish(
            run_id,
            status,
            total_processed=total_processed,
            total_created=total_created,
            total_failed=total_failed,
            error_message=last_error if any_failure else None,
        )
        self.vtlog.info(
            "pipeline_run_finished",
            run_id=run_id, status=status,
            processed=total_processed, created=total_created, failed=total_failed,
        )
        return run_id
