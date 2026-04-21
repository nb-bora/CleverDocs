"""Use case: archive document.

MVP: not implemented yet (needs domain rules + storage/index behavior).
"""

from __future__ import annotations

from app.application.commands.archive_document import ArchiveDocument


def handle_archive_document(*, cmd: ArchiveDocument) -> None:
    raise NotImplementedError("Archive use case not implemented in MVP yet")
