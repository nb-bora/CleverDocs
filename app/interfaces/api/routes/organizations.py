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
from app.interfaces.api.deps import TenantContext, UserContext, get_db, get_tenant_context, get_user_context


router = APIRouter(prefix="/v1/organizations", tags=["organizations"])

_ADMIN_ROLES = {"owner", "admin"}


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


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant


def _require_admin(tenant: TenantContext) -> None:
    if (tenant.role or "") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")


@router.get("", response_model=list[OrganizationOut])
def list_my_organizations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[UserContext, Depends(get_user_context)],
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
    user: Annotated[UserContext, Depends(get_user_context)],
) -> OrganizationOut:
    org = OrganizationModel(id=str(uuid.uuid4()), name=body.name, status="active")
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
    _require_admin(tenant)
    org = db.get(OrganizationModel, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
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
        role=body.role,
        status="active",
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
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
    if body.role is not None:
        m.role = body.role
    if body.status is not None:
        m.status = body.status
    db.add(m)
    db.commit()
    db.refresh(m)
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
    # Soft delete for MVP: set a terminal status.
    m.status = "removed"
    db.add(m)
    db.commit()
    return {"status": "removed", "membership_id": m.id}
