#!/usr/bin/env sh
set -eu

export APP_ENV="${APP_ENV:-prod}"
export APP_HOST="${APP_HOST:-0.0.0.0}"
export APP_PORT="${APP_PORT:-7860}"

# Hugging Face Spaces provides a persistent volume at /data.
# Keep DB + uploaded files there by default.
export DATABASE_URL="${DATABASE_URL:-sqlite:////data/cleverdocs.db}"
export LOCAL_STORAGE_DIR="${LOCAL_STORAGE_DIR:-/data/storage}"

mkdir -p "$LOCAL_STORAGE_DIR"

# Best-effort: if alembic isn't configured in the Space repo, don't block startup.
python -m alembic upgrade head || true

exec python -m uvicorn app.interfaces.api.main:app --host "$APP_HOST" --port "$APP_PORT"

