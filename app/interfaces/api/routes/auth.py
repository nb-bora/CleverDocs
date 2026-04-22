"""Auth routes (JWT access + opaque refresh)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi import UploadFile
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.user_model import UserModel
from app.infrastructure.audit.audit_logger import AuditEvent, AuditLogger
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.interfaces.api.deps import (
    CurrentUser,
    Settings,
    _create_access_token,
    get_current_user,
    get_db,
    get_settings,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.interfaces.api.schemas.auth_tokens import LoginRequest, RefreshRequest, TokenPairResponse
from app.interfaces.api.schemas.users import ChangePasswordRequest


router = APIRouter(prefix="/v1/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post(
    "/login",
    response_model=TokenPairResponse,
    responses={
        403: {"description": "User disabled"},
    },
)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPairResponse:
    email = body.email.strip().lower()
    user = db.execute(select(UserModel).where(UserModel.email == email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=403, detail="User disabled")
    if not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(body.password, user.password_hash):
        # Best-effort audit (no org context at login time)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token, ttl = _create_access_token(settings=settings, user_id=user.id)
    refresh_token = issue_refresh_token(settings=settings, db=db, user_id=user.id)
    # Auth audit (organization unknown here)
    AuditLogger(db).log(
        AuditEvent(
            organization_id="auth",
            actor_user_id=user.id,
            action="AUTH_LOGIN",
            target_type="user",
            target_id=user.id,
            detail={"email": user.email},
        )
    )
    db.commit()
    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token, expires_in=ttl)


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(
    body: RefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPairResponse:
    new_refresh = rotate_refresh_token(settings=settings, db=db, raw_refresh_token=body.refresh_token)
    # After rotation, we need user_id; rotate returned new token only, so re-fetch by old token is not possible.
    # Instead, look up new refresh token row by hashing it.
    from app.interfaces.api.deps import _hash_refresh_token  # local import to avoid exporting
    from app.infrastructure.db.orm.models.refresh_token_model import RefreshTokenModel

    rt = db.execute(
        select(RefreshTokenModel).where(RefreshTokenModel.token_hash == _hash_refresh_token(new_refresh))
    ).scalar_one()
    access_token, ttl = _create_access_token(settings=settings, user_id=rt.user_id)
    return TokenPairResponse(access_token=access_token, refresh_token=new_refresh, expires_in=ttl)


@router.post("/logout")
def logout(
    body: RefreshRequest,
    db: Session = Depends(get_db),
) -> dict:
    revoke_refresh_token(db=db, raw_refresh_token=body.refresh_token)
    return {"status": "ok"}


@router.get("/me")
def me(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    u = db.get(UserModel, current_user.user_id)
    avatar = getattr(u, "avatar_storage_key", None) if u is not None else None
    display_name = getattr(u, "display_name", None) if u is not None else None
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "display_name": display_name,
        "avatar_storage_key": avatar,
    }


@router.post("/me/change_password")
def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(UserModel, current_user.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=403, detail="User disabled")
    if not user.password_hash:
        raise HTTPException(status_code=409, detail="PASSWORD_NOT_SET")
    if not pwd_context.verify(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.password_hash = pwd_context.hash(body.new_password)
    db.add(user)
    AuditLogger(db).log(
        AuditEvent(
            organization_id="auth",
            actor_user_id=user.id,
            action="AUTH_CHANGE_PASSWORD",
            target_type="user",
            target_id=user.id,
            detail=None,
        )
    )
    db.commit()
    return {"status": "ok"}


@router.post("/me/avatar")
def upload_avatar(
    file: UploadFile,
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="INVALID_IMAGE")

    user = db.get(UserModel, current_user.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    storage = LocalFileStorage(root_dir=settings.local_storage_dir)
    key = storage.save_upload(file)

    # Best-effort cleanup of previous avatar file.
    prev = getattr(user, "avatar_storage_key", None)
    if prev:
        try:
            storage.resolve(prev).unlink(missing_ok=True)
        except Exception:
            ...

    user.avatar_storage_key = key
    db.add(user)
    AuditLogger(db).log(
        AuditEvent(
            organization_id="auth",
            actor_user_id=user.id,
            action="AUTH_UPLOAD_AVATAR",
            target_type="user",
            target_id=user.id,
            detail={"content_type": file.content_type, "filename": file.filename},
        )
    )
    db.commit()
    return {"status": "ok", "avatar_storage_key": key}


@router.get("/me/avatar")
def get_my_avatar(
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> FileResponse:
    user = db.get(UserModel, current_user.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    key = getattr(user, "avatar_storage_key", None)
    if not key:
        raise HTTPException(status_code=404, detail="AVATAR_NOT_SET")
    storage = LocalFileStorage(root_dir=settings.local_storage_dir)
    path = storage.resolve(key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="AVATAR_FILE_MISSING")
    return FileResponse(path=str(path), filename=os.path.basename(path))
