"""Dependency injection wiring.

On garde ça simple pour le MVP: Settings + DB session + storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from pathlib import Path
from typing import Generator

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.db.orm.models.organization_model import OrganizationModel
from app.infrastructure.db.orm.models.refresh_token_model import RefreshTokenModel
from app.infrastructure.db.orm.models.user_model import UserModel


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_name: str = "CleverDocs"
    app_log_level: str = "INFO"

    database_url: str = "sqlite:///./cleverdocs.db"

    storage_backend: str = "local"
    local_storage_dir: str = "storage"

    opensearch_url: str = "http://localhost:9200"
    opensearch_index_prefix: str = "cleverdocs"

    # OCR (EasyOCR)
    ocr_langs: str = "fr"  # comma-separated (e.g. "fr,en")
    ocr_gpu: bool = False
    ocr_pdf_max_pages: int = 20
    ocr_pdf_zoom: float = 2.0

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "cleverdocs"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 30 * 24 * 3600


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass(frozen=True)
class LocalStorage:
    root_dir: Path

    def ensure(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)


def get_local_storage(settings: Settings = None) -> LocalStorage:
    s = settings or get_settings()
    root_dir = Path(s.local_storage_dir)
    return LocalStorage(root_dir=root_dir)


@dataclass(frozen=True)
class TenantContext:
    organization_id: str
    user_id: str
    role: str | None = None


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str


# Simple Bearer token auth (no OAuth2 password/scopes UI in Swagger).
bearer_scheme = HTTPBearer(auto_error=False)


def _now() -> datetime:
    return datetime.now(UTC)


def _create_access_token(*, settings: Settings, user_id: str) -> tuple[str, int]:
    ttl = max(60, int(settings.access_token_ttl_seconds))
    now = _now()
    payload = {
        "iss": settings.jwt_issuer,
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, ttl


def _hash_refresh_token(token: str) -> str:
    # SHA-256 hex is enough here (token itself is high-entropy random).
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _ensure_utc(dt: datetime) -> datetime:
    # SQLite often returns naive datetimes even when timezone=True.
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def issue_refresh_token(*, settings: Settings, db: Session, user_id: str) -> str:
    raw = secrets.token_urlsafe(48)
    ttl = max(3600, int(settings.refresh_token_ttl_seconds))
    expires_at = _now() + timedelta(seconds=ttl)
    rt = RefreshTokenModel(
        user_id=user_id,
        token_hash=_hash_refresh_token(raw),
        expires_at=expires_at,
        revoked_at=None,
    )
    db.add(rt)
    db.commit()
    return raw


def rotate_refresh_token(*, settings: Settings, db: Session, raw_refresh_token: str) -> str:
    token_hash = _hash_refresh_token(raw_refresh_token)
    rt = db.execute(
        select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
    ).scalar_one_or_none()
    if rt is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if rt.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    if _ensure_utc(rt.expires_at) <= _now():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    rt.revoked_at = _now()
    db.add(rt)
    db.commit()
    return issue_refresh_token(settings=settings, db=db, user_id=rt.user_id)


def revoke_refresh_token(*, db: Session, raw_refresh_token: str) -> None:
    token_hash = _hash_refresh_token(raw_refresh_token)
    rt = db.execute(
        select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
    ).scalar_one_or_none()
    if rt is None:
        return
    if rt.revoked_at is None:
        rt.revoked_at = _now()
        db.add(rt)
        db.commit()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None or (credentials.scheme or "").lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require_sub": True, "require_exp": True, "require_iat": True},
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=403, detail="User disabled")
    return CurrentUser(user_id=user.id, email=user.email)


def get_tenant_context(
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    # Tenant selection: allow X-Org-Id but verify membership. If absent, pick the first active membership.
    if x_org_id:
        m = db.execute(
            select(MembershipModel)
            .where(MembershipModel.organization_id == x_org_id)
            .where(MembershipModel.user_id == current_user.user_id)
            .where(MembershipModel.status == "active")
        ).scalar_one_or_none()
        if m is None:
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        org_id = x_org_id
        role = m.role
    else:
        m = db.execute(
            select(MembershipModel)
            .where(MembershipModel.user_id == current_user.user_id)
            .where(MembershipModel.status == "active")
            .order_by(MembershipModel.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        if m is None:
            raise HTTPException(status_code=403, detail="No active organization membership")
        org_id = m.organization_id
        role = m.role

    org = db.get(OrganizationModel, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if getattr(org, "status", "active") != "active":
        raise HTTPException(status_code=403, detail="Organization suspended")

    return TenantContext(organization_id=org_id, user_id=current_user.user_id, role=role)


@dataclass(frozen=True)
class UserContext:
    user_id: str


def get_user_context(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> UserContext:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-Id header")
    user = db.get(UserModel, x_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=403, detail="User disabled")
    return UserContext(user_id=x_user_id)

