"""EventPublisher port (publish domain events)."""


class EventPublisher:
    def publish(self, event) -> None:
        raise NotImplementedError
