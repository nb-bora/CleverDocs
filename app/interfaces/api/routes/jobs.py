"""Jobs admin routes (MVP).

This is intentionally minimal and will be protected by auth later.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.job_model import JobModel
from app.interfaces.api.deps import TenantContext, get_db, get_tenant_context


router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

_ADMIN_ROLES = {"owner", "admin"}


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant


def _require_admin(tenant: TenantContext) -> None:
    if (tenant.role or "") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")


@router.get("")
def list_jobs(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(_get_tenant)] = None,
):
    _require_admin(tenant)
    stmt = (
        select(JobModel)
        .where(JobModel.organization_id == tenant.organization_id)
        .order_by(JobModel.created_at.desc())
        .limit(limit)
    )
    items = db.execute(stmt).scalars().all()
    return [
        {
            "id": j.id,
            "type": j.type,
            "status": j.status,
            "document_id": j.document_id,
            "attempts": j.attempts,
            "max_attempts": j.max_attempts,
            "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
            "last_error": j.last_error,
            "locked_by": j.locked_by,
            "locked_at": j.locked_at.isoformat() if j.locked_at else None,
            "created_at": j.created_at.isoformat(),
            "updated_at": j.updated_at.isoformat(),
        }
        for j in items
    ]


@router.get("/{job_id}")
def get_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(_get_tenant)] = None,
) -> dict:
    _require_admin(tenant)
    j = db.get(JobModel, job_id)
    if j is None or j.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": j.id,
        "type": j.type,
        "status": j.status,
        "document_id": j.document_id,
        "attempts": j.attempts,
        "max_attempts": j.max_attempts,
        "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
        "last_error": j.last_error,
        "locked_by": j.locked_by,
        "locked_at": j.locked_at.isoformat() if j.locked_at else None,
        "created_at": j.created_at.isoformat(),
        "updated_at": j.updated_at.isoformat(),
    }


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(_get_tenant)] = None,
) -> dict:
    _require_admin(tenant)
    j = db.get(JobModel, job_id)
    if j is None or j.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if j.status not in {"queued", "running"}:
        return {"status": j.status, "job_id": j.id}
    j.status = "cancelled"
    j.locked_by = None
    j.locked_at = None
    j.next_run_at = None
    db.add(j)
    db.commit()
    return {"status": "cancelled", "job_id": j.id}


@router.post("/{job_id}/retry")
def retry_job(
    job_id: str,
    reset_attempts: Annotated[bool, Query()] = True,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(_get_tenant)] = None,
) -> dict:
    _require_admin(tenant)
    j = db.get(JobModel, job_id)
    if j is None or j.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Job not found")
    j.status = "queued"
    j.locked_by = None
    j.locked_at = None
    j.next_run_at = None
    j.last_error = None
    if reset_attempts:
        j.attempts = 0
    db.add(j)
    db.commit()
    return {"status": "queued", "job_id": j.id, "reset_attempts": bool(reset_attempts)}


@router.post("/retry_failed")
def retry_failed_jobs(
    type: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    reset_attempts: Annotated[bool, Query()] = True,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(_get_tenant)] = None,
) -> dict:
    _require_admin(tenant)
    sel = (
        select(JobModel.id)
        .where(JobModel.organization_id == tenant.organization_id)
        .where(JobModel.status == "failed")
        .order_by(JobModel.updated_at.desc())
    )
    if type:
        sel = sel.where(JobModel.type == type)
    job_ids = [row[0] for row in db.execute(sel.limit(limit)).all()]
    if not job_ids:
        return {"retried": 0, "type": type, "limit": limit}

    upd = (
        update(JobModel)
        .where(JobModel.id.in_(job_ids))
        .values(
            status="queued",
            locked_by=None,
            locked_at=None,
            next_run_at=None,
            last_error=None,
            attempts=(0 if reset_attempts else JobModel.attempts),
        )
        .execution_options(synchronize_session=False)
    )
    result = db.execute(upd)
    db.commit()
    return {"retried": int(result.rowcount or 0), "type": type, "limit": limit}

