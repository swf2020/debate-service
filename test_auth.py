"""
Tests for auth module and auth endpoints.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

_tmp_db = tempfile.mktemp(suffix=".auth_test.db")
os.environ["DEBATE_DB_PATH"] = _tmp_db
os.environ["DEEPSEEK_API_KEY"] = "test-key-mock"
os.environ["ADMIN_USERS"] = "admin,root"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-testing"

from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestRegister:
    def test_register_new_user(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "alice", "password": "secret123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "alice"
        assert data["user"]["is_admin"] is False

    def test_register_admin_user(self, client):
        """A user listed in ADMIN_USERS env var becomes admin on registration."""
        resp = client.post("/api/auth/register", json={
            "username": "root", "password": "root1234"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["is_admin"] is True

    def test_register_duplicate(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "alice", "password": "another"
        })
        assert resp.status_code == 409

    def test_register_short_username(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "a", "password": "password"
        })
        assert resp.status_code == 400

    def test_register_short_password(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "charlie", "password": "ab"
        })
        assert resp.status_code == 400


class TestLogin:
    def test_login_success(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "secret123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "alice"

    def test_login_wrong_password(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "wrongpass"
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "nobody", "password": "whatever"
        })
        assert resp.status_code == 401


class TestDefaultAdmin:
    def test_default_admin_login(self, client):
        """The default admin account (admin/1234) seeded by init_db can log in."""
        resp = client.post("/api/auth/login", json={
            "username": "admin", "password": "1234"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["is_admin"] is True

    def test_default_admin_wrong_password(self, client):
        """Default admin login with wrong password returns 401."""
        resp = client.post("/api/auth/login", json={
            "username": "admin", "password": "wrong"
        })
        assert resp.status_code == 401


class TestMe:
    def test_me_with_valid_token(self, client):
        # Register to get a token
        reg = client.post("/api/auth/register", json={
            "username": "bob", "password": "bob1234"
        })
        token = reg.json()["token"]

        resp = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "bob"

    def test_me_without_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self, client):
        resp = client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid.token.here"
        })
        assert resp.status_code == 401


class TestAdminPageAccess:
    """Non-admin users must NOT see the admin panel page (and link)."""

    @staticmethod
    def _unique_username(prefix: str = "user") -> str:
        import uuid as _uuid
        return f"{prefix}_{_uuid.uuid4().hex[:8]}"

    def test_admin_page_redirects_unauthenticated(self, client):
        """GET /admin without a token must return 401, not the admin page."""
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated /admin, got {resp.status_code}"
        )

    def test_admin_page_forbidden_for_non_admin(self, client):
        """A non-admin user must get 403 when accessing /admin."""
        reg = client.post("/api/auth/register", json={
            "username": self._unique_username("normal_user"),
            "password": "test1234"
        })
        assert reg.status_code == 200, f"Register failed: {reg.json()}"
        token = reg.json()["token"]

        resp = client.get("/admin", headers={
            "Authorization": f"Bearer {token}"
        }, follow_redirects=False)
        assert resp.status_code in (401, 403), (
            f"Expected 401/403 for non-admin /admin, got {resp.status_code}"
        )

    def test_admin_page_accessible_for_admin(self, client):
        """An admin user must be able to access /admin."""
        resp = client.post("/api/auth/login", json={
            "username": "admin", "password": "1234"
        })
        token = resp.json()["token"]

        resp = client.get("/admin", headers={
            "Authorization": f"Bearer {token}"
        }, follow_redirects=False)
        assert resp.status_code == 200, (
            f"Expected 200 for admin /admin, got {resp.status_code}"
        )

    def test_non_admin_register_has_is_admin_false(self, client):
        """Non-admin user registered without ADMIN_USERS must have is_admin=False."""
        resp = client.post("/api/auth/register", json={
            "username": self._unique_username("regular_joe"),
            "password": "joe12345"
        })
        assert resp.status_code == 200, f"Register failed: {resp.json()}"
        data = resp.json()
        assert data["user"]["is_admin"] is False, (
            f"Non-admin user is_admin should be False, got {data['user']['is_admin']}"
        )

    def test_admin_user_has_is_admin_true_in_me(self, client):
        """The /api/auth/me endpoint must return is_admin=True for admin users."""
        resp = client.post("/api/auth/login", json={
            "username": "admin", "password": "1234"
        })
        token = resp.json()["token"]

        resp = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        assert resp.json()["user"]["is_admin"] is True


class TestJWTTokenPersistence:
    """JWT tokens must survive server restarts — JWT_SECRET_KEY must be persistent."""

    def test_jwt_secret_key_is_configured(self):
        """JWT_SECRET_KEY must be set in environment for token persistence."""
        import auth as auth_module

        env_key = os.environ.get("JWT_SECRET_KEY")
        assert env_key, (
            "JWT_SECRET_KEY not set in environment! "
            "Without it, auth module generates a random key on every restart, "
            "invalidating all previously issued tokens."
        )
        assert auth_module.JWT_SECRET_KEY == env_key, (
            "auth.JWT_SECRET_KEY does not match JWT_SECRET_KEY env var"
        )

    def test_token_works_across_simulated_restart(self, client):
        """A token issued before restart must work after restart (same signing key)."""
        import auth as auth_module

        # Issue a token
        token = auth_module.create_access_token("user-99", "testuser", False)

        # Decode it — simulates "after restart" verification with same key
        payload = auth_module.decode_access_token(token)
        assert payload["sub"] == "user-99"
        assert payload["username"] == "testuser"
        assert payload["is_admin"] is False

        # Also verify via endpoint
        resp = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        # Token for non-existent user — 401 is expected (user not in DB),
        # but NOT "Invalid token" which would mean key mismatch
        assert resp.status_code != 401 or resp.json().get("detail") != "Invalid token", (
            "Token rejected as invalid — JWT_SECRET_KEY likely changed between sign and verify"
        )

    def test_registered_user_token_works_for_debate_start(self, client):
        """Token from registration must work for protected endpoints like /api/debate/start."""
        import uuid as _uuid
        username = f"debater_{_uuid.uuid4().hex[:8]}"

        reg = client.post("/api/auth/register", json={
            "username": username, "password": "test1234"
        })
        assert reg.status_code == 200, f"Register failed: {reg.json()}"
        token = reg.json()["token"]

        # Token must work for /api/debate/start (the endpoint from the bug report)
        resp = client.post("/api/debate/start", json={
            "topic": "测试辩题",
            "rounds": 1,
            "pro_skills": {"debater_1": None, "debater_2": None, "debater_3": None},
            "con_skills": {"debater_1": None, "debater_2": None, "debater_3": None},
            "judge_skill": None,
        }, headers={"Authorization": f"Bearer {token}"})
        # Should be 200 (debate created), NOT 401 "Invalid token"
        assert resp.status_code == 200, (
            f"Expected 200 for /api/debate/start with valid token, "
            f"got {resp.status_code}: {resp.json()}"
        )
