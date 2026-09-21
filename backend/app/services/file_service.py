"""
AI Workspace Platform - File Service
Real file storage: persists uploads to disk and records metadata in the DB.
"""
import uuid
import mimetypes
from pathlib import Path
from typing import Optional, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.file import File
from app.models.project import Project
from app.models.user import User


# Base directory where uploaded files are stored.
# Each project gets its own sub-directory: <UPLOAD_ROOT>/<project_id>/
UPLOAD_ROOT = Path(getattr(settings, "STORAGE_ROOT", "/opt/ai-workspace/storage")) / "uploads"


def _project_dir(project_id: uuid.UUID) -> Path:
    d = UPLOAD_ROOT / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(
    db: Session,
    project_id: uuid.UUID,
    filename: str,
    content: bytes,
    mime_type: Optional[str] = None,
) -> File:
    """
    Save *content* to disk under the project directory and create a DB record.

    Returns the newly created File ORM object.
    """
    # Derive MIME type if not supplied
    if not mime_type:
        guessed, _ = mimetypes.guess_type(filename)
        mime_type = guessed or "application/octet-stream"

    # Write file to disk with a stable unique name to avoid collisions
    file_id = uuid.uuid4()
    safe_name = f"{file_id.hex}_{Path(filename).name}"
    dest = _project_dir(project_id) / safe_name
    dest.write_bytes(content)

    db_file = File(
        id=file_id,
        project_id=project_id,
        filename=filename,
        size=len(content),
        mime_type=mime_type,
        storage_path=str(dest),
    )
    db.add(db_file)

    # Update project counters
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is not None:
        project.file_count = (project.file_count or 0) + 1
        project.storage_used = (project.storage_used or 0) + len(content)
        user = db.query(User).filter(User.id == project.user_id).first()
        if user is not None:
            user.storage_used = (user.storage_used or 0) + len(content)

    db.commit()
    db.refresh(db_file)

    # Phase 6.1: trigger async indexing (extraction + chunking) after upload
    try:
        import threading
        from app.services.indexing_service import index_file
        from app.db.session import SessionLocal as _SessionLocal

        def _run_index(file_id: uuid.UUID) -> None:
            with _SessionLocal() as _db:
                _file = _db.query(File).filter(File.id == file_id).first()
                if _file is not None:
                    index_file(_db, _file)

        t = threading.Thread(target=_run_index, args=(file_id,), daemon=True)
        t.start()
    except Exception:
        pass  # indexing is best-effort; do not fail upload

    return db_file


def save_temp_upload(
    filename: str,
    content: bytes,
    mime_type: Optional[str] = None,
) -> dict:
    """
    Save a file to a temporary upload directory (not linked to any project).
    Returns a dict with storage_path, mime_type, and filename — suitable for
    embedding in message extra_data so the completion endpoint can read it.
    """
    if not mime_type:
        guessed, _ = mimetypes.guess_type(filename)
        mime_type = guessed or "application/octet-stream"

    temp_dir = UPLOAD_ROOT / "_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4()
    safe_name = f"{file_id.hex}_{Path(filename).name}"
    dest = temp_dir / safe_name
    dest.write_bytes(content)
    return {"storage_path": str(dest), "mime_type": mime_type, "filename": filename}


def list_files(db: Session, project_id: uuid.UUID) -> List[File]:
    """Return all files for a project, ordered newest-first."""
    return (
        db.query(File)
        .filter(File.project_id == project_id)
        .order_by(File.created_at.desc())
        .all()
    )


def get_file(db: Session, project_id: uuid.UUID, file_id: uuid.UUID) -> Optional[File]:
    """Fetch a single file record that belongs to the given project."""
    return (
        db.query(File)
        .filter(File.id == file_id, File.project_id == project_id)
        .first()
    )


def delete_file(db: Session, project_id: uuid.UUID, file_id: uuid.UUID) -> bool:
    """
    Delete the DB record and the on-disk file.

    Returns True if the file was found and removed, False otherwise.
    """
    db_file = get_file(db, project_id, file_id)
    if db_file is None:
        return False

    # Remove from disk (best-effort)
    disk_path = Path(db_file.storage_path)
    if disk_path.exists():
        disk_path.unlink()

    # Update project counters
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is not None:
        project.file_count = max(0, (project.file_count or 1) - 1)
        project.storage_used = max(0, (project.storage_used or db_file.size) - db_file.size)
        user = db.query(User).filter(User.id == project.user_id).first()
        if user is not None:
            user.storage_used = max(0, (user.storage_used or db_file.size) - db_file.size)

    db.delete(db_file)
    db.commit()
    return True
