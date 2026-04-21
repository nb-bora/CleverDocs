"""Use case: add document version.

MVP: not implemented yet (needs versioning model + storage rules + reprocessing).
"""

from __future__ import annotations

from app.application.commands.add_document_version import AddDocumentVersion


def handle_add_document_version(*, cmd: AddDocumentVersion) -> None:
    raise NotImplementedError("Document versioning use case not implemented in MVP yet")
