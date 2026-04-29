"""Pipeline orchestration: templates, scheduler, cron, per-stage health (File 22)."""
from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Protocol

from pipeline.registry import RUN_TYPES

ALLOWED_ON_FAILURE = ("stop", "skip", "continue")
TEMPLATE_STATUSES = ("draft", "active", "archived")
DEFAULT_TEMPLATE_SLUG = "standard_v1"


# ---------------------------------------------------------------------------
# Cron evaluator
# ---------------------------------------------------------------------------
class CronEvaluatorAdapter(Protocol):
    name: str

    def next_fire(self, *, after: _dt.datetime, expr: str, tz: str = "UTC") -> _dt.datetime:
        ...


def _parse_field(token: str, lo: int, hi: int) -> set[int]:
    token = token.strip()
    if token == "*":
        return set(range(lo, hi + 1))
    if token.startswith("*/"):
        try:
            step = int(token[2:])
        except ValueError:
            raise ValueError(f"invalid step in cron field: {token!r}")
        if step <= 0:
            raise ValueError(f"invalid step in cron field: {token!r}")
        return {n for n in range(lo, hi + 1) if (n - lo) % step == 0}
    try:
        n = int(token)
    except ValueError:
        raise ValueError(f"unsupported cron field: {token!r}")
    if not (lo <= n <= hi):
        raise ValueError(f"cron field {token!r} out of range [{lo},{hi}]")
    return {n}


class SimpleCronEvaluator:
    """Supports only `*`, `N`, and `*/N` per field; ignores tz (treats as UTC)."""

    name = "simple_v1"

    def _parse(self, expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"cron expression must have 5 fields: {expr!r}")
        m, h, dom, mon, dow = parts
        return (
            _parse_field(m, 0, 59),
            _parse_field(h, 0, 23),
            _parse_field(dom, 1, 31),
            _parse_field(mon, 1, 12),
            _parse_field(dow, 0, 6),
        )

    def next_fire(self, *, after: _dt.datetime, expr: str, tz: str = "UTC") -> _dt.datetime:
        m_set, h_set, dom_set, mon_set, dow_set = self._parse(expr)
        cur = after.replace(second=0, microsecond=0) + _dt.timedelta(minutes=1)
        # Cap at ~2 years of minute steps to avoid runaway.
        for _ in range(2 * 366 * 24 * 60):
            if (cur.month in mon_set and cur.day in dom_set
                    and (cur.weekday() + 1) % 7 in dow_set
                    and cur.hour in h_set and cur.minute in m_set):
                return cur
            cur = cur + _dt.timedelta(minutes=1)
        raise ValueError(f"could not find next fire for cron {expr!r} within 2 years")


_default_cron_evaluator: CronEvaluatorAdapter = SimpleCronEvaluator()


def get_default_cron_evaluator() -> CronEvaluatorAdapter:
    return _default_cron_evaluator


def set_default_cron_evaluator(adapter: CronEvaluatorAdapter | None) -> None:
    global _default_cron_evaluator
    _default_cron_evaluator = adapter or SimpleCronEvaluator()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None, microsecond=0)


def _iso(dt: _dt.datetime) -> str:
    return dt.replace(microsecond=0).isoformat(timespec="seconds")


def _validate_steps(steps: list[dict]) -> list[dict]:
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    out: list[dict] = []
    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise ValueError(f"step[{i}] must be an object")
        rt = raw.get("run_type")
        if rt not in RUN_TYPES:
            raise ValueError(f"step[{i}].run_type {rt!r} is not a known run_type")
        if rt == "full_pipeline":
            raise ValueError("steps may not nest full_pipeline")
        on_fail = raw.get("on_failure", "continue")
        if on_fail not in ALLOWED_ON_FAILURE:
            raise ValueError(f"step[{i}].on_failure must be one of {ALLOWED_ON_FAILURE}")
        cfg = raw.get("config") or {}
        if not isinstance(cfg, dict):
            raise ValueError(f"step[{i}].config must be an object")
        out.append({"run_type": rt, "config": cfg, "on_failure": on_fail})
    return out


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------
def create_template(repos, *, project_id: int | None, name: str, slug: str,
                    steps: list[dict], notes: str | None = None,
                    created_by: str | None = None,
                    status: str = "active") -> dict:
    if status not in TEMPLATE_STATUSES:
        raise ValueError(f"invalid status {status!r}")
    if not name or not slug:
        raise ValueError("name and slug required")
    validated = _validate_steps(steps)
    version = repos.pipeline_templates.latest_version(
        project_id=project_id, slug=slug,
    ) + 1
    tid = repos.pipeline_templates.create({
        "project_id": int(project_id) if project_id is not None else None,
        "name": name, "slug": slug, "version": version,
        "status": status, "steps": validated,
        "notes": notes, "created_by": created_by,
    })
    return repos.pipeline_templates.get(tid)


def update_template(repos, template_id: int, *, name: str | None = None,
                    status: str | None = None, steps: list[dict] | None = None,
                    notes: str | None = None) -> dict:
    tpl = repos.pipeline_templates.get(int(template_id))
    if not tpl:
        raise ValueError(f"template {template_id} not found")
    payload: dict = {}
    if name is not None:
        payload["name"] = name
    if status is not None:
        if status not in TEMPLATE_STATUSES:
            raise ValueError(f"invalid status {status!r}")
        payload["status"] = status
    if steps is not None:
        payload["steps"] = _validate_steps(steps)
    if notes is not None:
        payload["notes"] = notes
    if payload:
        repos.pipeline_templates.update(int(template_id), payload)
    return repos.pipeline_templates.get(int(template_id))


def clone_template(repos, template_id: int, *, name: str | None = None,
                   project_id: int | None = None,
                   created_by: str | None = None) -> dict:
    src = repos.pipeline_templates.get(int(template_id))
    if not src:
        raise ValueError(f"template {template_id} not found")
    target_project = project_id if project_id is not None else src.get("project_id")
    return create_template(
        repos,
        project_id=target_project,
        name=name or f"{src['name']} (copy)",
        slug=src["slug"],
        steps=src["steps"],
        notes=src.get("notes"),
        created_by=created_by or "clone",
        status="draft",
    )


def archive_template(repos, template_id: int) -> dict:
    return update_template(repos, template_id, status="archived")


def resolve_template(repos, *, template_id: int | None = None,
                     project_id: int | None = None,
                     slug: str = DEFAULT_TEMPLATE_SLUG) -> dict:
    if template_id is not None:
        tpl = repos.pipeline_templates.get(int(template_id))
        if not tpl:
            raise ValueError(f"template {template_id} not found")
        return tpl
    # Prefer project-scoped active template by slug, then global.
    if project_id is not None:
        tpl = repos.pipeline_templates.get_by_slug(
            slug, project_id=int(project_id), status="active",
        )
        if tpl:
            return tpl
    tpl = repos.pipeline_templates.find_one({
        "slug": slug, "project_id": None, "status": "active",
    })
    if not tpl:
        raise ValueError(f"no active template with slug {slug!r}")
    return tpl


# ---------------------------------------------------------------------------
# Template execution
# ---------------------------------------------------------------------------
def run_template(repos, pipeline_runner, *, template: dict,
                 project_id: int, icp_id: int | None = None,
                 dry_run: bool = False, parent_run_id: int | None = None,
                 overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    steps = template.get("steps") or []
    executed: list[dict] = []
    failed = False
    for i, step in enumerate(steps):
        rt = step["run_type"]
        cfg = dict(step.get("config") or {})
        cfg.update(overrides.get(rt, {}))
        on_fail = step.get("on_failure", "continue")
        try:
            run_id = pipeline_runner.run_now(
                project_id=int(project_id),
                icp_id=int(icp_id) if icp_id is not None else None,
                run_type=rt,
                config=cfg,
                dry_run=dry_run,
            )
            child = repos.pipeline_runs.get(run_id) or {}
            status = child.get("status") or "unknown"
        except Exception as exc:  # pragma: no cover - defensive
            run_id = None
            status = "failed"
            child = {"error_message": str(exc)}
        step_record = {
            "step_index": i,
            "run_type": rt,
            "on_failure": on_fail,
            "run_id": run_id,
            "status": status,
            "started_at": (child.get("started_at") if run_id else None),
            "finished_at": (child.get("finished_at") if run_id else None),
            "total_processed": int(child.get("total_processed") or 0),
            "total_created": int(child.get("total_created") or 0),
            "total_failed": int(child.get("total_failed") or 0),
            "error_message": child.get("error_message"),
        }
        executed.append(step_record)
        if status in ("failed", "partially_completed"):
            failed = True
            if on_fail == "stop":
                break
    summary = {
        "template_id": template.get("id"),
        "template_slug": template.get("slug"),
        "template_version": template.get("version"),
        "step_count": len(steps),
        "executed_count": len(executed),
        "steps": executed,
    }
    if parent_run_id is not None:
        repos.pipeline_runs.set_summary(int(parent_run_id), summary)
    summary["overall_status"] = "failed" if failed else "completed"
    return summary


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
def update_next_fire(repos, schedule_id: int, *, now: _dt.datetime | None = None,
                     evaluator: CronEvaluatorAdapter | None = None) -> dict:
    sch = repos.pipeline_schedules.get(int(schedule_id))
    if not sch:
        raise ValueError(f"schedule {schedule_id} not found")
    ev = evaluator or get_default_cron_evaluator()
    base = now or _now()
    nxt = ev.next_fire(after=base, expr=sch["cron_expr"], tz=sch.get("timezone") or "UTC")
    repos.pipeline_schedules.update(int(schedule_id), {"next_fire_at": _iso(nxt)})
    return repos.pipeline_schedules.get(int(schedule_id))


def fire_schedule(repos, pipeline_runner, schedule_id: int, *,
                  now: _dt.datetime | None = None,
                  evaluator: CronEvaluatorAdapter | None = None) -> dict:
    sch = repos.pipeline_schedules.get(int(schedule_id))
    if not sch:
        raise ValueError(f"schedule {schedule_id} not found")
    template = resolve_template(repos, template_id=int(sch["template_id"]))
    base = now or _now()
    parent_id = pipeline_runner.run_now(
        project_id=int(sch["project_id"]),
        icp_id=sch.get("icp_id"),
        run_type="full_pipeline",
        config={"template_id": int(template["id"]), "schedule_id": int(sch["id"])},
        dry_run=False,
    )
    ev = evaluator or get_default_cron_evaluator()
    nxt = ev.next_fire(after=base, expr=sch["cron_expr"], tz=sch.get("timezone") or "UTC")
    repos.pipeline_schedules.update(int(schedule_id), {
        "last_fired_at": _iso(base),
        "last_run_id": int(parent_id),
        "next_fire_at": _iso(nxt),
    })
    return {"schedule_id": int(schedule_id), "run_id": int(parent_id),
            "fired_at": _iso(base), "next_fire_at": _iso(nxt)}


def scheduler_tick(repos, pipeline_runner, *, now: _dt.datetime | None = None,
                   limit: int = 50,
                   evaluator: CronEvaluatorAdapter | None = None) -> dict:
    base = now or _now()
    due = repos.pipeline_schedules.list_due(now_iso_str=_iso(base), limit=int(limit))
    fired: list[dict] = []
    skipped: list[dict] = []
    for sch in due:
        try:
            res = fire_schedule(
                repos, pipeline_runner, int(sch["id"]), now=base, evaluator=evaluator,
            )
            fired.append(res)
        except Exception as exc:
            skipped.append({"schedule_id": int(sch["id"]), "reason": str(exc)})
    return {"now": _iso(base), "due_count": len(due),
            "fired_count": len(fired), "skipped_count": len(skipped),
            "fired": fired, "skipped": skipped}


# ---------------------------------------------------------------------------
# Health roll-up
# ---------------------------------------------------------------------------
def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return float(s[k])


def _parse_iso(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def stage_health(repos, run_type: str, *, project_id: int | None = None,
                 limit: int = 50) -> dict:
    query: dict = {"run_type": run_type}
    if project_id is not None:
        query["project_id"] = int(project_id)
    rows = repos.pipeline_runs.find(query, order_by="started_at DESC, id DESC", limit=int(limit))
    n = len(rows)
    success = sum(1 for r in rows if r.get("status") == "completed")
    failed = sum(1 for r in rows if r.get("status") in ("failed", "partially_completed"))
    durations: list[float] = []
    for r in rows:
        started = _parse_iso(r.get("started_at"))
        finished = _parse_iso(r.get("finished_at"))
        if started and finished:
            durations.append(max(0.0, (finished - started).total_seconds() * 1000.0))
    last = rows[0] if rows else None
    last_error: str | None = None
    for r in rows:
        if r.get("error_message"):
            last_error = r["error_message"]
            break
    return {
        "run_type": run_type,
        "count_total": n,
        "count_success": success,
        "count_failed": failed,
        "success_rate": (success / n) if n else 0.0,
        "p50_ms": _percentile(durations, 50),
        "p95_ms": _percentile(durations, 95),
        "last_run_at": (last.get("started_at") if last else None),
        "last_status": (last.get("status") if last else None),
        "last_error": last_error,
    }


def stages_overview(repos, *, project_id: int | None = None,
                    limit: int = 50) -> dict:
    stages = [stage_health(repos, rt, project_id=project_id, limit=limit)
              for rt in RUN_TYPES]
    return {"project_id": project_id, "limit": limit, "stages": stages}


def trace_run(repos, run_id: int) -> dict:
    run = repos.pipeline_runs.get(int(run_id))
    if not run:
        raise ValueError(f"run {run_id} not found")
    steps = repos.pipeline_run_steps.find(
        {"pipeline_run_id": int(run_id)},
        order_by="started_at ASC, id ASC",
    )
    summary = run.get("summary") or {}
    children: list[dict] = []
    for s in (summary.get("steps") or []):
        rid = s.get("run_id")
        child = repos.pipeline_runs.get(int(rid)) if rid else None
        children.append({"step": s, "child_run": child})
    return {"run": run, "steps": steps, "summary": summary, "children": children}
