"""Bootstrap routes (MVP only).

These endpoints exist to create Organizations/Users/Memberships quickly while auth is not implemented.
They will be removed or protected in Phase 7+.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.db.orm.models.organization_model import OrganizationModel
from app.infrastructure.db.orm.models.user_model import UserModel
from app.interfaces.api.deps import Settings, get_db, get_settings


router = APIRouter(prefix="/v1/bootstrap", tags=["bootstrap"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    user_email: EmailStr
    user_display_name: str | None = Field(default=None, max_length=255)
    role: str = Field(default="owner", min_length=1, max_length=32)
    password: str = Field(min_length=8, max_length=256)


class BootstrapResponse(BaseModel):
    organization_id: str
    user_id: str
    membership_id: str


@router.post("", response_model=BootstrapResponse)
def bootstrap(
    body: BootstrapRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BootstrapResponse:
    if settings.app_env != "dev":
        raise HTTPException(status_code=403, detail="BOOTSTRAP_DISABLED")
    org_id = str(uuid.uuid4())
    user = UserModel(
        id=str(uuid.uuid4()),
        email=str(body.user_email).lower(),
        display_name=body.user_display_name,
        password_hash=pwd_context.hash(body.password),
        status="active",
    )
    org = OrganizationModel(id=org_id, name=body.organization_name, owner_user_id=user.id, status="active")
    membership = MembershipModel(
        id=str(uuid.uuid4()),
        user_id=user.id,
        organization_id=org_id,
        role=body.role,
        status="active",
    )
    db.add_all([org, user, membership])
    db.commit()
    return BootstrapResponse(organization_id=org.id, user_id=user.id, membership_id=membership.id)

