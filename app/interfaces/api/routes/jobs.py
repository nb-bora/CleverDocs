"""Jobs admin routes (MVP).

This is intentionally minimal and will be protected by auth later.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.job_model import JobModel
from app.interfaces.api.deps import TenantContext, get_db, get_tenant_context


router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant


@router.get("")
def list_jobs(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(_get_tenant)] = None,
):
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


@router.post("/retry_failed")
def retry_failed_jobs(
    type: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    reset_attempts: Annotated[bool, Query()] = True,
    db: Annotated[Session, Depends(get_db)] = None,
    tenant: Annotated[TenantContext, Depends(_get_tenant)] = None,
) -> dict:
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

