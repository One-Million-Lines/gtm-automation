"""Pipeline orchestration API: templates, schedules, scheduler, health (File 22)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api_shared import pipeline_runner, repos
from services import orchestrator_service as svc

router = APIRouter(tags=["orchestration"])


# ---------- Schemas ----------
class StepIn(BaseModel):
    run_type: str
    config: dict = Field(default_factory=dict)
    on_failure: str = "continue"


class TemplateCreate(BaseModel):
    project_id: Optional[int] = None
    name: str
    slug: str
    steps: list[StepIn]
    notes: Optional[str] = None
    created_by: Optional[str] = None
    status: str = "active"


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    steps: Optional[list[StepIn]] = None
    notes: Optional[str] = None


class TemplateClone(BaseModel):
    name: Optional[str] = None
    project_id: Optional[int] = None
    created_by: Optional[str] = None


class ScheduleCreate(BaseModel):
    project_id: int
    template_id: int
    icp_id: Optional[int] = None
    name: str
    cron_expr: str
    timezone: str = "UTC"
    enabled: bool = True
    notes: Optional[str] = None


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    template_id: Optional[int] = None
    icp_id: Optional[int] = None
    cron_expr: Optional[str] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None
    notes: Optional[str] = None


class TickIn(BaseModel):
    limit: int = 50


class RunTemplateIn(BaseModel):
    template_id: Optional[int] = None
    template_slug: Optional[str] = None
    project_id: int
    icp_id: Optional[int] = None
    overrides: dict = Field(default_factory=dict)
    dry_run: bool = False


# ---------- Templates ----------
@router.get("/pipeline/templates")
def list_templates(project_id: Optional[int] = None,
                   include_global: bool = True,
                   status: Optional[str] = None,
                   limit: int = 200):
    return repos.pipeline_templates.list_for_project(
        project_id, status=status, include_global=include_global, limit=limit,
    )


@router.get("/pipeline/templates/{template_id}")
def get_template(template_id: int):
    tpl = repos.pipeline_templates.get(template_id)
    if not tpl:
        raise HTTPException(404, f"template {template_id} not found")
    return tpl


@router.post("/pipeline/templates")
def create_template(body: TemplateCreate):
    try:
        return svc.create_template(
            repos,
            project_id=body.project_id,
            name=body.name,
            slug=body.slug,
            steps=[s.model_dump() for s in body.steps],
            notes=body.notes,
            created_by=body.created_by,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.patch("/pipeline/templates/{template_id}")
def update_template(template_id: int, body: TemplateUpdate):
    try:
        return svc.update_template(
            repos, template_id,
            name=body.name, status=body.status,
            steps=[s.model_dump() for s in body.steps] if body.steps is not None else None,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/pipeline/templates/{template_id}/clone")
def clone_template(template_id: int, body: TemplateClone):
    try:
        return svc.clone_template(
            repos, template_id,
            name=body.name, project_id=body.project_id, created_by=body.created_by,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/pipeline/templates/{template_id}")
def archive_template(template_id: int):
    try:
        return svc.archive_template(repos, template_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/pipeline/templates/run")
def run_template(body: RunTemplateIn):
    try:
        template = svc.resolve_template(
            repos,
            template_id=body.template_id,
            project_id=body.project_id,
            slug=body.template_slug or svc.DEFAULT_TEMPLATE_SLUG,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    parent_run_id = pipeline_runner.run_now(
        project_id=body.project_id,
        icp_id=body.icp_id,
        run_type="full_pipeline",
        config={"template_id": int(template["id"]), "overrides": body.overrides},
        dry_run=body.dry_run,
    )
    return {"parent_run_id": parent_run_id, "template_id": int(template["id"])}


# ---------- Schedules ----------
@router.get("/pipeline/schedules")
def list_schedules(project_id: int = Query(...), limit: int = 200):
    return repos.pipeline_schedules.list_for_project(project_id, limit=limit)


@router.get("/pipeline/schedules/{schedule_id}")
def get_schedule(schedule_id: int):
    s = repos.pipeline_schedules.get(schedule_id)
    if not s:
        raise HTTPException(404, f"schedule {schedule_id} not found")
    return s


@router.post("/pipeline/schedules")
def create_schedule(body: ScheduleCreate):
    if not repos.pipeline_templates.get(body.template_id):
        raise HTTPException(400, f"template {body.template_id} not found")
    # Validate cron at create time.
    try:
        ev = svc.get_default_cron_evaluator()
        from datetime import datetime, UTC
        nxt = ev.next_fire(
            after=datetime.now(UTC).replace(tzinfo=None),
            expr=body.cron_expr, tz=body.timezone,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    sid = repos.pipeline_schedules.create({
        "project_id": int(body.project_id),
        "template_id": int(body.template_id),
        "icp_id": body.icp_id,
        "name": body.name,
        "cron_expr": body.cron_expr,
        "timezone": body.timezone,
        "enabled": 1 if body.enabled else 0,
        "next_fire_at": nxt.isoformat(timespec="seconds"),
        "notes": body.notes,
    })
    return repos.pipeline_schedules.get(sid)


@router.patch("/pipeline/schedules/{schedule_id}")
def update_schedule(schedule_id: int, body: ScheduleUpdate):
    sch = repos.pipeline_schedules.get(schedule_id)
    if not sch:
        raise HTTPException(404, f"schedule {schedule_id} not found")
    payload: dict = {}
    if body.name is not None:
        payload["name"] = body.name
    if body.template_id is not None:
        if not repos.pipeline_templates.get(body.template_id):
            raise HTTPException(400, f"template {body.template_id} not found")
        payload["template_id"] = int(body.template_id)
    if body.icp_id is not None:
        payload["icp_id"] = int(body.icp_id) if body.icp_id else None
    if body.timezone is not None:
        payload["timezone"] = body.timezone
    if body.enabled is not None:
        payload["enabled"] = 1 if body.enabled else 0
    if body.notes is not None:
        payload["notes"] = body.notes
    if body.cron_expr is not None:
        payload["cron_expr"] = body.cron_expr
        try:
            from datetime import datetime, UTC
            ev = svc.get_default_cron_evaluator()
            nxt = ev.next_fire(
                after=datetime.now(UTC).replace(tzinfo=None),
                expr=body.cron_expr,
                tz=body.timezone or sch.get("timezone") or "UTC",
            )
            payload["next_fire_at"] = nxt.isoformat(timespec="seconds")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    if payload:
        repos.pipeline_schedules.update(schedule_id, payload)
    return repos.pipeline_schedules.get(schedule_id)


@router.delete("/pipeline/schedules/{schedule_id}")
def delete_schedule(schedule_id: int):
    if not repos.pipeline_schedules.get(schedule_id):
        raise HTTPException(404, f"schedule {schedule_id} not found")
    repos.pipeline_schedules.delete(schedule_id)
    return {"ok": True, "schedule_id": schedule_id}


@router.post("/pipeline/schedules/{schedule_id}/fire-now")
def fire_now(schedule_id: int):
    try:
        return svc.fire_schedule(repos, pipeline_runner, schedule_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


# ---------- Scheduler tick ----------
@router.post("/pipeline/scheduler/tick")
def scheduler_tick(body: TickIn | None = None):
    limit = body.limit if body else 50
    return svc.scheduler_tick(repos, pipeline_runner, limit=limit)


# ---------- Health & traces ----------
@router.get("/pipeline/health")
def health_overview(project_id: Optional[int] = None, limit: int = 50):
    return svc.stages_overview(repos, project_id=project_id, limit=limit)


@router.get("/pipeline/health/{run_type}")
def health_for_stage(run_type: str, project_id: Optional[int] = None, limit: int = 50):
    return svc.stage_health(repos, run_type, project_id=project_id, limit=limit)


@router.get("/pipeline/runs/{run_id}/trace")
def run_trace(run_id: int):
    try:
        return svc.trace_run(repos, run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
