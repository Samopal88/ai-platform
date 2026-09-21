"""
AI Workspace Platform - Project Service
Real SQLAlchemy CRUD for the Project model.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chat import Chat
from app.models.message import Message
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


def create_project(
    db: Session,
    data: ProjectCreate,
    user_id: UUID,
) -> Project:
    """
    Create a new project owned by user_id.

    user_id is required: the Project model has user_id NOT NULL.
    Callers must supply a valid user UUID — this function raises ValueError
    if user_id is None rather than violating the DB constraint silently.
    """
    if user_id is None:
        raise ValueError(
            "user_id is required to create a project. "
            "The Project model enforces a NOT NULL foreign key to users.id."
        )
    project = Project(
        name=data.name,
        description=data.description,
        instructions=getattr(data, "instructions", None),
        user_id=user_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: UUID) -> Optional[Project]:
    """Return a project by UUID, or None if not found."""
    return db.query(Project).filter(Project.id == project_id).first()


def list_projects(db: Session, user_id: Optional[UUID] = None) -> list:
    """
    Return all projects.
    If user_id is provided, filter to that user's projects only.
    """
    q = db.query(Project)
    if user_id is not None:
        q = q.filter(Project.user_id == user_id)
    projects = q.order_by(Project.created_at.desc()).all()
    _attach_project_activity_metadata(db=db, projects=projects)
    # Active projects first: newest last_message_at first; projects without chat activity go last.
    projects.sort(
        key=lambda p: getattr(p, "last_message_at", None) or datetime.min,
        reverse=True,
    )
    return projects


def update_project(
    db: Session,
    project_id: UUID,
    data: ProjectUpdate,
) -> Optional[Project]:
    """
    Update mutable fields on an existing project.
    Returns the updated project, or None if not found.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: UUID) -> bool:
    """
    Delete a project by UUID.
    Returns True if deleted, False if not found.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return False
    db.delete(project)
    db.commit()
    return True


def _attach_project_activity_metadata(db: Session, projects: list[Project]) -> None:
    """Populate transient chat_count + last_message_at for project list responses."""
    if not projects:
        return

    project_ids = [p.id for p in projects]

    chat_rows = (
        db.query(
            Chat.project_id.label("project_id"),
            func.count(Chat.id).label("chat_count"),
        )
        .filter(Chat.project_id.in_(project_ids))
        .group_by(Chat.project_id)
        .all()
    )
    chat_count_map = {row.project_id: int(row.chat_count or 0) for row in chat_rows}

    msg_rows = (
        db.query(
            Chat.project_id.label("project_id"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .join(Message, Message.chat_id == Chat.id)
        .filter(Chat.project_id.in_(project_ids))
        .group_by(Chat.project_id)
        .all()
    )
    msg_map = {row.project_id: row.last_message_at for row in msg_rows}

    for project in projects:
        project.chat_count = chat_count_map.get(project.id, 0)
        project.last_message_at = msg_map.get(project.id)
