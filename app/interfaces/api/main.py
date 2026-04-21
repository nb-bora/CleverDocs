"""FastAPI entrypoint."""

from fastapi import FastAPI

from app.infrastructure.db.orm.base import Base
from app.infrastructure.db.session import ENGINE
from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel  # noqa: F401
from app.infrastructure.db.orm.models.document_model import DocumentModel  # noqa: F401
from app.interfaces.api.routes.documents import router as documents_router
from app.interfaces.api.routes.search import router as search_router


app = FastAPI(title="CleverDocs")

app.include_router(documents_router)
app.include_router(search_router)


@app.on_event("startup")
def _startup_create_tables() -> None:
    # MVP ergonomics: create tables automatically so the API can run immediately.
    # Later phases should rely on Alembic migrations in production.
    Base.metadata.create_all(bind=ENGINE)


@app.get("/health")
def health():
    return {"status": "ok"}
