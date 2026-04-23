"""Document schemas (DTOs) used by the HTTP API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    organization_id: str | None = None
    organization_name: str | None = None
    uploaded_by_user_id: str | None = None
    filename: str
    status: str
    storage_key: str
    failed_reason: str | None = None
    text_preview: str | None = None
    created_at: datetime
    updated_at: datetime


class UploadDocumentResponse(BaseModel):
    document: DocumentOut


class ProcessDocumentResponse(BaseModel):
    document: DocumentOut

