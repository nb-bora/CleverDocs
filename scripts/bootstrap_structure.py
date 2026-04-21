"""
Bootstrap CleverDocs project skeleton.

Creates the full DDD/CQRS folder structure and Python module stubs.
Safe to re-run (idempotent): it won't overwrite existing files.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


FILES: dict[str, str] = {
    # --- root packages ---
    "app/__init__.py": '"""CleverDocs application package."""\n',
    "app/domain/__init__.py": '"""Domain layer (pure business logic)."""\\n',
    "app/application/__init__.py": '"""Application layer (use cases / orchestration)."""\\n',
    "app/infrastructure/__init__.py": '"""Infrastructure layer (adapters, persistence, integrations)."""\\n',
    "app/interfaces/__init__.py": '"""Interface layer (HTTP API, DTOs, middleware)."""\\n',
    "app/projections/__init__.py": '"""Read-model projections consumers."""\\n',
    "app/workers/__init__.py": '"""Async workers entrypoints."""\\n',

    # --- domain/common ---
    "app/domain/common/__init__.py": '"""Shared domain building blocks."""\\n',
    "app/domain/common/entity.py": '"""Base Entity types for the domain layer."""\\n\\n\\nclass Entity:\\n    def __init__(self, entity_id: str) -> None:\\n        self.id = entity_id\\n',
    "app/domain/common/value_object.py": '"""Base ValueObject types for the domain layer (immutable by convention)."""\\n',
    "app/domain/common/events.py": '"""Base DomainEvent types used by domain and application layers."""\\n\\n\\nclass DomainEvent:\\n    pass\\n',
    "app/domain/common/exceptions.py": '"""Domain exceptions (invariant violations, invalid transitions)."""\\n\\n\\nclass DomainError(Exception):\\n    pass\\n',

    # --- organization ---
    "app/domain/organization/__init__.py": '"""Organization (tenant) bounded context."""\\n',
    "app/domain/organization/entities/__init__.py": '"""Organization entities."""\\n',
    "app/domain/organization/entities/organization.py": '"""Organization aggregate/entity (tenant)."""\\n',
    "app/domain/organization/entities/membership.py": '"""Membership entity linking user <-> organization with roles."""\\n',
    "app/domain/organization/repositories/__init__.py": '"""Organization repositories (ports)."""\\n',
    "app/domain/organization/repositories/organization_repository.py": '"""OrganizationRepository port (interface)."""\\n\\n\\nclass OrganizationRepository:\\n    pass\\n',

    # --- identity ---
    "app/domain/identity/__init__.py": '"""Identity & access bounded context."""\\n',
    "app/domain/identity/entities/__init__.py": '"""Identity entities."""\\n',
    "app/domain/identity/entities/user.py": '"""User entity."""\\n',
    "app/domain/identity/entities/role.py": '"""Role entity (often scoped per organization)."""\\n',
    "app/domain/identity/entities/permission.py": '"""Permission entity (atomic capability)."""\\n',
    "app/domain/identity/services/__init__.py": '"""Identity domain services / policies."""\\n',
    "app/domain/identity/services/authorization_policy.py": '"""Authorization policy rules (authZ) for use cases."""\\n\\n\\nclass AuthorizationPolicy:\\n    pass\\n',
    "app/domain/identity/services/document_policy.py": '"""Document policy rules for actions/transitions."""\\n\\n\\nclass DocumentPolicy:\\n    pass\\n',
    "app/domain/identity/repositories/__init__.py": '"""Identity repositories (ports)."""\\n',
    "app/domain/identity/repositories/user_repository.py": '"""UserRepository port (interface)."""\\n\\n\\nclass UserRepository:\\n    pass\\n',

    # --- document ---
    "app/domain/document/__init__.py": '"""Document bounded context (core domain)."""\\n',
    "app/domain/document/aggregates/__init__.py": '"""Document aggregates."""\\n',
    "app/domain/document/aggregates/document.py": '"""Document aggregate root: lifecycle + invariants."""\\n',
    "app/domain/document/aggregates/document_versioning.py": '"""Document versioning rules (active version, rollback)."""\\n',
    "app/domain/document/value_objects/__init__.py": '"""Document value objects."""\\n',
    "app/domain/document/value_objects/document_status.py": '"""Document status value object/enum."""\\n',
    "app/domain/document/value_objects/file_type.py": '"""File type value object/enum."""\\n',
    "app/domain/document/events/__init__.py": '"""Document domain events."""\\n',
    "app/domain/document/events/document_uploaded.py": '"""Event: document uploaded."""\\n',
    "app/domain/document/events/document_processed.py": '"""Event: OCR processed."""\\n',
    "app/domain/document/events/document_indexed.py": '"""Event: indexed in search."""\\n',
    "app/domain/document/events/document_failed.py": '"""Event: document processing failed."""\\n',
    "app/domain/document/events/document_version_added.py": '"""Event: new document version added."""\\n',
    "app/domain/document/events/document_reindex_requested.py": '"""Event: reindex requested."""\\n',
    "app/domain/document/repositories/__init__.py": '"""Document repositories (ports)."""\\n',
    "app/domain/document/repositories/document_repository.py": '"""DocumentRepository port (interface)."""\\n\\n\\nclass DocumentRepository:\\n    pass\\n',

    # --- processing ---
    "app/domain/processing/__init__.py": '"""Processing bounded context (OCR + enrichment as domain ports)."""\\n',
    "app/domain/processing/entities/__init__.py": '"""Processing entities."""\\n',
    "app/domain/processing/entities/document_content.py": '"""DocumentContent entity: raw/clean text + OCR metadata."""\\n',
    "app/domain/processing/services/__init__.py": '"""Processing service ports (interfaces)."""\\n',
    "app/domain/processing/services/ocr_service.py": '"""OCR service port (interface)."""\\n\\n\\nclass OcrService:\\n    def extract_text(self, *, file_path: str) -> str:\\n        raise NotImplementedError\\n',
    "app/domain/processing/services/text_cleaner.py": '"""Text cleaner port (interface)."""\\n\\n\\nclass TextCleaner:\\n    def clean(self, raw_text: str) -> str:\\n        raise NotImplementedError\\n',

    # --- search ---
    "app/domain/search/__init__.py": '"""Search bounded context (read model ports)."""\\n',
    "app/domain/search/value_objects/__init__.py": '"""Search value objects."""\\n',
    "app/domain/search/value_objects/search_query.py": '"""SearchQuery value object."""\\n',
    "app/domain/search/services/__init__.py": '"""Search service ports (interfaces)."""\\n',
    "app/domain/search/services/search_engine.py": '"""Search engine port (interface)."""\\n\\n\\nclass SearchEngine:\\n    pass\\n',
    "app/domain/search/read_models/__init__.py": '"""Search read models."""\\n',
    "app/domain/search/read_models/search_result.py": '"""SearchResult read model."""\\n',

    # --- application ---
    "app/application/common/__init__.py": '"""Application common building blocks."""\\n',
    "app/application/common/unit_of_work.py": '"""UnitOfWork port (transaction boundary)."""\\n\\n\\nclass UnitOfWork:\\n    def __enter__(self):\\n        return self\\n\\n    def __exit__(self, exc_type, exc, tb):\\n        return False\\n\\n    def commit(self) -> None:\\n        raise NotImplementedError\\n',
    "app/application/common/event_publisher.py": '"""EventPublisher port (publish domain events)."""\\n\\n\\nclass EventPublisher:\\n    def publish(self, event) -> None:\\n        raise NotImplementedError\\n',
    "app/application/commands/__init__.py": '"""Write-side commands (DTOs)."""\\n',
    "app/application/commands/upload_document.py": '"""Command: UploadDocument."""\\n',
    "app/application/commands/archive_document.py": '"""Command: ArchiveDocument."""\\n',
    "app/application/commands/add_document_version.py": '"""Command: AddDocumentVersion."""\\n',
    "app/application/commands/request_reindex.py": '"""Command: RequestReindex."""\\n',
    "app/application/handlers/__init__.py": '"""Command handlers (use cases)."""\\n',
    "app/application/handlers/upload_document_handler.py": '"""Use case: upload document."""\\n',
    "app/application/handlers/archive_document_handler.py": '"""Use case: archive document."""\\n',
    "app/application/handlers/add_document_version_handler.py": '"""Use case: add document version."""\\n',
    "app/application/handlers/request_reindex_handler.py": '"""Use case: request reindex."""\\n',
    "app/application/queries/__init__.py": '"""Read-side queries (DTOs / query handlers)."""\\n',
    "app/application/queries/search_documents.py": '"""Query: search documents."""\\n',
    "app/application/queries/get_document.py": '"""Query: get document."""\\n',
    "app/application/queries/get_document_status_timeline.py": '"""Query: document status timeline."""\\n',
    "app/application/auth/__init__.py": '"""Application auth helpers."""\\n',
    "app/application/auth/require_permission.py": '"""Helper: require a permission for a use case."""\\n',

    # --- infrastructure ---
    "app/infrastructure/db/__init__.py": '"""Database infrastructure."""\\n',
    "app/infrastructure/db/orm/__init__.py": '"""ORM setup (SQLAlchemy models)."""\\n',
    "app/infrastructure/db/orm/base.py": '"""SQLAlchemy declarative base (placeholder)."""\\n',
    "app/infrastructure/db/orm/models/__init__.py": '"""ORM models package."""\\n',
    "app/infrastructure/db/orm/models/organization_model.py": '"""ORM model: organization."""\\n',
    "app/infrastructure/db/orm/models/membership_model.py": '"""ORM model: membership."""\\n',
    "app/infrastructure/db/orm/models/user_model.py": '"""ORM model: user."""\\n',
    "app/infrastructure/db/orm/models/role_model.py": '"""ORM model: role."""\\n',
    "app/infrastructure/db/orm/models/permission_model.py": '"""ORM model: permission."""\\n',
    "app/infrastructure/db/orm/models/document_model.py": '"""ORM model: document."""\\n',
    "app/infrastructure/db/orm/models/document_content_model.py": '"""ORM model: document content."""\\n',
    "app/infrastructure/db/orm/models/audit_log_model.py": '"""ORM model: audit log."""\\n',
    "app/infrastructure/db/repositories/__init__.py": '"""SQL repository implementations."""\\n',
    "app/infrastructure/db/repositories/organization_repository_sql.py": '"""SQL implementation of OrganizationRepository."""\\n',
    "app/infrastructure/db/repositories/user_repository_sql.py": '"""SQL implementation of UserRepository."""\\n',
    "app/infrastructure/db/repositories/document_repository_sql.py": '"""SQL implementation of DocumentRepository."""\\n',
    "app/infrastructure/db/session.py": '"""DB session factory (placeholder)."""\\n',
    "app/infrastructure/db/unit_of_work_sql.py": '"""SQL UnitOfWork implementation (placeholder)."""\\n',
    "app/infrastructure/audit/__init__.py": '"""Audit infrastructure."""\\n',
    "app/infrastructure/audit/audit_logger.py": '"""Audit logger (writes to audit_log)."""\\n',
    "app/infrastructure/storage/__init__.py": '"""File storage infrastructure."""\\n',
    "app/infrastructure/storage/local_file_storage.py": '"""Local file storage adapter."""\\n',
    "app/infrastructure/storage/s3_file_storage.py": '"""S3-compatible file storage adapter."""\\n',
    "app/infrastructure/messaging/__init__.py": '"""Messaging infrastructure (event bus, outbox)."""\\n',
    "app/infrastructure/messaging/event_bus.py": '"""Event bus adapter (placeholder)."""\\n',
    "app/infrastructure/messaging/outbox/__init__.py": '"""Outbox pattern components."""\\n',
    "app/infrastructure/messaging/outbox/outbox_model.py": '"""Outbox event persistence model (placeholder)."""\\n',
    "app/infrastructure/messaging/outbox/outbox_publisher.py": '"""Publish outbox events to bus (placeholder)."""\\n',
    "app/infrastructure/messaging/outbox/outbox_dispatcher.py": '"""Dispatcher: poll outbox, publish, mark sent (idempotent)."""\\n',
    "app/infrastructure/ocr/__init__.py": '"""OCR adapters."""\\n',
    "app/infrastructure/ocr/easyocr_adapter.py": '"""EasyOCR adapter (placeholder)."""\\n',
    "app/infrastructure/ocr/tesseract_adapter.py": '"""Tesseract adapter (placeholder)."""\\n',
    "app/infrastructure/ocr/ocr_service_impl.py": '"""OCR service implementation (placeholder)."""\\n',
    "app/infrastructure/search/__init__.py": '"""Search infrastructure adapters."""\\n',
    "app/infrastructure/search/opensearch_client.py": '"""OpenSearch/Elasticsearch client wrapper (placeholder)."""\\n',
    "app/infrastructure/search/search_engine_impl.py": '"""Search engine implementation (placeholder)."""\\n',

    # --- interfaces/api ---
    "app/interfaces/api/__init__.py": '"""FastAPI application."""\\n',
    "app/interfaces/api/main.py": '"""FastAPI entrypoint (placeholder)."""\\n\\nfrom fastapi import FastAPI\\n\\n\\napp = FastAPI(title=\\\"CleverDocs\\\")\\n\\n\\n@app.get(\\\"/health\\\")\\ndef health():\\n    return {\\\"status\\\": \\\"ok\\\"}\\n',
    "app/interfaces/api/deps.py": '"""Dependency injection wiring (placeholder)."""\\n',
    "app/interfaces/api/middleware/__init__.py": '"""API middleware."""\\n',
    "app/interfaces/api/middleware/auth_middleware.py": '"""Authentication middleware (placeholder)."""\\n',
    "app/interfaces/api/middleware/tenant_context.py": '"""Tenant context resolver (placeholder)."""\\n',
    "app/interfaces/api/routes/__init__.py": '"""API routes."""\\n',
    "app/interfaces/api/routes/auth.py": '"""Auth routes (placeholder)."""\\n',
    "app/interfaces/api/routes/organizations.py": '"""Organization routes (placeholder)."""\\n',
    "app/interfaces/api/routes/documents.py": '"""Document routes (placeholder)."""\\n',
    "app/interfaces/api/routes/search.py": '"""Search routes (placeholder)."""\\n',
    "app/interfaces/api/schemas/__init__.py": '"""API schemas (DTOs)."""\\n',
    "app/interfaces/api/schemas/auth.py": '"""Auth schemas (placeholder)."""\\n',
    "app/interfaces/api/schemas/organizations.py": '"""Organization schemas (placeholder)."""\\n',
    "app/interfaces/api/schemas/documents.py": '"""Document schemas (placeholder)."""\\n',
    "app/interfaces/api/schemas/search.py": '"""Search schemas (placeholder)."""\\n',

    # --- projections ---
    "app/projections/search_projection_consumer.py": '"""Projection consumer: DocumentProcessed -> search index upsert (placeholder)."""\\n',
    "app/projections/search_reindex_consumer.py": '"""Projection consumer: DocumentReindexRequested -> index rebuild (placeholder)."""\\n',

    # --- workers ---
    "app/workers/ocr_worker.py": '"""Worker: consume DocumentUploaded -> OCR (placeholder)."""\\n',
    "app/workers/indexing_worker.py": '"""Worker: consume DocumentProcessed -> index (placeholder)."""\\n',

    # --- tests ---
    "tests/__init__.py": '"""Test suite root."""\\n',
}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    created = 0
    skipped = 0
    for rel, content in FILES.items():
        abs_path = ROOT / rel
        ensure_parent(abs_path)
        if abs_path.exists():
            skipped += 1
            continue
        abs_path.write_text(content, encoding="utf-8")
        created += 1
    print(f"Bootstrap done. created={created} skipped={skipped} root={ROOT}")


if __name__ == "__main__":
    main()

