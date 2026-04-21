"""EventPublisher port (publish domain events)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.common.events import DomainEvent


class EventPublisher(ABC):
    @abstractmethod
    def publish(self, event: DomainEvent) -> None: ...


class InMemoryEventPublisher(EventPublisher):
    """MVP publisher: stores events in memory (useful for tests/dev)."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)
