"""Event bus adapter (MVP).

For now, we keep the outbox dispatcher operational without an external broker by
considering "publish" as a no-op. Later versions can plug Kafka/SQS/RabbitMQ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PublishedEvent:
    event_type: str
    payload: dict[str, Any]
    organization_id: str | None = None


class EventBus:
    def publish(self, ev: PublishedEvent) -> None:
        # No-op MVP: outbox still provides transactional auditability/replay later.
        return
