"""SQLAlchemy declarative base.

L'infrastructure DB vit ici (pas dans le domain). Les modèles ORM utiliseront `Base`.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

