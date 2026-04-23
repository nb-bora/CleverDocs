from __future__ import annotations

import importlib
import os
import uuid

from fastapi.testclient import TestClient
from passlib.context import CryptContext


def _build_app():
    # Use a unique DB file per test to avoid Windows file locks.
    db_name = f"test_smoke_{uuid.uuid4().hex}.db"
    os.environ["DATABASE_URL"] = f"sqlite:///./{db_name}"
    os.environ["APP_ENV"] = "dev"

    import app.interfaces.api.main as main_mod

    importlib.reload(main_mod)
    # Ensure schema exists (startup is not always triggered in tests).
    main_mod._startup_create_tables()
    return main_mod.app


def _seed_org_and_user(*, organization_name: str, user_email: str, user_display_name: str, role: str, password: str) -> str:
    """Seed org+user+membership directly in DB for tests."""
    from app.infrastructure.db.session import SessionLocal
    from app.infrastructure.db.orm.models.membership_model import MembershipModel
    from app.infrastructure.db.orm.models.organization_model import OrganizationModel
    from app.infrastructure.db.orm.models.user_model import UserModel

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    membership_id = str(uuid.uuid4())

    db = SessionLocal()
    try:
        user = UserModel(
            id=user_id,
            email=str(user_email).lower(),
            display_name=user_display_name,
            password_hash=pwd_context.hash(password),
            status="active",
        )
        org = OrganizationModel(id=org_id, name=organization_name, owner_user_id=user_id, status="active")
        membership = MembershipModel(
            id=membership_id,
            user_id=user_id,
            organization_id=org_id,
            role=role,
            status="active",
        )
        db.add_all([user, org, membership])
        db.commit()
        return org_id
    finally:
        db.close()


def test_login_and_me_and_tenant_access() -> None:
    app = _build_app()
    with TestClient(app) as c:

        org_id = _seed_org_and_user(
            organization_name="acme",
            user_email="alice@example.com",
            user_display_name="Alice",
            role="owner",
            password="super-secret-123",
        )

        # Login returns JWT access + refresh.
        login = c.post(
            "/v1/auth/login", json={"email": "alice@example.com", "password": "super-secret-123"}
        )
        assert login.status_code == 200
        tokens = login.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens

        headers = {"Authorization": f"Bearer {tokens['access_token']}", "X-Org-Id": org_id}

        me = c.get("/v1/auth/me", headers={"Authorization": headers["Authorization"]})
        assert me.status_code == 200
        assert me.json()["email"] == "alice@example.com"

        # Tenant-protected route should work with JWT + X-Org-Id.
        orgs = c.get("/v1/organizations", headers={"Authorization": headers["Authorization"]})
        assert orgs.status_code == 200
        assert isinstance(orgs.json(), list)

        docs = c.get("/v1/documents", headers=headers)
        assert docs.status_code == 200


def test_search_requires_auth() -> None:
    app = _build_app()
    with TestClient(app) as c:
        r = c.get("/v1/search", params={"q": "x"})
        assert r.status_code in (401, 403, 400)


def test_owner_cannot_be_removed_or_demoted_and_transfer_works() -> None:
    app = _build_app()
    with TestClient(app) as c:
        org_id = _seed_org_and_user(
            organization_name="org2",
            user_email="owner@example.com",
            user_display_name="Owner",
            role="owner",
            password="super-secret-123",
        )

        login = c.post(
            "/v1/auth/login", json={"email": "owner@example.com", "password": "super-secret-123"}
        )
        access = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {access}", "X-Org-Id": org_id}

        # Add a member
        add = c.post(
            f"/v1/organizations/{org_id}/members",
            headers=headers,
            json={"user_email": "bob@example.com", "role": "member"},
        )
        assert add.status_code == 200
        bob_user_id = add.json()["user_id"]

        # List members -> find owner membership id
        members = c.get(f"/v1/organizations/{org_id}/members", headers=headers).json()
        owner_membership = next(m for m in members if m["role"] == "owner")

        # Can't demote owner
        demote = c.patch(
            f"/v1/organizations/{org_id}/members/{owner_membership['id']}",
            headers=headers,
            json={"role": "admin"},
        )
        assert demote.status_code == 409

        # Can't remove owner
        rem = c.delete(
            f"/v1/organizations/{org_id}/members/{owner_membership['id']}",
            headers=headers,
        )
        assert rem.status_code == 409

        # Transfer ownership to Bob
        tr = c.post(
            f"/v1/organizations/{org_id}/transfer_ownership",
            headers=headers,
            json={"new_owner_user_id": bob_user_id},
        )
        assert tr.status_code == 200

        # Now Bob is owner
        members2 = c.get(f"/v1/organizations/{org_id}/members", headers=headers).json()
        assert any(m["user_id"] == bob_user_id and m["role"] == "owner" for m in members2)
        assert any(m["user_id"] == owner_membership["user_id"] and m["role"] == "admin" for m in members2)

