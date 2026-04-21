"""Authorization policy rules (authZ) for use cases.

MVP: role-based checks on membership role strings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: str
    user_id: str | None
    role: str | None = None  # owner|admin|member|reader


class AuthorizationPolicy:
    def can_upload(self, ctx: TenantContext) -> bool:
        return (ctx.role or "") in {"owner", "admin", "member"}

    def can_read(self, ctx: TenantContext) -> bool:
        return (ctx.role or "") in {"owner", "admin", "member", "reader"}

    def can_admin_jobs(self, ctx: TenantContext) -> bool:
        return (ctx.role or "") in {"owner", "admin"}
