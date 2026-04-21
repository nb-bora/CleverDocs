"""User API schemas (MVP)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    id: str
    email: EmailStr
    display_name: str | None = None
    status: str


class CreateUserRequest(BaseModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=255)

