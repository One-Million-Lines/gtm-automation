"""PipelineContext shared by all modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from repositories import RepoRegistry
from vtutils.vtlogger import getLog


@dataclass
class PipelineContext:
    project_id: int
    icp_id: Optional[int]
    pipeline_run_id: int
    repos: RepoRegistry
    vtlog: Any  # main app logger; modules should prefer child_logger()
    config: dict = field(default_factory=dict)
    dry_run: bool = False

    def child_logger(self, module_name: str):
        """Return a logger scoped to the current module."""
        return getLog(f"pipeline.{module_name}")
