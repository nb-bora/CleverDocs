"""Invitation routes (create/accept/revoke)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.identity.services.authorization_policy import AuthorizationPolicy, TenantContext as DomainTenantContext
from app.infrastructure.db.orm.models.invitation_model import InvitationModel
from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.db.orm.models.user_model import UserModel
from app.interfaces.api.deps import Settings, TenantContext, get_db, get_settings, get_tenant_context
from app.interfaces.api.schemas.invitations import (
    AcceptInvitationRequest,
    CreateInvitationRequest,
    CreateInvitationResponse,
    InvitationOut,
)


router = APIRouter(prefix="/v1/invitations", tags=["invitations"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_authz = AuthorizationPolicy()
_VALID_ROLES = {"admin", "member", "reader"}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("", response_model=CreateInvitationResponse)
def create_invitation(
    body: CreateInvitationRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
) -> InvitationOut:
    if not _authz.is_admin(
        DomainTenantContext(
            organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role
        )
    ):
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="INVALID_ROLE")

    raw = secrets.token_urlsafe(48)
    inv = InvitationModel(
        id=str(uuid.uuid4()),
        organization_id=tenant.organization_id,
        email=str(body.email).lower(),
        role=body.role,
        token_hash=_hash_token(raw),
        expires_at=_now() + timedelta(days=7),
        accepted_at=None,
        revoked_at=None,
        created_by_user_id=tenant.user_id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    out = InvitationOut(
        id=inv.id,
        organization_id=inv.organization_id,
        email=inv.email,
        role=inv.role,
        expires_at=inv.expires_at.isoformat(),
        accepted_at=inv.accepted_at.isoformat() if inv.accepted_at else None,
        revoked_at=inv.revoked_at.isoformat() if inv.revoked_at else None,
    )
    return CreateInvitationResponse(invitation=out, token=raw)


@router.post("/accept")
def accept_invitation(
    body: AcceptInvitationRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    token_hash = _hash_token(body.token)
    inv = db.execute(select(InvitationModel).where(InvitationModel.token_hash == token_hash)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Invitation revoked")
    if inv.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Invitation already accepted")
    if inv.expires_at <= _now():
        raise HTTPException(status_code=409, detail="Invitation expired")

    email = inv.email.lower()
    user = db.execute(select(UserModel).where(UserModel.email == email)).scalar_one_or_none()
    if user is None:
        user = UserModel(
            id=str(uuid.uuid4()),
            email=email,
            display_name=body.display_name,
            password_hash=pwd_context.hash(body.password),
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.password_hash:
        user.password_hash = pwd_context.hash(body.password)
        if body.display_name is not None:
            user.display_name = body.display_name
        db.add(user)
        db.commit()
        db.refresh(user)

    m = db.execute(
        select(MembershipModel)
        .where(MembershipModel.organization_id == inv.organization_id)
        .where(MembershipModel.user_id == user.id)
    ).scalar_one_or_none()
    if m is None:
        m = MembershipModel(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=inv.organization_id,
            role=inv.role,
            status="active",
        )
        db.add(m)
    else:
        if m.role != "owner":
            m.role = inv.role
        m.status = "active"
        db.add(m)

    inv.accepted_at = _now()
    db.add(inv)
    db.commit()
    return {"status": "ok", "organization_id": inv.organization_id, "user_id": user.id}


@router.post("/{invitation_id}/revoke")
def revoke_invitation(
    invitation_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
) -> dict:
    if not _authz.is_admin(
        DomainTenantContext(
            organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role
        )
    ):
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")
    inv = db.get(InvitationModel, invitation_id)
    if inv is None or inv.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.revoked_at is None:
        inv.revoked_at = _now()
        db.add(inv)
        db.commit()
    return {"status": "revoked", "invitation_id": inv.id}

