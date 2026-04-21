"""UnitOfWork port (transaction boundary)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class UnitOfWork(ABC):
    """Transaction boundary + access to repositories.

    In MVP, we keep this sync.
    """

    def __enter__(self) -> "UnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            try:
                self.rollback()
            except Exception:
                pass
        return False

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
