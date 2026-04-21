"""Document status value object.

This defines the write-model lifecycle states for a Document aggregate.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    uploaded = "uploaded"
    processing = "processing"
    processed = "processed"

    indexing_pending = "indexing_pending"
    indexed = "indexed"
    indexing_failed = "indexing_failed"

    failed = "failed"
