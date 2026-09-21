"""Memory API endpoints for project-scoped key-value storage with auth.

Phase 8.3: Pin/unpin added.  Delete, list, and recall remain backward-compatible.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.services.memory_service import (
    store_memory,
    _load,
    _is_expired,
    _save,
)

router = APIRouter(prefix="/api/projects/{project_id}/memory", tags=["memory"])


class MemoryStoreRequest(BaseModel):
    key: str
    value: str
    ttl_days: Optional[int] = 30


class MemoryEntry(BaseModel):
    key: str
    value: str
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    pinned: bool = False


def _ensure_project_access(db: Session, project_id: UUID, current_user: User) -> None:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("", response_model=MemoryEntry, status_code=201)
def store(
    project_id: UUID,
    body: MemoryStoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntry:
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    project_id_str = str(project_id)
    store_memory(project_id_str, body.key, body.value, body.ttl_days or 30)
    data = _load(project_id_str)
    entry = data[body.key]
    return MemoryEntry(
        key=body.key,
        value=entry["value"],
        created_at=entry.get("created_at"),
        expires_at=entry.get("expires_at"),
        pinned=bool(entry.get("pinned", False)),
    )


@router.get("/{key}", response_model=MemoryEntry)
def recall(
    project_id: UUID,
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntry:
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    data = _load(str(project_id))
    entry = data.get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Memory key not found")
    if _is_expired(entry):
        raise HTTPException(status_code=404, detail="Memory key has expired")
    return MemoryEntry(
        key=key,
        value=entry["value"],
        created_at=entry.get("created_at"),
        expires_at=entry.get("expires_at"),
        pinned=bool(entry.get("pinned", False)),
    )


@router.get("", response_model=list[MemoryEntry])
def list_all(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MemoryEntry]:
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    data = _load(str(project_id))
    results = []
    for k, entry in data.items():
        if _is_expired(entry):
            continue
        results.append(MemoryEntry(
            key=k,
            value=entry["value"],
            created_at=entry.get("created_at"),
            expires_at=entry.get("expires_at"),
            pinned=bool(entry.get("pinned", False)),
        ))
    # Pinned entries first, then by creation time
    results.sort(key=lambda e: (not e.pinned, e.created_at or ""))
    return results


@router.delete("/{key}", status_code=204)
def delete(
    project_id: UUID,
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    project_id_str = str(project_id)
    data = _load(project_id_str)
    if key not in data:
        raise HTTPException(status_code=404, detail="Memory key not found")
    del data[key]
    _save(project_id_str, data)


@router.post("/{key}/pin", response_model=MemoryEntry)
def pin_memory(
    project_id: UUID,
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntry:
    """Phase 8.3: Pin a memory entry so it appears first in listings."""
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    project_id_str = str(project_id)
    data = _load(project_id_str)
    if key not in data:
        raise HTTPException(status_code=404, detail="Memory key not found")
    if _is_expired(data[key]):
        raise HTTPException(status_code=404, detail="Memory key has expired")
    data[key]["pinned"] = True
    _save(project_id_str, data)
    entry = data[key]
    return MemoryEntry(
        key=key,
        value=entry["value"],
        created_at=entry.get("created_at"),
        expires_at=entry.get("expires_at"),
        pinned=True,
    )


@router.post("/{key}/unpin", response_model=MemoryEntry)
def unpin_memory(
    project_id: UUID,
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntry:
    """Phase 8.3: Unpin a memory entry."""
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    project_id_str = str(project_id)
    data = _load(project_id_str)
    if key not in data:
        raise HTTPException(status_code=404, detail="Memory key not found")
    data[key]["pinned"] = False
    _save(project_id_str, data)
    entry = data[key]
    return MemoryEntry(
        key=key,
        value=entry["value"],
        created_at=entry.get("created_at"),
        expires_at=entry.get("expires_at"),
        pinned=False,
    )



def _ensure_project_access(db: Session, project_id: UUID, current_user: User) -> None:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("", response_model=MemoryEntry, status_code=201)
def store(
    project_id: UUID,
    body: MemoryStoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntry:
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    project_id_str = str(project_id)
    store_memory(project_id_str, body.key, body.value, body.ttl_days or 30)
    data = _load(project_id_str)
    entry = data[body.key]
    return MemoryEntry(
        key=body.key,
        value=entry["value"],
        created_at=entry.get("created_at"),
        expires_at=entry.get("expires_at"),
    )


@router.get("/{key}", response_model=MemoryEntry)
def recall(
    project_id: UUID,
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryEntry:
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    data = _load(str(project_id))
    entry = data.get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Memory key not found")
    if _is_expired(entry):
        raise HTTPException(status_code=404, detail="Memory key has expired")
    return MemoryEntry(
        key=key,
        value=entry["value"],
        created_at=entry.get("created_at"),
        expires_at=entry.get("expires_at"),
    )


@router.get("", response_model=list[MemoryEntry])
def list_all(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MemoryEntry]:
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    data = _load(str(project_id))
    results = []
    for k, entry in data.items():
        if _is_expired(entry):
            continue
        results.append(MemoryEntry(
            key=k,
            value=entry["value"],
            created_at=entry.get("created_at"),
            expires_at=entry.get("expires_at"),
        ))
    return results


@router.delete("/{key}", status_code=204)
def delete(
    project_id: UUID,
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _ensure_project_access(db=db, project_id=project_id, current_user=current_user)
    project_id_str = str(project_id)
    data = _load(project_id_str)
    if key not in data:
        raise HTTPException(status_code=404, detail="Memory key not found")
    del data[key]
    _save(project_id_str, data)
