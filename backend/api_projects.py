"""Project CRUD endpoints (minimal — list + create for now)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api_shared import repos

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


@router.get("")
def list_projects() -> dict:
    return {"data": repos.projects.find({}, order_by="id DESC")}


@router.post("")
def create_project(body: ProjectCreate) -> dict:
    pid = repos.projects.create(body.model_dump(exclude_none=True))
    proj = repos.projects.get(pid)
    if not proj:
        raise HTTPException(status_code=500, detail="failed to create project")
    return proj


@router.get("/{project_id}")
def get_project(project_id: int) -> dict:
    proj = repos.projects.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")
    return proj
