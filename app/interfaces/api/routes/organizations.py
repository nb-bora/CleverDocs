"""Organization management routes (MVP).

Auth is still header-based (X-Org-Id / X-User-Id). These endpoints are minimal and
mainly support tenant/membership administration before Phase 7.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.db.orm.models.organization_model import OrganizationModel
from app.infrastructure.db.orm.models.user_model import UserModel
from app.interfaces.api.deps import CurrentUser, TenantContext, get_current_user, get_db, get_tenant_context
from app.domain.identity.services.authorization_policy import AuthorizationPolicy, TenantContext as DomainTenantContext
from app.infrastructure.audit.audit_logger import AuditEvent, AuditLogger
from app.infrastructure.messaging.outbox.outbox_model import OutboxEvent, enqueue_outbox_event


router = APIRouter(prefix="/v1/organizations", tags=["organizations"])

_authz = AuthorizationPolicy()
_VALID_ROLES = {"owner", "admin", "member", "reader"}


class OrganizationOut(BaseModel):
    id: str
    name: str
    status: str


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class MembershipOut(BaseModel):
    id: str
    user_id: str
    organization_id: str
    role: str
    status: str


class AddMemberRequest(BaseModel):
    user_email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="member", min_length=1, max_length=32)


class UpdateMemberRequest(BaseModel):
    role: str | None = Field(default=None, min_length=1, max_length=32)
    status: str | None = Field(default=None, min_length=1, max_length=32)

class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: str = Field(min_length=1, max_length=36)


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant


def _require_admin(tenant: TenantContext) -> None:
    if not _authz.is_admin(
        DomainTenantContext(
            organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role
        )
    ):
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")


def _require_owner(tenant: TenantContext) -> None:
    if not _authz.is_owner(
        DomainTenantContext(
            organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role
        )
    ):
        raise HTTPException(status_code=403, detail="OWNER_REQUIRED")


def _get_active_owner_membership(db: Session, organization_id: str) -> MembershipModel | None:
    return db.execute(
        select(MembershipModel)
        .where(MembershipModel.organization_id == organization_id)
        .where(MembershipModel.role == "owner")
        .where(MembershipModel.status == "active")
        .order_by(MembershipModel.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()


@router.get("", response_model=list[OrganizationOut])
def list_my_organizations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[OrganizationOut]:
    stmt = (
        select(OrganizationModel)
        .join(MembershipModel, MembershipModel.organization_id == OrganizationModel.id)
        .where(MembershipModel.user_id == user.user_id)
        .where(MembershipModel.status == "active")
        .order_by(OrganizationModel.created_at.desc())
    )
    items = db.execute(stmt).scalars().all()
    return [OrganizationOut.model_validate(o, from_attributes=True) for o in items]


@router.post("", response_model=OrganizationOut)
def create_organization(
    body: CreateOrganizationRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> OrganizationOut:
    org = OrganizationModel(id=str(uuid.uuid4()), name=body.name, owner_user_id=user.user_id, status="active")
    db.add(org)
    db.add(
        MembershipModel(
            id=str(uuid.uuid4()),
            user_id=user.user_id,
            organization_id=org.id,
            role="owner",
            status="active",
        )
    )
    db.commit()
    db.refresh(org)
    AuditLogger(db).log(
        AuditEvent(
            organization_id=org.id,
            actor_user_id=user.user_id,
            action="ORG_CREATE",
            target_type="organization",
            target_id=org.id,
            detail={"name": org.name},
        )
    )
    enqueue_outbox_event(
        db=db,
        ev=OutboxEvent(
            organization_id=org.id,
            event_type="ORG_CREATED",
            payload={"organization_id": org.id, "owner_user_id": user.user_id, "name": org.name},
        ),
    )
    db.commit()
    return OrganizationOut.model_validate(org, from_attributes=True)


@router.get("/{organization_id}", response_model=OrganizationOut)
def get_organization(
    organization_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> OrganizationOut:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    org = db.get(OrganizationModel, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationOut.model_validate(org, from_attributes=True)


@router.patch("/{organization_id}", response_model=OrganizationOut)
def update_organization(
    organization_id: str,
    body: UpdateOrganizationRequest,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> OrganizationOut:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)
    org = db.get(OrganizationModel, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if body.name is not None:
        org.name = body.name
    db.add(org)
    db.commit()
    db.refresh(org)
    return OrganizationOut.model_validate(org, from_attributes=True)


@router.post("/{organization_id}/suspend", response_model=OrganizationOut)
def suspend_organization(
    organization_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> OrganizationOut:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)
    org = db.get(OrganizationModel, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.status = "suspended"
    db.add(org)
    db.commit()
    db.refresh(org)
    return OrganizationOut.model_validate(org, from_attributes=True)


@router.post("/{organization_id}/activate", response_model=OrganizationOut)
def activate_organization(
    organization_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> OrganizationOut:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)
    org = db.get(OrganizationModel, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.status = "active"
    db.add(org)
    db.commit()
    db.refresh(org)
    return OrganizationOut.model_validate(org, from_attributes=True)


@router.delete("/{organization_id}")
def delete_organization(
    organization_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> dict:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_owner(tenant)
    org = db.get(OrganizationModel, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.owner_user_id != tenant.user_id:
        raise HTTPException(status_code=403, detail="OWNER_REQUIRED")
    # Soft delete in MVP: mark suspended.
    org.status = "suspended"
    db.add(org)
    db.commit()
    return {"status": "suspended", "organization_id": org.id}


@router.get("/{organization_id}/members", response_model=list[MembershipOut])
def list_members(
    organization_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> list[MembershipOut]:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)
    stmt = (
        select(MembershipModel)
        .where(MembershipModel.organization_id == organization_id)
        .order_by(MembershipModel.created_at.desc())
    )
    items = db.execute(stmt).scalars().all()
    return [MembershipOut.model_validate(m, from_attributes=True) for m in items]


@router.post("/{organization_id}/members", response_model=MembershipOut)
def add_member(
    organization_id: str,
    body: AddMemberRequest,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> MembershipOut:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)

    org = db.get(OrganizationModel, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    email = body.user_email.strip().lower()
    user = db.execute(select(UserModel).where(UserModel.email == email)).scalar_one_or_none()
    if user is None:
        user = UserModel(id=str(uuid.uuid4()), email=email, display_name=None, status="active")
        db.add(user)
        db.commit()
        db.refresh(user)

    existing = db.execute(
        select(MembershipModel)
        .where(MembershipModel.organization_id == organization_id)
        .where(MembershipModel.user_id == user.id)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.role == "owner":
            raise HTTPException(status_code=409, detail="OWNER_MEMBERSHIP_IMMUTABLE")
        if body.role not in _VALID_ROLES or body.role == "owner":
            raise HTTPException(status_code=400, detail="INVALID_ROLE")
        existing.role = body.role
        existing.status = "active"
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return MembershipOut.model_validate(existing, from_attributes=True)

    membership = MembershipModel(
        id=str(uuid.uuid4()),
        user_id=user.id,
        organization_id=organization_id,
        role=("member" if body.role not in _VALID_ROLES or body.role == "owner" else body.role),
        status="active",
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    AuditLogger(db).log(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=tenant.user_id,
            action="MEMBER_ADD",
            target_type="membership",
            target_id=membership.id,
            detail={"user_id": membership.user_id, "role": membership.role},
        )
    )
    db.commit()
    return MembershipOut.model_validate(membership, from_attributes=True)


@router.patch("/{organization_id}/members/{membership_id}", response_model=MembershipOut)
def update_member(
    organization_id: str,
    membership_id: str,
    body: UpdateMemberRequest,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> MembershipOut:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)
    m = db.get(MembershipModel, membership_id)
    if m is None or m.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    if m.role == "owner":
        raise HTTPException(status_code=409, detail="OWNER_MEMBERSHIP_IMMUTABLE")
    if body.role is not None:
        if body.role not in _VALID_ROLES or body.role == "owner":
            raise HTTPException(status_code=400, detail="INVALID_ROLE")
        m.role = body.role
    if body.status is not None:
        m.status = body.status
    db.add(m)
    db.commit()
    db.refresh(m)
    AuditLogger(db).log(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=tenant.user_id,
            action="MEMBER_UPDATE",
            target_type="membership",
            target_id=m.id,
            detail={"role": m.role, "status": m.status},
        )
    )
    db.commit()
    return MembershipOut.model_validate(m, from_attributes=True)


@router.post("/{organization_id}/members/{membership_id}/suspend", response_model=MembershipOut)
def suspend_member(
    organization_id: str,
    membership_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> MembershipOut:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)
    m = db.get(MembershipModel, membership_id)
    if m is None or m.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    if m.role == "owner":
        raise HTTPException(status_code=409, detail="OWNER_MEMBERSHIP_IMMUTABLE")
    m.status = "suspended"
    db.add(m)
    db.commit()
    db.refresh(m)
    return MembershipOut.model_validate(m, from_attributes=True)


@router.post("/{organization_id}/members/{membership_id}/activate", response_model=MembershipOut)
def activate_member(
    organization_id: str,
    membership_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> MembershipOut:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)
    m = db.get(MembershipModel, membership_id)
    if m is None or m.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    m.status = "active"
    db.add(m)
    db.commit()
    db.refresh(m)
    return MembershipOut.model_validate(m, from_attributes=True)


@router.delete("/{organization_id}/members/{membership_id}")
def remove_member(
    organization_id: str,
    membership_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> dict:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_admin(tenant)
    m = db.get(MembershipModel, membership_id)
    if m is None or m.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    if m.role == "owner":
        raise HTTPException(status_code=409, detail="OWNER_MEMBERSHIP_IMMUTABLE")
    # Soft delete for MVP: set a terminal status.
    m.status = "removed"
    db.add(m)
    db.commit()
    return {"status": "removed", "membership_id": m.id}


@router.post("/{organization_id}/transfer_ownership")
def transfer_ownership(
    organization_id: str,
    body: TransferOwnershipRequest,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> dict:
    if tenant.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="CROSS_TENANT_FORBIDDEN")
    _require_owner(tenant)

    org = db.get(OrganizationModel, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.owner_user_id != tenant.user_id:
        raise HTTPException(status_code=403, detail="OWNER_REQUIRED")

    new_owner = db.execute(
        select(MembershipModel)
        .where(MembershipModel.organization_id == organization_id)
        .where(MembershipModel.user_id == body.new_owner_user_id)
        .where(MembershipModel.status == "active")
        .limit(1)
    ).scalar_one_or_none()
    if new_owner is None:
        raise HTTPException(status_code=404, detail="New owner must be an active member")
    if new_owner.role == "owner":
        return {"status": "ok", "organization_id": organization_id, "new_owner_user_id": new_owner.user_id}

    # Transfer: promote new owner, demote old owner to admin.
    new_owner.role = "owner"
    org.owner_user_id = new_owner.user_id
    # Demote old owner membership (if exists) to admin.
    old_owner_m = _get_active_owner_membership(db, organization_id)
    if old_owner_m is not None and old_owner_m.user_id != new_owner.user_id:
        old_owner_m.role = "admin"
        db.add(old_owner_m)
    db.add_all([new_owner, org])
    db.commit()
    AuditLogger(db).log(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=tenant.user_id,
            action="ORG_TRANSFER_OWNERSHIP",
            target_type="organization",
            target_id=organization_id,
            detail={"new_owner_user_id": new_owner.user_id},
        )
    )
    db.commit()
    return {
        "status": "ok",
        "organization_id": organization_id,
        "old_owner_user_id": tenant.user_id,
        "new_owner_user_id": new_owner.user_id,
    }
