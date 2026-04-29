"""PipelineModule base classes.

PipelineModule  → abstract interface
BaseModule      → wraps execute() with run-step tracking, logging, try/except.
                  Real modules subclass BaseModule and implement execute(ctx).
"""
from __future__ import annotations

import traceback
from abc import ABC, abstractmethod

from pipeline.context import PipelineContext
from pipeline.result import ModuleResult


class PipelineModule(ABC):
    name: str = "module"

    @abstractmethod
    def run(self, ctx: PipelineContext) -> ModuleResult:
        ...


class BaseModule(PipelineModule):
    """Subclasses implement `execute(ctx) -> ModuleResult`.

    `run()` handles run-step DB tracking + logging + error capture so a failing
    module is recorded but does not raise out of the orchestrator.
    """
    name: str = "BaseModule"

    @abstractmethod
    def execute(self, ctx: PipelineContext) -> ModuleResult:
        ...

    def run(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        step_id = ctx.repos.pipeline_run_steps.start(ctx.pipeline_run_id, self.name)
        ctx.repos.module_logs.log(
            pipeline_run_id=ctx.pipeline_run_id,
            pipeline_run_step_id=step_id,
            module_name=self.name,
            level="info",
            message="module_started",
            context={"dry_run": ctx.dry_run},
        )
        try:
            result = self.execute(ctx)
            if not isinstance(result, ModuleResult):
                result = ModuleResult.fail(f"{self.name}.execute() did not return ModuleResult")
        except Exception as e:
            tb = traceback.format_exc()
            log.error("module_exception", module=self.name, exc=str(e))
            ctx.repos.module_logs.log(
                pipeline_run_id=ctx.pipeline_run_id,
                pipeline_run_step_id=step_id,
                module_name=self.name,
                level="error",
                message="module_exception",
                context={"error": str(e), "traceback": tb},
            )
            ctx.repos.pipeline_run_steps.finish(
                step_id, status="failed",
                error_message=str(e),
                result_data={"traceback": tb},
            )
            return ModuleResult.fail(str(e))

        status = "completed" if result.success else "failed"
        ctx.repos.pipeline_run_steps.finish(
            step_id,
            status=status,
            input_count=result.input_count,
            output_count=result.output_count,
            failed_count=result.failed_count,
            error_message=None if result.success else (result.message or "unknown error"),
            result_data=result.data,
        )
        ctx.repos.module_logs.log(
            pipeline_run_id=ctx.pipeline_run_id,
            pipeline_run_step_id=step_id,
            module_name=self.name,
            level="info" if result.success else "error",
            message="module_finished",
            context={
                "status": status,
                "input": result.input_count,
                "output": result.output_count,
                "failed": result.failed_count,
                "msg": result.message,
            },
        )
        return result


class DummyEchoModule(BaseModule):
    """Trivially-passing module used to verify the framework end-to-end."""
    name = "DummyEchoModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        ctx.child_logger(self.name).info("echo", project_id=ctx.project_id, icp_id=ctx.icp_id)
        return ModuleResult.ok(
            input_count=0, output_count=1,
            message="echo",
            data={"project_id": ctx.project_id, "dry_run": ctx.dry_run},
        )
