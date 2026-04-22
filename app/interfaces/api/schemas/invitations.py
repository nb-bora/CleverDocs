"""Invitation schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class CreateInvitationRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member", min_length=1, max_length=32)


class InvitationOut(BaseModel):
    id: str
    organization_id: str
    email: EmailStr
    role: str
    expires_at: str
    accepted_at: str | None = None
    revoked_at: str | None = None


class CreateInvitationResponse(BaseModel):
    invitation: InvitationOut
    token: str


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=2048)
    display_name: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=256)

