"""Smoke test for pipeline framework. Runs against a temp DB. Prints PASS/FAIL.

Usage:
    python tests/test_pipeline_smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT_DIR)

from db.sqlite_storage import SQLiteStorage
from pipeline import (
    BaseModule, ModuleResult, PipelineContext, PipelineRegistry, PipelineRunner,
)
from repositories import RepoRegistry
from setup_database import apply_migrations
from vtutils.vtlogger import initLog


SEEN: dict = {"contexts": []}


class EchoOkModule(BaseModule):
    name = "EchoOkModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        SEEN["contexts"].append({"dry_run": ctx.dry_run, "icp_id": ctx.icp_id})
        return ModuleResult.ok(input_count=2, output_count=5, message="ok")


class EchoFailModule(BaseModule):
    name = "EchoFailModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        raise RuntimeError("boom_in_module")


def assertion(cond: bool, msg: str, failures: list[str]) -> None:
    print(f"  {'OK' if cond else 'FAIL'}  {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    db_path = tmp.name
    print(f"Using temp DB: {db_path}")

    storage = SQLiteStorage(db_path)
    storage.run_script_file(f"{ROOT_DIR}/db/schema.sql")
    apply_migrations(storage, Path(f"{ROOT_DIR}/db/migrations"))

    repos = RepoRegistry(storage)
    vtlog = initLog("pipeline_smoke")

    project_id = repos.projects.create({"name": "P"})
    icp_id = repos.icps.create({"project_id": project_id, "name": "ICP1"})

    registry = PipelineRegistry()
    registry.register("full_pipeline", [EchoOkModule, EchoFailModule, EchoOkModule])
    runner = PipelineRunner(repos, vtlog, registry=registry)

    print("\n[full_pipeline with mixed modules]")
    run_id = runner.run_now(
        project_id=project_id, icp_id=icp_id,
        run_type="full_pipeline",
        config={"hello": "world"},
        dry_run=True,
    )
    assertion(run_id > 0, f"run created id={run_id}", failures)

    run = repos.pipeline_runs.get(run_id)
    assertion(run["status"] == "partially_completed",
              f"run.status == partially_completed (got {run['status']})", failures)
    assertion(run["finished_at"] is not None, "run.finished_at set", failures)
    # totals: 2 oks (input 2, output 5 each) + 1 failure
    assertion(run["total_processed"] == 4, f"total_processed=4 (got {run['total_processed']})", failures)
    assertion(run["total_created"] == 10, f"total_created=10 (got {run['total_created']})", failures)

    steps = repos.pipeline_run_steps.find({"pipeline_run_id": run_id}, order_by="id ASC")
    assertion(len(steps) == 3, f"3 step rows (got {len(steps)})", failures)
    assertion(steps[0]["status"] == "completed", "step1 completed", failures)
    assertion(steps[1]["status"] == "failed", "step2 failed", failures)
    assertion(bool(steps[1]["error_message"]) and "boom" in steps[1]["error_message"],
              "step2 error_message contains boom", failures)
    assertion(steps[2]["status"] == "completed", "step3 completed (continued past failure)", failures)

    logs = repos.module_logs.find({"pipeline_run_id": run_id})
    assertion(len(logs) >= 4, f"module_logs written (got {len(logs)})", failures)

    # dry_run propagated
    assertion(len(SEEN["contexts"]) == 2 and all(c["dry_run"] is True for c in SEEN["contexts"]),
              "dry_run propagated to module contexts", failures)
    assertion(all(c["icp_id"] == icp_id for c in SEEN["contexts"]),
              "icp_id propagated to module contexts", failures)

    print("\n[stop_on_failure]")
    SEEN["contexts"].clear()
    run_id2 = runner.run_now(
        project_id=project_id, icp_id=icp_id,
        run_type="full_pipeline",
        config={"stop_on_failure": True},
    )
    steps2 = repos.pipeline_run_steps.find({"pipeline_run_id": run_id2}, order_by="id ASC")
    assertion(len(steps2) == 2, f"stop_on_failure: only 2 steps ran (got {len(steps2)})", failures)
    run2 = repos.pipeline_runs.get(run_id2)
    assertion(run2["status"] == "partially_completed",
              f"stop_on_failure run.status (got {run2['status']})", failures)

    print("\n[get_run_detail]")
    detail = runner.get_run_detail(run_id)
    assertion(detail and detail["run"]["id"] == run_id, "detail.run", failures)
    assertion(len(detail["steps"]) == 3, "detail.steps len", failures)
    assertion(len(detail["logs"]) >= 4, "detail.logs len", failures)

    print("\n[recent runs]")
    recent = runner.list_recent_runs(project_id, limit=10)
    assertion(len(recent) == 2, f"list_recent_runs (got {len(recent)})", failures)

    storage.close()
    os.unlink(db_path)

    print("\n" + "=" * 60)
    if failures:
        print(f"FAIL — {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS — all assertions OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
