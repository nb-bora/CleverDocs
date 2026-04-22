"""User API schemas (MVP)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    id: str
    email: EmailStr
    display_name: str | None = None
    avatar_storage_key: str | None = None
    status: str


class CreateUserRequest(BaseModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=255)


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

