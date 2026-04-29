"""FullPipelineModule — template-driven orchestration entry point (File 22)."""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult


class FullPipelineModule(BaseModule):
    """Resolves a pipeline_templates row and runs each step via PipelineRunner.

    Config keys:
      template_id (int, optional)   — explicit template to run
      template_slug (str, optional) — slug to resolve (defaults to 'standard_v1')
      overrides (dict, optional)    — {run_type: config_overrides}
      schedule_id (int, optional)   — informational, recorded in summary
    """

    name = "FullPipelineModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        # Lazy imports to avoid circular dependencies during module load.
        from pipeline.runner import PipelineRunner
        from services import orchestrator_service

        cfg = ctx.config or {}
        template_id = cfg.get("template_id")
        slug = cfg.get("template_slug") or orchestrator_service.DEFAULT_TEMPLATE_SLUG
        overrides = cfg.get("overrides") or {}

        try:
            template = orchestrator_service.resolve_template(
                ctx.repos,
                template_id=int(template_id) if template_id else None,
                project_id=ctx.project_id,
                slug=slug,
            )
        except ValueError as exc:
            return ModuleResult.fail(str(exc))

        runner = PipelineRunner(ctx.repos, ctx.vtlog)
        summary = orchestrator_service.run_template(
            ctx.repos,
            runner,
            template=template,
            project_id=ctx.project_id,
            icp_id=ctx.icp_id,
            dry_run=ctx.dry_run,
            parent_run_id=ctx.pipeline_run_id,
            overrides=overrides,
        )

        executed = summary.get("steps") or []
        success = sum(1 for s in executed if s.get("status") == "completed")
        failed = sum(1 for s in executed
                     if s.get("status") in ("failed", "partially_completed"))
        overall_failed = summary.get("overall_status") == "failed"
        msg = (f"template={template.get('slug')} v{template.get('version')} "
               f"steps={len(executed)}/{summary.get('step_count')} "
               f"success={success} failed={failed}")
        if overall_failed:
            return ModuleResult.fail(msg, data=summary)
        return ModuleResult.ok(
            input_count=len(executed),
            output_count=success,
            failed_count=failed,
            message=msg,
            data=summary,
        )
