"""FastAPI entrypoint."""

import os
import sys

from fastapi import FastAPI

from app.infrastructure.db.orm.base import Base
from app.infrastructure.db.session import ENGINE, ensure_sqlite_fts, ensure_sqlite_jobs_schema, ensure_sqlite_tenant_schema
from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel  # noqa: F401
from app.infrastructure.db.orm.models.document_model import DocumentModel  # noqa: F401
from app.infrastructure.db.orm.models.job_model import JobModel  # noqa: F401
from app.infrastructure.db.orm.models.organization_model import OrganizationModel  # noqa: F401
from app.infrastructure.db.orm.models.user_model import UserModel  # noqa: F401
from app.infrastructure.db.orm.models.membership_model import MembershipModel  # noqa: F401
from app.infrastructure.db.orm.models.audit_log_model import AuditLogModel  # noqa: F401
from app.interfaces.api.routes.bootstrap import router as bootstrap_router
from app.interfaces.api.routes.documents import router as documents_router
from app.interfaces.api.routes.jobs import router as jobs_router
from app.interfaces.api.routes.organizations import router as organizations_router
from app.interfaces.api.routes.search import router as search_router
from app.interfaces.api.routes.users import router as users_router


app = FastAPI(title="CleverDocs")

app.include_router(documents_router)
app.include_router(bootstrap_router)
app.include_router(jobs_router)
app.include_router(organizations_router)
app.include_router(search_router)
app.include_router(users_router)


@app.on_event("startup")
def _startup_create_tables() -> None:
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

    # MVP ergonomics: create tables automatically so the API can run immediately.
    # Later phases should rely on Alembic migrations in production.
    Base.metadata.create_all(bind=ENGINE)
    ensure_sqlite_tenant_schema()
    ensure_sqlite_fts()
    ensure_sqlite_jobs_schema()


@app.get("/health")
def health():
    return {"status": "ok"}
