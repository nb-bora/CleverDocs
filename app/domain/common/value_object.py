"""Base ValueObject types for the domain layer (immutable by convention)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValueObject:
    """Marker base class for Value Objects."""
