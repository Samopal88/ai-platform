"""
AI Workspace Platform - Auth API
Minimal email-based auth for public MVP.
"""
from __future__ import annotations

import re
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_token import create_auth_token, verify_auth_token
from app.core.auth_password import hash_password, verify_password
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.auth_acceptance_store import mark_terms_accepted, mark_terms_accepted_db
from app.services.email_service import send_password_reset_email, send_welcome_email

router = APIRouter(prefix="/api/auth", tags=["Auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LOGIN_RATE_WINDOW_SEC = 60
_LOGIN_RATE_LIMIT = 5
_LOGIN_RATE_BUCKETS: dict[str, list[float]] = {}


class GuestOrLoginRequest(BaseModel):
    email: str
    accept_terms: bool | None = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    accept_terms: bool | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    email: str
    token: str
    sync_token: str
    accepted_terms: bool
    accepted_at: str


class GuestResponse(BaseModel):
    user_id: str
    sync_token: str
    token: str


class GenericOkResponse(BaseModel):
    ok: bool = True


class ResolveResponse(BaseModel):
    user_id: str
    email: str
    token: str


def _token_from_uid(uid: str) -> str:
    return uid.replace("-", "")[:8].upper()


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _validate_email(email: str) -> str:
    normalized = _normalize_email(email)
    if not _EMAIL_RE.match(normalized):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid email")
    return normalized


def _check_login_rate_limit(client_ip: str) -> None:
    if settings.ENVIRONMENT.lower() not in {"production", "prod"} and client_ip in {"127.0.0.1", "::1", "localhost", "testclient", "unknown"}:
        return

    now = time.time()
    bucket = _LOGIN_RATE_BUCKETS.get(client_ip, [])
    bucket = [ts for ts in bucket if (now - ts) < _LOGIN_RATE_WINDOW_SEC]
    if len(bucket) >= _LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in a minute.",
        )
    bucket.append(now)
    _LOGIN_RATE_BUCKETS[client_ip] = bucket


def _build_auth_response(user: User, accepted_at: str) -> AuthResponse:
    uid = str(user.id)
    return AuthResponse(
        user_id=uid,
        email=(user.email or "").strip().lower(),
        token=create_auth_token(uid, user.email or ""),
        sync_token=_token_from_uid(uid),
        accepted_terms=True,
        accepted_at=accepted_at,
    )


def _mark_acceptance(db: Session, request: Request, user: User) -> str:
    client_ip = (request.client.host if request.client else None)
    user_agent = request.headers.get("User-Agent")
    try:
        return mark_terms_accepted_db(
            db,
            str(user.id),
            ip_address=client_ip,
            user_agent=user_agent,
        )
    except Exception:
        if settings.ENVIRONMENT.lower() in {"production", "prod"}:
            raise
        return mark_terms_accepted(str(user.id))


def _build_password_reset_link(token: str) -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/chat?reset_token={token}"


def _password_reset_ok() -> GenericOkResponse:
    return GenericOkResponse(ok=True)


@router.post("/register", response_model=AuthResponse)
def register(data: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if data.accept_terms is not True:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Terms and privacy acceptance is required.",
        )
    client_ip = (request.client.host if request.client else "") or "unknown"
    _check_login_rate_limit(client_ip)

    email = _validate_email(data.email)
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None and existing.password_hash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    try:
        password_hash = hash_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if existing is None:
        user = User(id=uuid4(), email=email, password_hash=password_hash, plan_type="free")
        db.add(user)
    else:
        user = existing
        user.password_hash = password_hash
    db.commit()
    db.refresh(user)
    accepted_at = _mark_acceptance(db, request, user)
    try:
        send_welcome_email(email)
    except Exception:
        pass
    return _build_auth_response(user, accepted_at)


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = (request.client.host if request.client else "") or "unknown"
    _check_login_rate_limit(client_ip)

    email = _validate_email(data.email)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    accepted_at = _mark_acceptance(db, request, user)
    return _build_auth_response(user, accepted_at)


@router.post("/guest-or-login", response_model=AuthResponse)
def guest_or_login(data: GuestOrLoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Email-based MVP login:
    - find by email or create user
    - return user_id + signed token
    """
    if data.accept_terms is not True:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Terms and privacy acceptance is required.",
        )
    client_ip = (request.client.host if request.client else "") or "unknown"
    _check_login_rate_limit(client_ip)

    email = _validate_email(data.email)
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            id=uuid4(),
            email=email,
            password_hash="",
            plan_type="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    accepted_at = _mark_acceptance(db, request, user)
    return _build_auth_response(user, accepted_at)


@router.post("/guest", response_model=GuestResponse)
def create_guest(db: Session = Depends(get_db)):
    """
    Legacy endpoint kept for backward compatibility.
    """
    new_id = uuid4()
    sync_token = _token_from_uid(str(new_id)).lower()
    email = f"guest-{sync_token}@workspace.local"
    user = User(
        id=new_id,
        email=email,
        password_hash="",
        plan_type="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return GuestResponse(
        user_id=str(new_id),
        sync_token=sync_token.upper(),
        token=create_auth_token(str(new_id), email),
    )


class MigrateGuestChatsRequest(BaseModel):
    guest_token: str


class MigrateGuestChatsResponse(BaseModel):
    migrated: int


@router.post("/migrate-guest-chats", response_model=MigrateGuestChatsResponse)
def migrate_guest_chats(
    data: MigrateGuestChatsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Reassign personal chats from a guest user to the calling email-authenticated user.
    The caller must supply their own Bearer token in Authorization AND the guest token.
    Only chats with no project_id are migrated (personal chats only).
    """
    from app.models.chat import Chat as ChatModel
    from app.models.chat_artifact import ChatArtifact

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth token")
    auth_payload = verify_auth_token(auth_header[len("Bearer "):].strip())
    if not auth_payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token")

    try:
        real_uid = UUID(str(auth_payload["uid"]))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token")

    real_user = db.query(User).filter(User.id == real_uid).first()
    if real_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Verify the guest token is real and belongs to a guest user
    guest_payload = verify_auth_token(data.guest_token)
    if not guest_payload:
        return MigrateGuestChatsResponse(migrated=0)

    try:
        guest_uid = UUID(str(guest_payload["uid"]))
    except Exception:
        return MigrateGuestChatsResponse(migrated=0)

    if guest_uid == real_uid:
        return MigrateGuestChatsResponse(migrated=0)

    guest_user = db.query(User).filter(User.id == guest_uid).first()
    if guest_user is None:
        return MigrateGuestChatsResponse(migrated=0)

    # Reject if the supposed "guest" account is actually a real (email-registered) user.
    # Guest accounts always have workspace.local emails; accepting a real user's token here
    # would silently move their chats to the caller's account.
    guest_email = (guest_user.email or "").lower()
    if not guest_email.endswith("@workspace.local"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provided guest_token does not belong to a guest account.",
        )

    # Reassign personal chats (no project_id)
    chats = db.query(ChatModel).filter(
        ChatModel.user_id == guest_uid,
        ChatModel.project_id.is_(None),
    ).all()

    for chat in chats:
        chat.user_id = real_uid
        # Reassign artifacts too
        db.query(ChatArtifact).filter(ChatArtifact.chat_id == chat.id).update(
            {"user_id": real_uid}
        )

    db.commit()
    return MigrateGuestChatsResponse(migrated=len(chats))


@router.post("/forgot-password", response_model=GenericOkResponse)
def forgot_password(data: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = (request.client.host if request.client else "") or "unknown"
    _check_login_rate_limit(client_ip)

    email = _validate_email(data.email)
    user = db.query(User).filter(User.email == email).first()
    if user is not None and user.password_hash:
        token = create_auth_token(
            str(user.id),
            user.email or "",
            ttl_seconds=60 * 60,
            token_type="password_reset",
        )
        try:
            send_password_reset_email(
                to_email=email,
                reset_url=_build_password_reset_link(token),
                reset_token=token,
            )
        except Exception:
            pass
    return _password_reset_ok()


@router.post("/reset-password", response_model=GenericOkResponse)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    payload = verify_auth_token(data.token, expected_token_type="password_reset")
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired reset token")

    try:
        user_id = UUID(str(payload["uid"]))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired reset token")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        user.password_hash = hash_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    db.commit()
    return _password_reset_ok()


@router.get("/resolve", response_model=ResolveResponse)
def resolve_token(token: str, db: Session = Depends(get_db)):
    token = token.strip().upper()

    try:
        uid = UUID(token if len(token) == 36 else token.lower())
        user = db.query(User).filter(User.id == uid).first()
        if user:
            return ResolveResponse(
                user_id=str(user.id),
                email=(user.email or "").strip().lower(),
                token=create_auth_token(str(user.id), user.email or ""),
            )
    except (ValueError, AttributeError):
        pass

    all_users = db.query(User).all()
    for user in all_users:
        if _token_from_uid(str(user.id)) == token:
            return ResolveResponse(
                user_id=str(user.id),
                email=(user.email or "").strip().lower(),
                token=create_auth_token(str(user.id), user.email or ""),
            )

    raise HTTPException(status_code=404, detail="Sync code not found")
