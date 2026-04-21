"""Helper: require a permission for a use case (MVP)."""

from __future__ import annotations

from app.domain.identity.services.authorization_policy import AuthorizationPolicy, TenantContext


class PermissionDenied(RuntimeError):
    pass


def require_upload(ctx: TenantContext, policy: AuthorizationPolicy | None = None) -> None:
    p = policy or AuthorizationPolicy()
    if not p.can_upload(ctx):
        raise PermissionDenied("UPLOAD_FORBIDDEN")


def require_read(ctx: TenantContext, policy: AuthorizationPolicy | None = None) -> None:
    p = policy or AuthorizationPolicy()
    if not p.can_read(ctx):
        raise PermissionDenied("READ_FORBIDDEN")
