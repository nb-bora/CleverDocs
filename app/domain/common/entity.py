"""Base Entity types for the domain layer."""


class Entity:
    def __init__(self, entity_id: str) -> None:
        self.id = entity_id
