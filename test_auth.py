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
os.environ["ADMIN_USERS"] = "admin"

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
        resp = client.post("/api/auth/register", json={
            "username": "admin", "password": "admin123"
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
