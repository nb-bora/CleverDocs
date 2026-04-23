"""User routes consumed by the web app (MVP)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.user_model import UserModel
from app.domain.identity.services.username_policy import validate_username_github_like
from app.interfaces.api.deps import CurrentUser, TenantContext, get_current_user, get_db, get_tenant_context
from app.interfaces.api.schemas.users import UpdateUserRequest, UserOut
from app.domain.identity.services.authorization_policy import AuthorizationPolicy, TenantContext as DomainTenantContext


router = APIRouter(prefix="/v1/users", tags=["users"])

_authz = AuthorizationPolicy()


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant


def _require_admin(tenant: TenantContext) -> None:
    if not _authz.is_admin(
        DomainTenantContext(
            organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role
        )
    ):
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")


@router.get("/username_available")
def username_available(
    username: Annotated[str, Query(min_length=1, max_length=39)],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """Check if a username can be claimed by current user."""
    try:
        uname = validate_username_github_like(str(username))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    other = db.execute(select(UserModel).where(UserModel.username == uname)).scalar_one_or_none()
    if other is None:
        return {"available": True}
    return {"available": other.id == current_user.user_id}


@router.get("/directory", response_model=list[UserOut])
def directory(
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(_get_tenant)] = None,
) -> list[UserOut]:
    """Typeahead directory used by the invitations UI.

    We intentionally allow searching *global active users* (by email/username/display_name)
    so an admin can invite an existing user who is not yet a member of the current org.
    """
    _require_admin(tenant)
    stmt = select(UserModel).where(UserModel.status == "active")
    if q and str(q).strip():
        needle = f"%{str(q).strip().lower()}%"
        stmt = stmt.where(
            (UserModel.email.ilike(needle))
            | (UserModel.username.ilike(needle))
            | (UserModel.display_name.ilike(needle))
        )
    items = db.execute(stmt.order_by(UserModel.created_at.desc()).limit(int(limit))).scalars().all()
    return [UserOut.model_validate(u, from_attributes=True) for u in items]


@router.patch("/me", response_model=UserOut)
def update_me(
    body: UpdateUserRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> UserOut:
    user = db.get(UserModel, current_user.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if body.username is not None:
        try:
            uname = validate_username_github_like(str(body.username))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        other = db.execute(select(UserModel).where(UserModel.username == uname)).scalar_one_or_none()
        if other is not None and other.id != user.id:
            raise HTTPException(status_code=409, detail="USERNAME_TAKEN")
        user.username = uname
    if body.display_name is not None:
        user.display_name = body.display_name
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user, from_attributes=True)