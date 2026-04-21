"""Document routes.

Phase 1: upload + get document (MVP).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.db.orm.models.job_model import JobModel
from app.infrastructure.db.fts import upsert_sqlite_fts
from app.infrastructure.ocr.easyocr_adapter import EasyOcrNotInstalled
from app.infrastructure.ocr.ocr_service_impl import OcrConfig, OcrServiceImpl, PdfOcrNotInstalled
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.search.search_engine_impl import SearchEngineImpl, SearchEngineSettings
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.interfaces.api.deps import Settings, TenantContext, get_db, get_settings, get_tenant_context
from app.interfaces.api.schemas.documents import DocumentOut, ProcessDocumentResponse, UploadDocumentResponse


router = APIRouter(prefix="/v1/documents", tags=["documents"])


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant

def _background_ocr_and_index(
    *,
    document_id: str,
    absolute_path: str,
    suffix: str,
    settings: Settings,
) -> None:
    # Runs outside request lifecycle: create its own DB session.
    db = SessionLocal()
    try:
        doc = db.get(DocumentModel, document_id)
        if doc is None:
            return

        langs = tuple(x.strip() for x in settings.ocr_langs.split(",") if x.strip())
        ocr = OcrServiceImpl(
            OcrConfig(
                languages=langs or ("fr",),
                gpu=bool(settings.ocr_gpu),
                pdf_max_pages=int(settings.ocr_pdf_max_pages),
                pdf_zoom=float(settings.ocr_pdf_zoom),
            )
        )

        cleaned = ocr.extract_text(file_path=absolute_path)
        raw_text = cleaned

        content = db.get(DocumentContentModel, document_id) or DocumentContentModel(document_id=document_id)
        content.raw_text = raw_text
        content.cleaned_text = cleaned
        content.ocr_engine = "easyocr_pdf" if suffix == ".pdf" else "easyocr"
        content.language = ",".join(langs) if langs else None
        db.add(content)

        doc.status = "processed"
        doc.failed_reason = None
        db.add(doc)
        if cleaned and doc.organization_id:
            upsert_sqlite_fts(
                db=db,
                organization_id=doc.organization_id,
                document_id=doc.id,
                filename=doc.filename,
                content=cleaned,
            )
        db.commit()

        if cleaned:
            try:
                engine = SearchEngineImpl(
                    SearchEngineSettings(
                        opensearch_url=settings.opensearch_url,
                        index_prefix=settings.opensearch_index_prefix,
                    )
                )
                if engine.ping():
                    doc.status = "indexing_pending"
                    db.add(doc)
                    db.commit()
                    engine.index_document(
                        document_id=doc.id,
                        organization_id=doc.organization_id,
                        uploaded_by_user_id=doc.uploaded_by_user_id,
                        filename=doc.filename,
                        content=cleaned,
                        created_at_iso=doc.created_at.isoformat(),
                    )
                    doc.status = "indexed"
                    db.add(doc)
                    db.commit()
            except Exception:
                doc.status = "indexing_failed"
                db.add(doc)
                db.commit()

    except EasyOcrNotInstalled:
        doc = db.get(DocumentModel, document_id)
        if doc:
            doc.status = "failed"
            doc.failed_reason = "EASYOCR_NOT_INSTALLED"
            db.add(doc)
            db.commit()
    except PdfOcrNotInstalled:
        doc = db.get(DocumentModel, document_id)
        if doc:
            doc.status = "failed"
            doc.failed_reason = "PYMUPDF_NOT_INSTALLED"
            db.add(doc)
            db.commit()
    except Exception as e:
        doc = db.get(DocumentModel, document_id)
        if doc:
            doc.status = "failed"
            # Persist diagnostic info (helps a lot during development).
            msg = f"{type(e).__name__}: {e}".strip()
            doc.failed_reason = f"OCR_FAILED: {msg}" if msg else "OCR_FAILED"
            db.add(doc)
            db.commit()
    finally:
        db.close()


def _get_storage(settings: Settings) -> LocalFileStorage:
    return LocalFileStorage(root_dir=settings.local_storage_dir)


@router.post("", response_model=UploadDocumentResponse)
def upload_document(
    file: UploadFile,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    tenant: TenantContext = Depends(_get_tenant),
) -> UploadDocumentResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    storage = _get_storage(settings)
    storage_key = storage.save_upload(file)

    if not tenant.user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-Id header")

    doc = DocumentModel(
        id=str(uuid.uuid4()),
        organization_id=tenant.organization_id,
        uploaded_by_user_id=tenant.user_id,
        filename=file.filename,
        status="uploaded",
        storage_key=storage_key,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Enqueue OCR job right away (worker will process asynchronously).
    db.add(
        JobModel(
            type="OCR",
            status="queued",
            organization_id=tenant.organization_id,
            document_id=doc.id,
        )
    )
    db.commit()

    return UploadDocumentResponse(document=DocumentOut.model_validate(doc, from_attributes=True))


@router.post("/{document_id}/reindex")
def reindex_document(
    document_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(_get_tenant),
) -> dict:
    doc = db.get(DocumentModel, document_id)
    if doc is None or doc.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")
    db.add(
        JobModel(
            type="INDEX",
            status="queued",
            organization_id=tenant.organization_id,
            document_id=doc.id,
        )
    )
    db.commit()
    return {"status": "queued", "document_id": doc.id}


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(_get_tenant),
) -> DocumentOut:
    doc = db.get(DocumentModel, document_id)
    if doc is None or doc.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")
    content = db.get(DocumentContentModel, document_id)
    preview = None
    if content and content.cleaned_text:
        preview = content.cleaned_text[:500]
    out = DocumentOut.model_validate(doc, from_attributes=True)
    return out.model_copy(update={"text_preview": preview})


@router.post("/{document_id}/process", response_model=ProcessDocumentResponse)
def process_document(
    document_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    tenant: TenantContext = Depends(_get_tenant),
) -> ProcessDocumentResponse:
    doc = db.get(DocumentModel, document_id)
    if doc is None or doc.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")

    def _try_index(cleaned_text: str) -> None:
        # Index to OpenSearch if available (MVP). If indexing fails, mark as indexing_failed.
        try:
            engine = SearchEngineImpl(
                SearchEngineSettings(
                    opensearch_url=settings.opensearch_url,
                    index_prefix=settings.opensearch_index_prefix,
                )
            )
            if not engine.ping():
                return

            doc.status = "indexing_pending"
            db.add(doc)
            db.commit()

            engine.index_document(
                document_id=doc.id,
                organization_id=doc.organization_id,
                uploaded_by_user_id=doc.uploaded_by_user_id,
                filename=doc.filename,
                content=cleaned_text,
                created_at_iso=doc.created_at.isoformat(),
            )
            doc.status = "indexed"
            db.add(doc)
            db.commit()
        except Exception:
            doc.status = "indexing_failed"
            db.add(doc)
            db.commit()

    # Idempotence: if content already exists, don't redo extraction.
    existing = db.get(DocumentContentModel, document_id)
    if existing is not None:
        cleaned_existing = existing.cleaned_text or ""
        if cleaned_existing and doc.organization_id:
            upsert_sqlite_fts(
                db=db,
                organization_id=doc.organization_id,
                document_id=doc.id,
                filename=doc.filename,
                content=cleaned_existing,
            )
            db.commit()
        # If already indexed, just return. Otherwise try to index now.
        if doc.status != "indexed" and cleaned_existing:
            _try_index(cleaned_existing)
        out = DocumentOut.model_validate(doc, from_attributes=True)
        preview = cleaned_existing[:500] or None
        return ProcessDocumentResponse(document=out.model_copy(update={"text_preview": preview}))

    # Transition to processing
    doc.status = "processing"
    doc.failed_reason = None
    db.add(doc)
    db.commit()

    storage = _get_storage(settings)
    try:
        path = storage.resolve(doc.storage_key)
    except ValueError:
        doc.status = "failed"
        doc.failed_reason = "INVALID_STORAGE_KEY"
        db.add(doc)
        db.commit()
        raise HTTPException(status_code=500, detail="Invalid document storage key")

    if not path.exists():
        doc.status = "failed"
        doc.failed_reason = "FILE_NOT_FOUND"
        db.add(doc)
        db.commit()
        raise HTTPException(status_code=404, detail="File not found in storage")

    # MVP processing:
    # - if it's a text-like file, read it as UTF-8
    # - otherwise, mark as failed with OCR_NOT_IMPLEMENTED (until EasyOCR/Tesseract plugged)
    suffix = path.suffix.lower()
    text_like = suffix in {".txt", ".md", ".csv", ".log", ".json"}
    image_like = suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}

    raw_text: str
    cleaned: str
    ocr_engine: str
    language: str | None

    if text_like:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        cleaned = raw_text.strip()
        ocr_engine = "text"
        language = None
    elif image_like:
        # Run OCR in background (models download can take minutes on first run).
        doc.status = "processing"
        db.add(doc)
        db.commit()
        background.add_task(
            _background_ocr_and_index,
            document_id=document_id,
            absolute_path=str(path),
            suffix=suffix,
            settings=settings,
        )
        out = DocumentOut.model_validate(doc, from_attributes=True)
        return ProcessDocumentResponse(document=out)
    elif suffix == ".pdf":
        doc.status = "processing"
        db.add(doc)
        db.commit()
        background.add_task(
            _background_ocr_and_index,
            document_id=document_id,
            absolute_path=str(path),
            suffix=suffix,
            settings=settings,
        )
        out = DocumentOut.model_validate(doc, from_attributes=True)
        return ProcessDocumentResponse(document=out)
    else:
        doc.status = "failed"
        doc.failed_reason = "OCR_UNSUPPORTED_TYPE"
        db.add(doc)
        db.commit()
        out = DocumentOut.model_validate(doc, from_attributes=True)
        return ProcessDocumentResponse(document=out)

    content = existing or DocumentContentModel(document_id=document_id)
    content.raw_text = raw_text
    content.cleaned_text = cleaned
    content.ocr_engine = ocr_engine
    content.language = language
    db.add(content)

    doc.status = "processed"
    doc.failed_reason = None
    db.add(doc)
    if cleaned and doc.organization_id:
        upsert_sqlite_fts(
            db=db,
            organization_id=doc.organization_id,
            document_id=doc.id,
            filename=doc.filename,
            content=cleaned,
        )
    db.commit()

    if cleaned:
        _try_index(cleaned)

    out = DocumentOut.model_validate(doc, from_attributes=True)
    preview = cleaned[:500] or None
    return ProcessDocumentResponse(document=out.model_copy(update={"text_preview": preview}))


@router.get("/{document_id}/file")
def download_document_file(
    document_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    tenant: TenantContext = Depends(_get_tenant),
) -> FileResponse:
    doc = db.get(DocumentModel, document_id)
    if doc is None or doc.organization_id != tenant.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = _get_storage(settings)
    try:
        path = storage.resolve(doc.storage_key)
    except ValueError:
        # Storage key should always be safe; this indicates corruption or tampering.
        raise HTTPException(status_code=500, detail="Invalid document storage key")

    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found in storage")

    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=doc.filename,
    )

