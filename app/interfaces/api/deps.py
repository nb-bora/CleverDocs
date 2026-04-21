"""Dependency injection wiring.

On garde ça simple pour le MVP: Settings + DB session + storage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session

from app.infrastructure.db.session import SessionLocal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_name: str = "CleverDocs"
    app_log_level: str = "INFO"

    database_url: str = "sqlite:///./cleverdocs.db"

    storage_backend: str = "local"
    local_storage_dir: str = "storage"

    opensearch_url: str = "http://localhost:9200"
    opensearch_index_prefix: str = "cleverdocs"

    # OCR (EasyOCR)
    ocr_langs: str = "fr"  # comma-separated (e.g. "fr,en")
    ocr_gpu: bool = False
    ocr_pdf_max_pages: int = 20
    ocr_pdf_zoom: float = 2.0

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass(frozen=True)
class LocalStorage:
    root_dir: Path

    def ensure(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)


def get_local_storage(settings: Settings = None) -> LocalStorage:
    s = settings or get_settings()
    root_dir = Path(s.local_storage_dir)
    return LocalStorage(root_dir=root_dir)

