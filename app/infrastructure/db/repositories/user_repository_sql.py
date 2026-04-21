"""SQL implementation of UserRepository (MVP)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.user_model import UserModel


@dataclass(frozen=True)
class UserRepositorySql:
    db: Session

    def get(self, user_id: str) -> UserModel | None:
        return self.db.get(UserModel, user_id)

    def get_by_email(self, email: str) -> UserModel | None:
        return (
            self.db.execute(select(UserModel).where(UserModel.email == email.lower()))
            .scalars()
            .first()
        )

    def add(self, user: UserModel) -> None:
        self.db.add(user)
