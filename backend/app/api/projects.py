"""
AI Workspace Platform - Projects API
Token-scoped project CRUD.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.limits_service import ensure_project_limit
from app.services import project_service

router = APIRouter(prefix="/api/projects", tags=["Projects"])


class ProjectInstructionsPatch(BaseModel):
    instructions: Optional[str] = None


def _get_owned_project(db: Session, project_id: UUID, current_user: User):
    project = project_service.get_project(db=db, project_id=project_id)
    if project is None or project.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_project_limit(db=db, user=current_user)
    return project_service.create_project(db=db, data=data, user_id=current_user.id)


@router.get("", response_model=list[ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.list_projects(db=db, user_id=current_user.id)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_owned_project(db=db, project_id=project_id, current_user=current_user)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db=db, project_id=project_id, current_user=current_user)
    project = project_service.update_project(db=db, project_id=project_id, data=data)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def patch_project_instructions(
    project_id: UUID,
    data: ProjectInstructionsPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db=db, project_id=project_id, current_user=current_user)
    project = project_service.update_project(
        db=db,
        project_id=project_id,
        data=ProjectUpdate(instructions=data.instructions),
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db=db, project_id=project_id, current_user=current_user)
    deleted = project_service.delete_project(db=db, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
