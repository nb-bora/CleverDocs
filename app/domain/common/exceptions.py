"""Domain exceptions (invariant violations, invalid transitions)."""

from __future__ import annotations


class DomainError(Exception):
    """Base error for domain invariants."""


class InvariantViolation(DomainError):
    pass


class InvalidTransition(DomainError):
    pass
