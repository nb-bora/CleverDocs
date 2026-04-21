"""OCR worker (DB queue, MVP).

Run this worker as a separate process:
  python -m app.workers.ocr_worker

It polls `jobs` table for queued OCR jobs, processes documents, writes DocumentContent,
updates Document status, and enqueues INDEX jobs.
"""

from __future__ import annotations

import os
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.db.orm.models.job_model import JobModel
from app.infrastructure.db.session import SessionLocal, ensure_sqlite_fts
from app.infrastructure.db.fts import upsert_sqlite_fts
from app.infrastructure.ocr.ocr_service_impl import OcrConfig, OcrServiceImpl
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.interfaces.api.deps import Settings


WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _now() -> datetime:
    return datetime.now(UTC)


def claim_next_job(db: Session) -> JobModel | None:
    # MVP locking: for SQLite, keep it simple. In Postgres we'd use FOR UPDATE SKIP LOCKED.
    now = _now()
    job = db.execute(
        select(JobModel)
        .where(JobModel.type == "OCR")
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

    storage = LocalFileStorage(root_dir=settings.local_storage_dir)
    path = storage.resolve(doc.storage_key)
    if not path.exists():
        doc.status = "failed"
        doc.failed_reason = "FILE_NOT_FOUND"
        job.status = "failed"
        job.last_error = "FILE_NOT_FOUND"
        db.add_all([doc, job])
        db.commit()
        return

    suffix = path.suffix.lower()
    text_like = suffix in {".txt", ".md", ".csv", ".log", ".json"}

    doc.status = "processing"
    doc.failed_reason = None
    db.add(doc)
    db.commit()

    try:
        if text_like:
            raw = path.read_text(encoding="utf-8", errors="replace")
            cleaned = raw.strip()
            ocr_engine = "text"
            language = None
        else:
            langs = tuple(x.strip() for x in settings.ocr_langs.split(",") if x.strip())
            ocr = OcrServiceImpl(
                OcrConfig(
                    languages=langs or ("fr",),
                    gpu=bool(settings.ocr_gpu),
                    pdf_max_pages=int(settings.ocr_pdf_max_pages),
                    pdf_zoom=float(settings.ocr_pdf_zoom),
                )
            )
            cleaned = ocr.extract_text(file_path=str(path))
            raw = cleaned
            ocr_engine = "easyocr_pdf" if suffix == ".pdf" else "easyocr"
            language = ",".join(langs) if langs else None

        content = db.get(DocumentContentModel, doc.id) or DocumentContentModel(document_id=doc.id)
        content.raw_text = raw
        content.cleaned_text = cleaned
        content.ocr_engine = ocr_engine
        content.language = language
        db.add(content)

        doc.status = "processed"
        doc.failed_reason = None
        db.add(doc)

        # Keep SQLite FTS updated for smart fallback search.
        if cleaned:
            upsert_sqlite_fts(
                db=db,
                organization_id=doc.organization_id,
                document_id=doc.id,
                filename=doc.filename,
                content=cleaned,
            )

        # Enqueue index job (worker to be implemented next).
        db.add(JobModel(type="INDEX", status="queued", organization_id=doc.organization_id, document_id=doc.id))

        job.status = "succeeded"
        job.last_error = None
        db.add(job)
        db.commit()
    except Exception as e:
        doc.status = "failed"
        doc.failed_reason = f"OCR_FAILED: {type(e).__name__}: {e}"
        # Retry with exponential backoff until max_attempts.
        job.last_error = doc.failed_reason
        if job.attempts < job.max_attempts:
            job.status = "queued"
            job.schedule_in(seconds=min(300, 2 ** min(job.attempts, 8)))
        else:
            job.status = "failed"
        db.add_all([doc, job])
        db.commit()


def main() -> None:
    settings = Settings()

    # Ensure FTS table exists when using SQLite.
    ensure_sqlite_fts()

    print(f"OCR worker started: {WORKER_ID}")
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
