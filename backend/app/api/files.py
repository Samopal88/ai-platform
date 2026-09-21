"""
AI Workspace Platform - Files API
Project/file endpoints with token-scoped ownership checks.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.db.session import get_db
from app.models.chat import Chat
from app.models.chat_artifact import ChatArtifact
from app.models.file import File as FileModel
from app.models.project import Project
from app.models.user import User
from app.schemas.artifact import ArtifactListResponse
from app.schemas.file import FileListResponse, FileRead
from app.services import artifact_service
from app.services.limits_service import ensure_project_storage_available, ensure_storage_available
from app.services.file_service import delete_file, list_files, save_upload

router = APIRouter(tags=["Files"])
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


def _owned_project(db: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _owned_file(db: Session, file_id: uuid.UUID, user_id: uuid.UUID) -> FileModel:
    db_file = (
        db.query(FileModel)
        .join(Project, Project.id == FileModel.project_id)
        .filter(FileModel.id == file_id, Project.user_id == user_id)
        .first()
    )
    if db_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return db_file


def _owned_chat(db: Session, chat_id: uuid.UUID, user_id: uuid.UUID) -> Chat:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if chat.project_id is not None:
        _owned_project(db=db, project_id=chat.project_id, user_id=user_id)
        return chat
    if chat.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


@router.post(
    "/api/projects/{project_id}/files",
    response_model=FileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _owned_project(db=db, project_id=project_id, user_id=current_user.id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds {MAX_UPLOAD_SIZE} bytes",
        )
    ensure_storage_available(current_user, len(content))
    ensure_project_storage_available(project, current_user, len(content))

    return save_upload(
        db=db,
        project_id=project_id,
        filename=file.filename or "upload",
        content=content,
        mime_type=file.content_type,
    )


@router.get(
    "/api/projects/{project_id}/files",
    response_model=FileListResponse,
)
def get_project_files(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db=db, project_id=project_id, user_id=current_user.id)
    files = list_files(db=db, project_id=project_id)
    return FileListResponse(files=files, total=len(files))


@router.get(
    "/api/files/{file_id}",
)
def download_file(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_file = _owned_file(db=db, file_id=file_id, user_id=current_user.id)
    disk_path = Path(db_file.storage_path)
    if not disk_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File data not found on disk")
    return FileResponse(
        path=str(disk_path),
        media_type=db_file.mime_type or "application/octet-stream",
        filename=db_file.filename,
    )


@router.get(
    "/api/chat-artifact",
)
def download_temp_artifact(
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Download a temporary chat artifact file by its storage path."""
    disk_path = Path(path)
    # Security: only allow paths inside the known temp upload dir
    from app.services.file_service import UPLOAD_ROOT
    try:
        disk_path.resolve().relative_to((UPLOAD_ROOT / "_temp").resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid path")
    if not disk_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    filename = disk_path.name
    # Strip UUID prefix (hex_originalname)
    if '_' in filename:
        filename = filename[filename.index('_') + 1:]
    import mimetypes
    mime, _ = mimetypes.guess_type(filename)
    return FileResponse(
        path=str(disk_path),
        media_type=mime or "application/octet-stream",
        filename=filename,
    )


@router.get(
    "/api/chats/{chat_id}/artifacts",
    response_model=ArtifactListResponse,
)
def list_chat_artifacts(
    chat_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)
    artifacts = artifact_service.list_chat_artifacts(db=db, chat_id=chat_id)
    return ArtifactListResponse(artifacts=artifacts, total=len(artifacts))


@router.get(
    "/api/chats/{chat_id}/artifacts/{artifact_id}/download",
)
def download_chat_artifact(
    chat_id: uuid.UUID,
    artifact_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)
    artifact = artifact_service.get_chat_artifact(db=db, chat_id=chat_id, artifact_id=artifact_id)
    if artifact is None or artifact.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    disk_path = Path(artifact.storage_path)
    if not disk_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact data not found on disk")
    return FileResponse(
        path=str(disk_path),
        media_type=artifact.mime_type or "application/octet-stream",
        filename=artifact.filename,
    )


@router.get(
    "/api/projects/{project_id}/files/{file_id}/download",
)
def download_file_project_scoped(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db=db, project_id=project_id, user_id=current_user.id)
    db_file = _owned_file(db=db, file_id=file_id, user_id=current_user.id)
    if db_file.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return download_file(file_id=file_id, db=db, current_user=current_user)


@router.delete(
    "/api/projects/{project_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_file_project_scoped(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db=db, project_id=project_id, user_id=current_user.id)
    db_file = _owned_file(db=db, file_id=file_id, user_id=current_user.id)
    if db_file.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return remove_file(file_id=file_id, db=db, current_user=current_user)


@router.delete(
    "/api/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_file(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_file = _owned_file(db=db, file_id=file_id, user_id=current_user.id)
    removed = delete_file(db=db, project_id=db_file.project_id, file_id=file_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
