from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.errors import ApiError
from app.db.models import Project, Run
from app.db.session import get_db
from app.schemas.api import (
    ProjectCreate,
    ProjectDefaults,
    ProjectListResponse,
    ProjectRead,
    ProjectUpdate,
)
from app.schemas.common import new_id, utc_now_iso

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_project_read(db: Session, proj: Project) -> ProjectRead:
    run_count = db.scalar(select(func.count(Run.id)).where(Run.project_id == proj.id)) or 0
    last_activity = db.scalar(select(func.max(Run.updated_at)).where(Run.project_id == proj.id))
    return ProjectRead(
        project_id=proj.id,
        name=proj.name,
        description=proj.description,
        defaults=ProjectDefaults.model_validate(proj.defaults_json or {}),
        run_count=run_count,
        last_activity_at=last_activity,
        created_at=proj.created_at,
        updated_at=proj.updated_at,
    )


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    now = utc_now_iso()
    proj = Project(
        id=new_id("prj"),
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        defaults_json=payload.defaults.model_dump(),
        created_at=now,
        updated_at=now,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return _to_project_read(db, proj)


@router.get("", response_model=ProjectListResponse)
def list_projects(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    total = db.scalar(select(func.count(Project.id))) or 0
    rows = db.scalars(
        select(Project).order_by(Project.updated_at.desc()).offset(offset).limit(limit)
    ).all()
    return ProjectListResponse(
        items=[_to_project_read(db, p) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    proj = db.get(Project, project_id)
    if proj is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Project '{project_id}' was not found.",
        )
    return _to_project_read(db, proj)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    proj = db.get(Project, project_id)
    if proj is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Project '{project_id}' was not found.",
        )
    if payload.name is not None:
        proj.name = payload.name.strip()
    if payload.description is not None:
        proj.description = payload.description.strip() or None
    if payload.defaults is not None:
        proj.defaults_json = payload.defaults.model_dump()
    proj.updated_at = utc_now_iso()
    db.commit()
    db.refresh(proj)
    return _to_project_read(db, proj)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> None:
    proj = db.get(Project, project_id)
    if proj is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Project '{project_id}' was not found.",
        )
    db.delete(proj)
    db.commit()
