"""UserRepository port (interface)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.identity.entities.user import User


class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...
