"""Authorization policy rules (authZ) for use cases.

MVP: role-based checks on membership role strings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: str
    user_id: str
    role: str | None = None  # owner|admin|member|reader


class AuthorizationPolicy:
    ADMIN_ROLES = {"owner", "admin"}
    OWNER_ROLES = {"owner"}

    def is_admin(self, ctx: TenantContext) -> bool:
        return (ctx.role or "") in self.ADMIN_ROLES

    def is_owner(self, ctx: TenantContext) -> bool:
        return (ctx.role or "") in self.OWNER_ROLES

    def can_upload(self, ctx: TenantContext) -> bool:
        return (ctx.role or "") in {"owner", "admin", "member"}

    def can_read(self, ctx: TenantContext) -> bool:
        return (ctx.role or "") in {"owner", "admin", "member", "reader"}

    def can_admin_jobs(self, ctx: TenantContext) -> bool:
        return self.is_admin(ctx)

    def can_access_document(self, ctx: TenantContext, *, uploaded_by_user_id: str | None) -> bool:
        if self.is_admin(ctx):
            return True
        return uploaded_by_user_id is not None and uploaded_by_user_id == ctx.user_id

    def can_delete_organization(self, ctx: TenantContext) -> bool:
        return self.is_owner(ctx)

    def can_transfer_ownership(self, ctx: TenantContext) -> bool:
        return self.is_owner(ctx)
