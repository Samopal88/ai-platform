"""
AI Workspace Platform - Chats API
Token-scoped chat and message CRUD.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.chat import ChatCreate, ChatRead, ChatUpdate, MessageCreate, MessageRead
from app.services import chat_service
from app.services.file_service import save_temp_upload
from app.services.limits_service import ensure_storage_available

router = APIRouter(tags=["Chats"])


class ChatCreateBody(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    model: str


class PersonalChatCreateBody(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    model: str


class MessageCreateBody(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    tokens_used: int = Field(0, ge=0)
    model: Optional[str] = None
    extra_data: Optional[dict] = None


def _owned_project(db: Session, project_id: UUID, user_id: UUID) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _owned_chat(db: Session, chat_id: UUID, user_id: UUID):
    chat = chat_service.get_chat(db=db, chat_id=chat_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    if chat.project_id is not None:
        _owned_project(db=db, project_id=chat.project_id, user_id=user_id)
        return chat

    if chat.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


@router.post("/api/chats", response_model=ChatRead, status_code=status.HTTP_201_CREATED)
def create_personal_chat(
    data: PersonalChatCreateBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat_data = ChatCreate(
        project_id=None,
        user_id=current_user.id,
        title=data.title or "Новый чат",
        model=data.model,
    )
    return chat_service.create_chat(db=db, data=chat_data)


@router.get("/api/chats", response_model=list[ChatRead])
def list_personal_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return chat_service.list_personal_chats(db=db, user_id=current_user.id)


@router.post("/api/projects/{project_id}/chats", response_model=ChatRead, status_code=status.HTTP_201_CREATED)
def create_chat(
    project_id: UUID,
    data: ChatCreateBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db=db, project_id=project_id, user_id=current_user.id)
    chat_data = ChatCreate(
        project_id=project_id,
        user_id=current_user.id,
        title=data.title or "Новый чат",
        model=data.model,
    )
    return chat_service.create_chat(db=db, data=chat_data)


@router.get("/api/projects/{project_id}/chats", response_model=list[ChatRead])
def list_chats(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db=db, project_id=project_id, user_id=current_user.id)
    return chat_service.list_chats(db=db, project_id=project_id)


@router.delete("/api/projects/{project_id}/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_chat(
    project_id: UUID,
    chat_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db=db, project_id=project_id, user_id=current_user.id)
    chat = _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)
    if chat.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if not chat_service.delete_project_chat(db=db, project_id=project_id, chat_id=chat_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")


@router.get("/api/chats/{chat_id}", response_model=ChatRead)
def get_chat(
    chat_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)


@router.put("/api/chats/{chat_id}", response_model=ChatRead)
def update_chat(
    chat_id: UUID,
    data: ChatUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)

    update_dict = data.model_dump(exclude_unset=True)
    new_project_id = update_dict.get("project_id")
    if new_project_id is not None:
        _owned_project(db=db, project_id=new_project_id, user_id=current_user.id)

    chat = chat_service.update_chat(db=db, chat_id=chat.id, data=data)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


@router.patch("/api/chats/{chat_id}", response_model=ChatRead)
def patch_chat(
    chat_id: UUID,
    data: ChatUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update_chat(chat_id=chat_id, data=data, db=db, current_user=current_user)


@router.delete("/api/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)
    if not chat_service.delete_chat(db=db, chat_id=chat_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")


@router.post("/api/chats/{chat_id}/upload", status_code=status.HTTP_201_CREATED)
async def upload_chat_file(
    chat_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    _MAX_CHAT_UPLOAD = 20 * 1024 * 1024  # 20 MB guard
    if len(content) > _MAX_CHAT_UPLOAD:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB for chat uploads).")
    ensure_storage_available(current_user, len(content))
    return save_temp_upload(
        filename=file.filename or "upload",
        content=content,
        mime_type=file.content_type,
    )


@router.post("/api/chats/{chat_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def add_message(
    chat_id: UUID,
    data: MessageCreateBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)
    msg_data = MessageCreate(
        chat_id=chat_id,
        role=data.role,
        content=data.content,
        tokens_used=data.tokens_used,
        model=data.model,
        extra_data=data.extra_data,
    )
    message = chat_service.add_message(db=db, data=msg_data)
    if data.role == "user":
        chat_service.auto_title_from_first_user_message(db=db, chat_id=chat_id, first_message=data.content)
    return message


@router.get("/api/chats/{chat_id}/messages", response_model=list[MessageRead])
def get_messages(
    chat_id: UUID,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)
    return chat_service.get_messages(db=db, chat_id=chat_id, limit=limit)


@router.get("/api/projects/{project_id}/chats/{chat_id}/messages", response_model=list[MessageRead])
def get_project_chat_messages(
    project_id: UUID,
    chat_id: UUID,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db=db, project_id=project_id, user_id=current_user.id)
    chat = _owned_chat(db=db, chat_id=chat_id, user_id=current_user.id)
    if chat.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    messages = chat_service.get_project_chat_messages(
        db=db,
        project_id=project_id,
        chat_id=chat_id,
        limit=limit,
    )
    if messages is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return messages
