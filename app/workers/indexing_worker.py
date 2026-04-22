"""Indexing worker (DB queue, MVP).

Run this worker as a separate process:
  python -m app.workers.indexing_worker

It polls `jobs` table for queued INDEX jobs and pushes content to OpenSearch.
"""

from __future__ import annotations

import os
import socket
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.db.orm.models.job_model import JobModel
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.search.search_engine_impl import SearchEngineImpl, SearchEngineSettings
from app.interfaces.api.deps import Settings


WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _now() -> datetime:
    return datetime.now(UTC)


def claim_next_job(db: Session) -> JobModel | None:
    now = _now()
    job = db.execute(
        select(JobModel)
        .where(JobModel.type == "INDEX")
        .where(JobModel.status == "queued")
        .where(JobModel.organization_id.is_not(None))
        .where((JobModel.next_run_at.is_(None)) | (JobModel.next_run_at <= now))
        .order_by(JobModel.created_at.asc())
        .limit(1)
    ).scalars().first()

    if job is None:
        return None

    job.status = "running"
    job.locked_by = WORKER_ID
    job.locked_at = _now()
    job.attempts = int(job.attempts or 0) + 1
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_job(db: Session, job: JobModel, settings: Settings) -> None:
    doc = db.get(DocumentModel, job.document_id)
    if doc is None:
        job.status = "failed"
        job.last_error = "DOCUMENT_NOT_FOUND"
        db.add(job)
        db.commit()
        return
    if not doc.organization_id or doc.organization_id != job.organization_id:
        job.status = "failed"
        job.last_error = "TENANT_MISMATCH"
        db.add(job)
        db.commit()
        return

    content = db.get(DocumentContentModel, doc.id)
    cleaned = (content.cleaned_text if content else "") or ""
    if not cleaned:
        # If document is deleted, we still want to push status to the index (best-effort).
        if doc.status == "deleted":
            cleaned = ""
        else:
            job.status = "failed"
            job.last_error = "EMPTY_CONTENT"
            db.add(job)
            db.commit()
            return

    try:
        engine = SearchEngineImpl(
            SearchEngineSettings(
                opensearch_url=settings.opensearch_url,
                index_prefix=settings.opensearch_index_prefix,
            )
        )
        if not engine.ping():
            doc.status = "indexing_failed"
            doc.failed_reason = "OPENSEARCH_DOWN"
            job.last_error = "OPENSEARCH_DOWN"
            # Retry later (temporary dependency outage).
            if job.attempts < job.max_attempts:
                job.status = "queued"
                job.schedule_in(seconds=min(600, 5 * (2 ** min(job.attempts, 8))))
            else:
                job.status = "failed"
            db.add_all([doc, job])
            db.commit()
            return

        engine.index_document(
            document_id=doc.id,
            organization_id=doc.organization_id,
            uploaded_by_user_id=doc.uploaded_by_user_id,
            status=doc.status if doc.status in {"archived", "deleted"} else "indexed",
            filename=doc.filename,
            content=cleaned,
            created_at_iso=doc.created_at.isoformat(),
        )

        if doc.status not in {"archived", "deleted"}:
            doc.status = "indexed"
            doc.failed_reason = None
        job.status = "succeeded"
        job.last_error = None
        db.add_all([doc, job])
        db.commit()
    except Exception as e:
        doc.status = "indexing_failed"
        doc.failed_reason = f"INDEX_FAILED: {type(e).__name__}: {e}"
        job.last_error = doc.failed_reason
        if job.attempts < job.max_attempts:
            job.status = "queued"
            job.schedule_in(seconds=min(600, 5 * (2 ** min(job.attempts, 8))))
        else:
            job.status = "dead"
        db.add_all([doc, job])
        db.commit()


def main() -> None:
    settings = Settings()
    print(f"INDEX worker started: {WORKER_ID}")
    while True:
        db = SessionLocal()
        try:
            job = claim_next_job(db)
            if job is None:
                time.sleep(1.0)
                continue
            process_job(db, job, settings)
        finally:
            db.close()


if __name__ == "__main__":
    main()
