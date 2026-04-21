"""User management routes (MVP).

Important: auth is still header-based (X-Org-Id / X-User-Id). These endpoints are meant
for internal/admin use until Phase 7 introduces real authentication.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.db.orm.models.user_model import UserModel
from app.interfaces.api.deps import TenantContext, get_db, get_tenant_context
from app.interfaces.api.schemas.users import CreateUserRequest, UpdateUserRequest, UserOut


router = APIRouter(prefix="/v1/users", tags=["users"])

_ADMIN_ROLES = {"owner", "admin"}


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant


def _require_admin(tenant: TenantContext) -> None:
    if (tenant.role or "") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")


@router.get("", response_model=list[UserOut])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> list[UserOut]:
    _require_admin(tenant)
    stmt = (
        select(UserModel)
        .join(MembershipModel, MembershipModel.user_id == UserModel.id)
        .where(MembershipModel.organization_id == tenant.organization_id)
        .where(MembershipModel.status == "active")
        .order_by(UserModel.created_at.desc())
    )
    items = db.execute(stmt).scalars().all()
    return [UserOut.model_validate(u, from_attributes=True) for u in items]


@router.post("", response_model=UserOut)
def create_user(
    body: CreateUserRequest,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> UserOut:
    _require_admin(tenant)

    email = str(body.email).lower()
    existing = db.execute(select(UserModel).where(UserModel.email == email)).scalar_one_or_none()
    if existing is not None:
        return UserOut.model_validate(existing, from_attributes=True)

    user = UserModel(
        id=str(uuid.uuid4()),
        email=email,
        display_name=body.display_name,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user, from_attributes=True)


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> UserOut:
    _require_admin(tenant)
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user, from_attributes=True)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UpdateUserRequest,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> UserOut:
    _require_admin(tenant)
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.email is not None:
        email = str(body.email).lower()
        other = db.execute(select(UserModel).where(UserModel.email == email)).scalar_one_or_none()
        if other is not None and other.id != user.id:
            raise HTTPException(status_code=409, detail="Email already in use")
        user.email = email
    if body.display_name is not None:
        user.display_name = body.display_name

    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/{user_id}/disable", response_model=UserOut)
def disable_user(
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> UserOut:
    _require_admin(tenant)
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "disabled"
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/{user_id}/enable", response_model=UserOut)
def enable_user(
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> UserOut:
    _require_admin(tenant)
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "active"
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user, from_attributes=True)


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> dict:
    _require_admin(tenant)
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Soft delete for MVP: disable account.
    user.status = "disabled"
    db.add(user)
    db.commit()
    return {"status": "disabled", "user_id": user.id}

