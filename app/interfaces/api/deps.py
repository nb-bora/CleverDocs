"""Dependency injection wiring.

On garde ça simple pour le MVP: Settings + DB session + storage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from fastapi import Depends, Header, HTTPException

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session

from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.db.orm.models.organization_model import OrganizationModel
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
    user_id: str | None
    role: str | None = None


def get_tenant_context(
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> TenantContext:
    """MVP tenant resolution.

    - Requires `X-Org-Id` (strict isolation).
    - Optionally accepts `X-User-Id` and verifies membership if provided.
    """
    if not x_org_id:
        raise HTTPException(status_code=400, detail="Missing X-Org-Id header")

    org = db.get(OrganizationModel, x_org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if getattr(org, "status", "active") != "active":
        raise HTTPException(status_code=403, detail="Organization suspended")

    role: str | None = None
    if x_user_id:
        user = db.get(UserModel, x_user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        m = (
            db.query(MembershipModel)
            .filter(MembershipModel.organization_id == x_org_id)
            .filter(MembershipModel.user_id == x_user_id)
            .filter(MembershipModel.status == "active")
            .first()
        )
        if m is None:
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        role = getattr(m, "role", None)

    return TenantContext(organization_id=x_org_id, user_id=x_user_id, role=role)


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

