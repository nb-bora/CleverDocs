"""Invitation routes (create/accept/revoke)."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.identity.services.authorization_policy import AuthorizationPolicy, TenantContext as DomainTenantContext
from app.infrastructure.audit.audit_logger import AuditEvent, AuditLogger
from app.infrastructure.db.orm.models.invitation_model import InvitationModel
from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.db.orm.models.organization_model import OrganizationModel
from app.infrastructure.db.orm.models.audit_log_model import AuditLogModel
from app.infrastructure.db.orm.models.user_model import UserModel
from app.infrastructure.messaging.outbox.outbox_model import OutboxEvent, enqueue_outbox_event
from app.interfaces.api.deps import CurrentUser, Settings, TenantContext, get_current_user, get_db, get_settings, get_tenant_context
from app.interfaces.api.schemas.invitations import (
    AcceptInvitationRequest,
    AcceptInvitationLoggedInRequest,
    DeclineInvitationRequest,
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


def _ensure_utc(dt: datetime) -> datetime:
    # SQLite often returns naive datetimes even when timezone=True.
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _status(inv: InvitationModel) -> str:
    if inv.revoked_at is not None:
        return "revoked"
    if inv.accepted_at is not None:
        return "accepted"
    if getattr(inv, "declined_at", None) is not None:
        return "declined"
    if _ensure_utc(inv.expires_at) <= _now():
        return "expired"
    return "pending"


def _accept_url(raw_token: str) -> str:
    return f"/accept-invitation?token={raw_token}"


def _public_accept_url(*, settings: Settings, raw_token: str) -> str:
    base = (getattr(settings, "app_public_base_url", "") or "").rstrip("/")
    return f"{base}{_accept_url(raw_token)}" if base else _accept_url(raw_token)


def _email_queue_stats(*, db: Session, organization_id: str, invitation_id: str) -> tuple[datetime | None, int]:
    """Return (last_sent_at, count_last_24h) based on audit logs."""
    now = _now()
    since = now - timedelta(days=1)
    stmt = (
        select(AuditLogModel.created_at)
        .where(AuditLogModel.organization_id == organization_id)
        .where(AuditLogModel.action == "INVITATION_EMAIL_QUEUED")
        .where(AuditLogModel.target_type == "invitation")
        .where(AuditLogModel.target_id == invitation_id)
        .where(AuditLogModel.created_at >= since)
        .order_by(AuditLogModel.created_at.desc())
    )
    rows = db.execute(stmt).all()
    if not rows:
        return None, 0
    last = rows[0][0]
    return _ensure_utc(last), len(rows)


@router.get("", response_model=list[InvitationOut])
def list_invitations(
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
) -> list[InvitationOut]:
    is_admin = _authz.is_admin(
        DomainTenantContext(organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role)
    )

    stmt = (
        select(InvitationModel)
        .where(InvitationModel.organization_id == tenant.organization_id)
        .order_by(InvitationModel.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if not is_admin:
        # Non-admin users can still list invitations *addressed to them* within the current org.
        # This is required so any connected user can see their pending invites without admin rights.
        me_email = str(current_user.email).lower()
        stmt = stmt.where(
            (InvitationModel.email == me_email)
            | (InvitationModel.invited_user_id == current_user.user_id)
            | (InvitationModel.provisioned_user_id == current_user.user_id)
        )
    items = db.execute(stmt).scalars().all()
    org = db.get(OrganizationModel, tenant.organization_id)
    org_name = getattr(org, "name", None) if org else None

    out: list[InvitationOut] = []
    for inv in items:
        st = _status(inv)
        if status and st != status:
            continue
        out.append(
            InvitationOut(
                id=inv.id,
                organization_id=inv.organization_id,
                organization_name=org_name,
                email=inv.email,
                role=inv.role,
                status=st,
                expires_at=inv.expires_at.isoformat(),
                accepted_at=inv.accepted_at.isoformat() if inv.accepted_at else None,
                revoked_at=inv.revoked_at.isoformat() if inv.revoked_at else None,
                created_by_user_id=inv.created_by_user_id,
                created_at=inv.created_at.isoformat() if inv.created_at else None,
            )
        )
    return out


@router.get("/received", response_model=list[InvitationOut])
def list_received_invitations(
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
) -> list[InvitationOut]:
    """List invitations received by the current user across all organizations.

    This endpoint is intentionally NOT org-scoped: a user can receive invitations to orgs
    they are not yet a member of.
    """
    me_email = str(current_user.email).lower()
    stmt = (
        select(InvitationModel, OrganizationModel.name)
        .join(OrganizationModel, OrganizationModel.id == InvitationModel.organization_id)
        .where(
            (InvitationModel.email == me_email)
            | (InvitationModel.invited_user_id == current_user.user_id)
            | (InvitationModel.provisioned_user_id == current_user.user_id)
        )
        .order_by(InvitationModel.created_at.desc())
    )
    rows = db.execute(stmt).all()

    filtered: list[InvitationOut] = []
    for inv, org_name in rows:
        st = _status(inv)
        if status and st != status:
            continue
        filtered.append(
            InvitationOut(
                id=inv.id,
                organization_id=inv.organization_id,
                organization_name=str(org_name) if org_name is not None else None,
                email=inv.email,
                role=inv.role,
                status=st,
                expires_at=inv.expires_at.isoformat(),
                accepted_at=inv.accepted_at.isoformat() if inv.accepted_at else None,
                revoked_at=inv.revoked_at.isoformat() if inv.revoked_at else None,
                created_by_user_id=inv.created_by_user_id,
                created_at=inv.created_at.isoformat() if inv.created_at else None,
            )
        )

    start = int(offset)
    end = start + int(limit)
    return filtered[start:end]


@router.post("/{invitation_id}/token", response_model=CreateInvitationResponse)
def issue_receiver_token(
    invitation_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CreateInvitationResponse:
    """Issue a fresh accept token for the receiver (in-app actions).

    Only the invited user (by email/user link) can request a token, and only for pending invitations.
    """
    inv = db.get(InvitationModel, invitation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="INVITATION_NOT_FOUND")

    me_email = str(current_user.email).lower()
    is_mine = (
        str(getattr(inv, "email", "")).lower() == me_email
        or getattr(inv, "invited_user_id", None) == current_user.user_id
        or getattr(inv, "provisioned_user_id", None) == current_user.user_id
    )
    if not is_mine:
        raise HTTPException(status_code=403, detail="INVITATION_NOT_FOR_YOU")
    if inv.revoked_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_REVOKED")
    if inv.accepted_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_ALREADY_ACCEPTED")
    if getattr(inv, "declined_at", None) is not None:
        raise HTTPException(status_code=409, detail="INVITATION_DECLINED")
    if _ensure_utc(inv.expires_at) <= _now():
        raise HTTPException(status_code=409, detail="INVITATION_EXPIRED")

    raw = secrets.token_urlsafe(48)
    inv.token_hash = _hash_token(raw)
    inv.expires_at = _now() + timedelta(days=7)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    org = db.get(OrganizationModel, inv.organization_id)
    out = InvitationOut(
        id=inv.id,
        organization_id=inv.organization_id,
        organization_name=getattr(org, "name", None) if org else None,
        email=inv.email,
        role=inv.role,
        status=_status(inv),
        expires_at=inv.expires_at.isoformat(),
        accepted_at=inv.accepted_at.isoformat() if inv.accepted_at else None,
        revoked_at=inv.revoked_at.isoformat() if inv.revoked_at else None,
        created_by_user_id=inv.created_by_user_id,
        created_at=inv.created_at.isoformat() if inv.created_at else None,
    )
    return CreateInvitationResponse(invitation=out, accept_url=_accept_url(raw))

@router.post("", response_model=CreateInvitationResponse)
def create_invitation(
    body: CreateInvitationRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CreateInvitationResponse:
    if not _authz.is_admin(
        DomainTenantContext(
            organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role
        )
    ):
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="INVALID_ROLE")

    email = str(body.email).lower()
    if email == str(current_user.email).lower():
        raise HTTPException(status_code=400, detail="SELF_INVITE_FORBIDDEN")

    # If user exists, link invitation to that user. Otherwise provision a pre-user.
    existing_user = db.execute(select(UserModel).where(UserModel.email == email)).scalar_one_or_none()
    provisioned_user_id: str | None = None
    provisioned_user_was_created = False
    invited_user_id: str | None = None
    if existing_user is not None:
        invited_user_id = existing_user.id
    else:
        # Provision a pre-user without password (activation via invitation accept flow).
        u = UserModel(
            id=str(uuid.uuid4()),
            email=email,
            display_name=None,
            password_hash=None,
            status="invited",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        provisioned_user_id = u.id
        provisioned_user_was_created = True
    # Prevent multiple pending invitations to the same email.
    existing = db.execute(
        select(InvitationModel)
        .where(InvitationModel.organization_id == tenant.organization_id)
        .where(InvitationModel.email == email)
        .order_by(InvitationModel.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None and _status(existing) == "pending":
        raise HTTPException(status_code=409, detail="INVITATION_ALREADY_PENDING")

    raw = secrets.token_urlsafe(48)
    inv = InvitationModel(
        id=str(uuid.uuid4()),
        organization_id=tenant.organization_id,
        email=email,
        role=body.role,
        token_hash=_hash_token(raw),
        expires_at=_now() + timedelta(days=7),
        accepted_at=None,
        revoked_at=None,
        declined_at=None,
        invited_user_id=invited_user_id,
        provisioned_user_id=provisioned_user_id,
        provisioned_user_was_created=provisioned_user_was_created,
        created_by_user_id=tenant.user_id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    org = db.get(OrganizationModel, tenant.organization_id)
    out = InvitationOut(
        id=inv.id,
        organization_id=inv.organization_id,
        organization_name=getattr(org, "name", None) if org else None,
        email=inv.email,
        role=inv.role,
        status=_status(inv),
        expires_at=inv.expires_at.isoformat(),
        accepted_at=inv.accepted_at.isoformat() if inv.accepted_at else None,
        revoked_at=inv.revoked_at.isoformat() if inv.revoked_at else None,
        created_by_user_id=inv.created_by_user_id,
        created_at=inv.created_at.isoformat() if inv.created_at else None,
    )

    # Queue email notification (outbox) + audit.
    inviter = db.get(UserModel, tenant.user_id) if tenant.user_id else None
    payload = {
        "kind": "created",
        "invitation_id": inv.id,
        "organization_id": inv.organization_id,
        "organization_name": getattr(org, "name", "") if org else "",
        "email": inv.email,
        "role": inv.role,
        "accept_url": _public_accept_url(settings=settings, raw_token=raw),
        "expires_at": inv.expires_at.isoformat(),
        "created_by_user_id": inv.created_by_user_id,
        "inviter_display_name": getattr(inviter, "display_name", None) if inviter else None,
    }
    enqueue_outbox_event(
        db=db,
        ev=OutboxEvent(
            organization_id=inv.organization_id,
            event_type="INVITATION_EMAIL",
            payload=payload,
        ),
    )
    AuditLogger(db).log(
        AuditEvent(
            organization_id=inv.organization_id,
            actor_user_id=tenant.user_id,
            action="INVITATION_EMAIL_QUEUED",
            target_type="invitation",
            target_id=inv.id,
            detail={"kind": "created", "email": inv.email, "role": inv.role},
        )
    )
    db.commit()

    # Security: do not expose raw token unless explicitly enabled for dev/debug.
    return CreateInvitationResponse(invitation=out, accept_url=_accept_url(raw))


@router.post("/accept")
def accept_invitation(
    body: AcceptInvitationRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    token_hash = _hash_token(body.token)
    inv = db.execute(select(InvitationModel).where(InvitationModel.token_hash == token_hash)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="INVITATION_NOT_FOUND")
    if inv.revoked_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_REVOKED")
    if inv.accepted_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_ALREADY_ACCEPTED")
    if _ensure_utc(inv.expires_at) <= _now():
        raise HTTPException(status_code=409, detail="INVITATION_EXPIRED")

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
        if getattr(user, "status", "") == "invited":
            user.status = "active"
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


@router.post("/accept_logged_in")
def accept_invitation_logged_in(
    body: AcceptInvitationLoggedInRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    token_hash = _hash_token(body.token)
    inv = db.execute(select(InvitationModel).where(InvitationModel.token_hash == token_hash)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="INVITATION_NOT_FOUND")
    if inv.revoked_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_REVOKED")
    if inv.accepted_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_ALREADY_ACCEPTED")
    if _ensure_utc(inv.expires_at) <= _now():
        raise HTTPException(status_code=409, detail="INVITATION_EXPIRED")
    if inv.email.lower() != current_user.email.lower():
        raise HTTPException(status_code=403, detail="INVITATION_EMAIL_MISMATCH")

    user = db.get(UserModel, current_user.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

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


@router.post("/decline")
def decline_invitation(
    body: DeclineInvitationRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    token_hash = _hash_token(body.token)
    inv = db.execute(select(InvitationModel).where(InvitationModel.token_hash == token_hash)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="INVITATION_NOT_FOUND")
    if inv.revoked_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_REVOKED")
    if inv.accepted_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_ALREADY_ACCEPTED")
    if getattr(inv, "declined_at", None) is not None:
        return {"status": "ok", "organization_id": inv.organization_id}
    if _ensure_utc(inv.expires_at) <= _now():
        raise HTTPException(status_code=409, detail="INVITATION_EXPIRED")

    inv.declined_at = _now()
    db.add(inv)
    db.commit()

    # If we provisioned a pre-user just for this invitation, remove it (only if no memberships exist).
    if getattr(inv, "provisioned_user_was_created", False) and getattr(inv, "provisioned_user_id", None):
        uid = str(inv.provisioned_user_id)
        m = (
            db.execute(select(MembershipModel).where(MembershipModel.user_id == uid).limit(1))
            .scalars()
            .first()
        )
        if m is None:
            u = db.get(UserModel, uid)
            if u is not None and getattr(u, "status", "") == "invited" and getattr(u, "password_hash", None) in (None, ""):
                db.delete(u)
                db.commit()

    return {"status": "ok", "organization_id": inv.organization_id}

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
        enqueue_outbox_event(
            db=db,
            ev=OutboxEvent(
                organization_id=inv.organization_id,
                event_type="INVITATION_EMAIL",
                payload={
                    "kind": "revoked",
                    "invitation_id": inv.id,
                    "organization_id": inv.organization_id,
                    "email": inv.email,
                    "role": inv.role,
                },
            ),
        )
        AuditLogger(db).log(
            AuditEvent(
                organization_id=inv.organization_id,
                actor_user_id=tenant.user_id,
                action="INVITATION_EMAIL_QUEUED",
                target_type="invitation",
                target_id=inv.id,
                detail={"kind": "revoked", "email": inv.email},
            )
        )
        db.commit()
    return {"status": "revoked", "invitation_id": inv.id}


@router.post("/{invitation_id}/resend", response_model=CreateInvitationResponse)
def resend_invitation(
    invitation_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
) -> CreateInvitationResponse:
    if not _authz.is_admin(
        DomainTenantContext(
            organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role
        )
    ):
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")
    inv = db.get(InvitationModel, invitation_id)
    if inv is None or inv.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.revoked_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_REVOKED")
    if inv.accepted_at is not None:
        raise HTTPException(status_code=409, detail="INVITATION_ALREADY_ACCEPTED")

    # Anti-spam: rate-limit resend (per invitation).
    last, count_24h = _email_queue_stats(db=db, organization_id=inv.organization_id, invitation_id=inv.id)
    if count_24h >= int(getattr(settings, "invitation_resend_max_per_day", 3)):
        raise HTTPException(status_code=429, detail="INVITATION_RESEND_RATE_LIMIT")
    if last is not None:
        min_interval = int(getattr(settings, "invitation_resend_min_interval_seconds", 60))
        if (_now() - _ensure_utc(last)).total_seconds() < float(min_interval):
            raise HTTPException(status_code=429, detail="INVITATION_RESEND_TOO_SOON")

    raw = secrets.token_urlsafe(48)
    inv.token_hash = _hash_token(raw)
    inv.expires_at = _now() + timedelta(days=7)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    out = InvitationOut(
        id=inv.id,
        organization_id=inv.organization_id,
        email=inv.email,
        role=inv.role,
        status=_status(inv),
        expires_at=inv.expires_at.isoformat(),
        accepted_at=inv.accepted_at.isoformat() if inv.accepted_at else None,
        revoked_at=inv.revoked_at.isoformat() if inv.revoked_at else None,
        created_by_user_id=inv.created_by_user_id,
        created_at=inv.created_at.isoformat() if inv.created_at else None,
    )

    org = db.get(OrganizationModel, tenant.organization_id)
    inviter = db.get(UserModel, tenant.user_id) if tenant.user_id else None
    enqueue_outbox_event(
        db=db,
        ev=OutboxEvent(
            organization_id=inv.organization_id,
            event_type="INVITATION_EMAIL",
            payload={
                "kind": "resent",
                "invitation_id": inv.id,
                "organization_id": inv.organization_id,
                "organization_name": getattr(org, "name", "") if org else "",
                "email": inv.email,
                "role": inv.role,
                "accept_url": _public_accept_url(settings=settings, raw_token=raw),
                "expires_at": inv.expires_at.isoformat(),
                "created_by_user_id": inv.created_by_user_id,
                "inviter_display_name": getattr(inviter, "display_name", None) if inviter else None,
            },
        ),
    )
    AuditLogger(db).log(
        AuditEvent(
            organization_id=inv.organization_id,
            actor_user_id=tenant.user_id,
            action="INVITATION_EMAIL_QUEUED",
            target_type="invitation",
            target_id=inv.id,
            detail={"kind": "resent", "email": inv.email},
        )
    )
    db.commit()

    return CreateInvitationResponse(invitation=out, accept_url=_accept_url(raw))

