"""FastAPI entrypoint."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.db.orm.base import Base
from app.interfaces.api.deps import Settings as AppSettings
from app.infrastructure.db.session import (
    ENGINE,
    ensure_sqlite_fts,
    ensure_sqlite_identity_schema,
    ensure_sqlite_jobs_schema,
    ensure_sqlite_semantic_schema,
    ensure_sqlite_tenant_schema,
)
from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel  # noqa: F401
from app.infrastructure.db.orm.models.document_model import DocumentModel  # noqa: F401
from app.infrastructure.db.orm.models.job_model import JobModel  # noqa: F401
from app.infrastructure.db.orm.models.organization_model import OrganizationModel  # noqa: F401
from app.infrastructure.db.orm.models.user_model import UserModel  # noqa: F401
from app.infrastructure.db.orm.models.membership_model import MembershipModel  # noqa: F401
from app.infrastructure.db.orm.models.refresh_token_model import RefreshTokenModel  # noqa: F401
from app.infrastructure.db.orm.models.audit_log_model import AuditLogModel  # noqa: F401
from app.infrastructure.db.orm.models.invitation_model import InvitationModel  # noqa: F401
from app.interfaces.api.routes.auth import router as auth_router
from app.interfaces.api.routes.documents import router as documents_router
from app.interfaces.api.routes.invitations import router as invitations_router
from app.interfaces.api.routes.organizations import router as organizations_router
from app.interfaces.api.routes.qa import router as qa_router
from app.interfaces.api.routes.search import router as search_router
from app.interfaces.api.routes.users import router as users_router


def _startup_create_tables() -> None:
    settings = AppSettings()
    # Windows stability: ensure UTF-8 output so progress bars / OCR logs don't crash.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception as e:
        try:
            print(f"stdout/stderr reconfigure skipped: {type(e).__name__}: {e}", file=sys.stderr)
        except Exception:
            # If even stderr fails, continue startup anyway.
            ...

    # Disable tqdm unicode/progress rendering (EasyOCR downloads) to avoid console encoding issues.
    os.environ.setdefault("TQDM_DISABLE", "1")

    # Dev ergonomics: create/evolve schema automatically.
    # In non-dev environments, rely on Alembic migrations.
    if settings.app_env == "dev":
        Base.metadata.create_all(bind=ENGINE)
        ensure_sqlite_tenant_schema()
        ensure_sqlite_identity_schema()
        ensure_sqlite_fts()
        ensure_sqlite_semantic_schema()
        ensure_sqlite_jobs_schema()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _startup_create_tables()
    yield


app = FastAPI(title="CleverDocs", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(invitations_router)
app.include_router(search_router)
app.include_router(users_router)
app.include_router(qa_router)
