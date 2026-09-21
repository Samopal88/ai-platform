"""Preview/approve API for AI-assisted file edits."""
from __future__ import annotations

import difflib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.db.session import get_db
from app.models.context import AgentTask, FileEditProposal, FileVersion
from app.models.file import File as FileModel
from app.models.project import Project
from app.models.user import User
from app.services.model_router import ModelRouter

router = APIRouter(tags=["File Edits"])

_model_router = ModelRouter()

# Formats supported for AI-assisted editing (UTF-8 text types only)
_EDITABLE_SUFFIXES = {".txt", ".md", ".json", ".yaml", ".yml", ".csv", ".py", ".js", ".ts", ".html", ".htm", ".css", ".sh", ".toml", ".ini", ".conf", ".xml"}


class FileEditProposalCreate(BaseModel):
    proposed_content: str = Field(min_length=1)
    instruction: str | None = Field(default=None, max_length=2000)


class FileEditProposalRead(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    status: str
    diff_text: str
    created_at: datetime

    class Config:
        from_attributes = True


def _owned_file(db: Session, project_id: uuid.UUID, file_id: uuid.UUID, user_id: uuid.UUID) -> FileModel:
    db_file = (
        db.query(FileModel)
        .join(Project, Project.id == FileModel.project_id)
        .filter(FileModel.id == file_id, FileModel.project_id == project_id, Project.user_id == user_id)
        .first()
    )
    if db_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return db_file


def _proposal_path(file_id: uuid.UUID, proposal_id: uuid.UUID) -> Path:
    from app.services.file_service import UPLOAD_ROOT

    root = UPLOAD_ROOT / "_proposals" / str(file_id)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{proposal_id}.proposal"


def _read_text_file(db_file: FileModel) -> str:
    path = Path(db_file.storage_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File data not found on disk")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="Only UTF-8 text files can be edited in this preview flow")


@router.post(
    "/api/projects/{project_id}/files/{file_id}/edit-proposals",
    response_model=FileEditProposalRead,
    status_code=status.HTTP_201_CREATED,
)
def create_file_edit_proposal(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    data: FileEditProposalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_file = _owned_file(db, project_id, file_id, current_user.id)
    # Phase 7.1: read_only files cannot receive edit proposals
    if (db_file.mode or "read_only") == "read_only":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File is read-only and cannot be edited. Set mode to 'editable' first.",
        )
    current_content = _read_text_file(db_file)
    proposed_content = data.proposed_content
    diff_text = "".join(
        difflib.unified_diff(
            current_content.splitlines(keepends=True),
            proposed_content.splitlines(keepends=True),
            fromfile=db_file.filename,
            tofile=f"{db_file.filename}.proposed",
        )
    )
    if not diff_text:
        raise HTTPException(status_code=422, detail="Proposal does not change the file")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = AgentTask(
        project_id=project_id,
        user_id=current_user.id,
        task_type="file_edit",
        mode="preview",
        status="pending_approval",
        prompt=data.instruction or "Propose file edit",
        plan={"file_id": str(file_id)},
        result=None,
        error=None,
        requires_approval=True,
        approved_at=None,
    )
    db.add(task)
    db.flush()

    proposal_id = uuid.uuid4()
    proposed_path = _proposal_path(file_id, proposal_id)
    proposed_path.write_text(proposed_content, encoding="utf-8")
    proposal = FileEditProposal(
        id=proposal_id,
        task_id=task.id,
        file_id=file_id,
        base_version_id=None,
        proposed_content_path=str(proposed_path),
        diff_text=diff_text,
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


# ---------------------------------------------------------------------------
# Phase 7.3 – AI-assisted edit proposal generation
# ---------------------------------------------------------------------------

class AIEditRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    instruction: str = Field(min_length=5, max_length=2000)
    model_id: str | None = Field(default=None)


@router.post(
    "/api/projects/{project_id}/files/{file_id}/ai-edit",
    response_model=FileEditProposalRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_ai_edit_proposal(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    data: AIEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Phase 7.3: AI-assisted file edit.

    Uses the current file content + instruction to generate proposed new content
    via the model router, then stores it in the existing proposal/approval pipeline.
    The file is NOT changed until the user calls the approve endpoint.
    """
    db_file = _owned_file(db, project_id, file_id, current_user.id)

    # Guard: read_only files cannot receive any edit proposals
    if (db_file.mode or "read_only") == "read_only":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File is read-only. Set mode to 'editable' first.",
        )

    # Guard: only supported UTF-8 text formats
    suffix = Path(db_file.filename).suffix.lower()
    if suffix not in _EDITABLE_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"AI editing is not supported for files with extension '{suffix}'. Supported: {', '.join(sorted(_EDITABLE_SUFFIXES))}",
        )

    current_content = _read_text_file(db_file)

    # Build prompt for the model
    model_id = data.model_id or "gpt-4o-mini"
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert file editor. The user will give you the current file content and "
                "an editing instruction. You must return ONLY the complete new file content — no explanations, "
                "no markdown code fences, no commentary. Just the raw file text as it should appear after the edit."
            ),
        },
        {
            "role": "user",
            "content": (
                f"File: {db_file.filename}\n\n"
                f"Current content:\n{current_content}\n\n"
                f"Instruction: {data.instruction}\n\n"
                "Return only the complete new file content."
            ),
        },
    ]

    try:
        response = _model_router.route_response(messages, model_id=model_id, max_tokens=4096)
        proposed_content = (response.text or "").strip()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI provider error: {exc}")

    if not proposed_content:
        raise HTTPException(status_code=422, detail="AI returned empty content")

    diff_text = "".join(
        difflib.unified_diff(
            current_content.splitlines(keepends=True),
            proposed_content.splitlines(keepends=True),
            fromfile=db_file.filename,
            tofile=f"{db_file.filename}.ai_proposed",
        )
    )
    if not diff_text:
        raise HTTPException(status_code=422, detail="AI proposed content is identical to the current file")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = AgentTask(
        project_id=project_id,
        user_id=current_user.id,
        task_type="file_edit",
        mode="ai_proposal",
        status="pending_approval",
        prompt=data.instruction,
        plan={"file_id": str(file_id), "model_id": model_id, "ai_generated": True},
        result=None,
        error=None,
        requires_approval=True,
        approved_at=None,
    )
    db.add(task)
    db.flush()

    proposal_id = uuid.uuid4()
    proposed_path = _proposal_path(file_id, proposal_id)
    proposed_path.write_text(proposed_content, encoding="utf-8")
    proposal = FileEditProposal(
        id=proposal_id,
        task_id=task.id,
        file_id=file_id,
        base_version_id=None,
        proposed_content_path=str(proposed_path),
        diff_text=diff_text,
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal

def list_file_edit_proposals(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_file(db, project_id, file_id, current_user.id)
    proposals = (
        db.query(FileEditProposal)
        .filter(FileEditProposal.file_id == file_id)
        .order_by(FileEditProposal.created_at.desc())
        .all()
    )
    return {"proposals": proposals, "total": len(proposals)}


@router.post("/api/projects/{project_id}/files/{file_id}/edit-proposals/{proposal_id}/approve")
def approve_file_edit_proposal(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_file = _owned_file(db, project_id, file_id, current_user.id)
    proposal = (
        db.query(FileEditProposal)
        .filter(FileEditProposal.id == proposal_id, FileEditProposal.file_id == file_id)
        .first()
    )
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="Proposal is already resolved")

    file_path = Path(db_file.storage_path)
    proposed_path = Path(proposal.proposed_content_path)
    if not proposed_path.exists():
        raise HTTPException(status_code=404, detail="Proposed content not found")
    current_bytes = file_path.read_bytes()
    version_number = db.query(FileVersion).filter(FileVersion.file_id == file_id).count() + 1
    version_path = file_path.with_name(f"{file_path.name}.v{version_number}.bak")
    version_path.write_bytes(current_bytes)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    version = FileVersion(
        file_id=file_id,
        version_number=version_number,
        storage_path=str(version_path),
        size=len(current_bytes),
        mime_type=db_file.mime_type,
        created_by=current_user.id,
        created_reason="approved_file_edit_proposal",
        created_at=now,
    )
    db.add(version)
    db.flush()

    new_bytes = proposed_path.read_bytes()
    file_path.write_bytes(new_bytes)
    db_file.size = len(new_bytes)
    db_file.updated_at = now
    db_file.extraction_status = "pending"
    db_file.index_status = "pending"
    proposal.status = "approved"
    proposal.approved_by = current_user.id
    proposal.approved_at = now
    proposal.applied_version_id = version.id
    db.commit()
    return {"ok": True, "proposal_id": str(proposal.id), "version_id": str(version.id)}


@router.post("/api/projects/{project_id}/files/{file_id}/edit-proposals/{proposal_id}/reject")
def reject_file_edit_proposal(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_file(db, project_id, file_id, current_user.id)
    proposal = (
        db.query(FileEditProposal)
        .filter(FileEditProposal.id == proposal_id, FileEditProposal.file_id == file_id)
        .first()
    )
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="Proposal is already resolved")
    proposal.status = "rejected"
    db.commit()
    return {"ok": True, "proposal_id": str(proposal.id), "status": proposal.status}


# ---------------------------------------------------------------------------
# Phase 7.1 – file mode management
# ---------------------------------------------------------------------------

class FileModeUpdate(BaseModel):
    mode: str = Field(pattern=r"^(read_only|editable|generated)$")


@router.patch("/api/projects/{project_id}/files/{file_id}/mode")
def set_file_mode(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    data: FileModeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the mode (read_only|editable|generated) of a project file."""
    db_file = _owned_file(db, project_id, file_id, current_user.id)
    db_file.mode = data.mode
    db.commit()
    return {"ok": True, "file_id": str(db_file.id), "mode": db_file.mode}


# ---------------------------------------------------------------------------
# Phase 7.2 – file version list and restore
# ---------------------------------------------------------------------------

class FileVersionRead(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    version_number: int
    size: int
    mime_type: str | None
    created_reason: str | None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/api/projects/{project_id}/files/{file_id}/versions")
def list_file_versions(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List saved versions for a project file (most recent first)."""
    _owned_file(db, project_id, file_id, current_user.id)
    versions = (
        db.query(FileVersion)
        .filter(FileVersion.file_id == file_id)
        .order_by(FileVersion.version_number.desc())
        .all()
    )
    return {"versions": versions, "total": len(versions)}


@router.post("/api/projects/{project_id}/files/{file_id}/versions/{version_id}/restore")
def restore_file_version(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore a file to a saved version, saving the current content first."""
    db_file = _owned_file(db, project_id, file_id, current_user.id)
    version = (
        db.query(FileVersion)
        .filter(FileVersion.id == version_id, FileVersion.file_id == file_id)
        .first()
    )
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    version_path = Path(version.storage_path)
    if not version_path.exists():
        raise HTTPException(status_code=404, detail="Version data not found on disk")

    file_path = Path(db_file.storage_path)
    current_bytes = file_path.read_bytes() if file_path.exists() else b""
    new_version_number = db.query(FileVersion).filter(FileVersion.file_id == file_id).count() + 1
    backup_path = file_path.with_name(f"{file_path.name}.v{new_version_number}.bak")
    backup_path.write_bytes(current_bytes)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    backup_version = FileVersion(
        file_id=file_id,
        version_number=new_version_number,
        storage_path=str(backup_path),
        size=len(current_bytes),
        mime_type=db_file.mime_type,
        created_by=current_user.id,
        created_reason="pre_restore_backup",
        created_at=now,
    )
    db.add(backup_version)
    db.flush()

    restored_bytes = version_path.read_bytes()
    file_path.write_bytes(restored_bytes)
    db_file.size = len(restored_bytes)
    db_file.updated_at = now
    db_file.extraction_status = "pending"
    db_file.index_status = "pending"
    db.commit()
    return {"ok": True, "file_id": str(db_file.id), "restored_version_id": str(version.id), "backup_version_id": str(backup_version.id)}
