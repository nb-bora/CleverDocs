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


class MembershipOut(BaseModel):
    id: str
    user_id: str
    organization_id: str
    role: str
    status: str


class AddMemberRequest(BaseModel):
    user_email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="member", min_length=1, max_length=32)


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
