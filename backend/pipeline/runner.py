"""PipelineRunner: thin facade used by API + tests."""
from __future__ import annotations

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.registry import PipelineRegistry, default_registry
from repositories import RepoRegistry


class PipelineRunner:
    def __init__(
        self,
        repos: RepoRegistry,
        vtlog,
        *,
        registry: PipelineRegistry | None = None,
    ) -> None:
        self.repos = repos
        self.vtlog = vtlog
        self.registry = registry or default_registry
        self.orchestrator = PipelineOrchestrator(repos, vtlog)

    def run_now(
        self,
        *,
        project_id: int,
        icp_id: int | None,
        run_type: str,
        config: dict | None = None,
        dry_run: bool = False,
    ) -> int:
        module_classes = self.registry.get(run_type)
        if not module_classes:
            raise ValueError(
                f"No modules registered for run_type='{run_type}'. "
                f"Known: {self.registry.known_run_types()}"
            )
        modules = [cls() for cls in module_classes]
        return self.orchestrator.run(
            project_id=project_id,
            icp_id=icp_id,
            run_type=run_type,
            modules=modules,
            config=config,
            dry_run=dry_run,
        )

    def list_recent_runs(self, project_id: int, limit: int = 50) -> list[dict]:
        return self.repos.pipeline_runs.find(
            {"project_id": project_id},
            order_by="started_at DESC, id DESC",
            limit=limit,
        )

    def get_run_detail(self, run_id: int, *, log_limit: int = 50) -> dict | None:
        run = self.repos.pipeline_runs.get(run_id)
        if not run:
            return None
        steps = self.repos.pipeline_run_steps.find(
            {"pipeline_run_id": run_id},
            order_by="started_at ASC, id ASC",
        )
        logs = self.repos.module_logs.find(
            {"pipeline_run_id": run_id},
            order_by="created_at DESC, id DESC",
            limit=log_limit,
        )
        return {"run": run, "steps": steps, "logs": logs}
