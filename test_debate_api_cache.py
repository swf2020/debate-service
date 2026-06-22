"""
Integration tests for debate API with Redis cache layer.
"""
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Temp file DB so multiple connections share the same data
_tmp_dir = tempfile.mkdtemp(prefix="debate_test_")
TEST_DB_PATH = Path(_tmp_dir) / "test.db"

os.environ["DEBATE_DB_PATH"] = str(TEST_DB_PATH)
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-cache-tests"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _register(client: TestClient, username: str | None = None) -> str:
    """Register a test user and return JWT token."""
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": "testpass"},
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def _create(client: TestClient, token: str, topic: str = "Test topic") -> str:
    """Create a debate and return its ID."""
    resp = client.post(
        "/api/debate/start",
        json={
            "topic": topic, "rounds": 1, "format": "cdwc",
            "pro_skills": {"debater_1": None, "debater_2": None, "debater_3": None, "debater_4": None},
            "con_skills": {"debater_1": None, "debater_2": None, "debater_3": None, "debater_4": None},
            "judge_skill": None,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return resp.json()["debate_id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Fixture: import app lazily so env vars are set first ────────────────────


@pytest.fixture(scope="module")
def client():
    """Create a TestClient that enters the app lifespan (init_db, etc.)."""
    from main import app
    with TestClient(app) as c:
        yield c


# ── Tests: Batch endpoint ───────────────────────────────────────────────────


class TestBatchEndpoint:
    """GET /api/debate/speeches/batch"""

    def test_returns_200_with_valid_auth(self, client):
        token = _register(client)
        resp = client.get("/api/debate/speeches/batch?ids=id1,id2", headers=_auth(token))
        assert resp.status_code == 200
        assert "speeches" in resp.json()

    def test_requires_auth(self, client):
        resp = client.get("/api/debate/speeches/batch?ids=id1")
        assert resp.status_code == 401

    def test_empty_ids(self, client):
        token = _register(client)
        resp = client.get("/api/debate/speeches/batch?ids=", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == {"speeches": {}}

    def test_no_ids_param(self, client):
        token = _register(client)
        resp = client.get("/api/debate/speeches/batch", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == {"speeches": {}}


# ── Tests: Debate detail ────────────────────────────────────────────────────


class TestDebateDetail:
    """GET /api/debate/{id}"""

    def test_returns_speeches(self, client):
        token = _register(client)
        debate_id = _create(client, token)

        resp = client.get(f"/api/debate/{debate_id}", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "speeches" in data
        assert isinstance(data["speeches"], list)

    def test_not_found(self, client):
        token = _register(client)
        resp = client.get("/api/debate/nonexistent-id", headers=_auth(token))
        assert resp.status_code == 404


# ── Tests: Delete ───────────────────────────────────────────────────────────


class TestDelete:
    """DELETE /api/debate/{id}"""

    def test_delete_works(self, client):
        token = _register(client)
        debate_id = _create(client, token)

        resp = client.delete(f"/api/debate/{debate_id}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        resp2 = client.get(f"/api/debate/{debate_id}", headers=_auth(token))
        assert resp2.status_code == 404

    def test_not_found(self, client):
        token = _register(client)
        resp = client.delete("/api/debate/nonexistent", headers=_auth(token))
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.delete("/api/debate/some-id")
        assert resp.status_code == 401


# ── Tests: Redis integration ────────────────────────────────────────────────


class TestRedisIntegration:
    """Verify Redis cache is called during debate lifecycle."""

    def test_batch_endpoint_uses_redis(self, client):
        """Batch endpoint calls Redis get_batch_summaries."""
        mock_cache = MagicMock()
        mock_cache.enabled = True
        mock_cache.get_batch_summaries = AsyncMock(return_value={
            "d1": [{"debater": "pro_1", "content": "Hi"}],
            "d2": [{"debater": "con_1", "content": "No"}],
        })

        token = _register(client)
        with patch("main.get_redis", return_value=mock_cache):
            resp = client.get("/api/debate/speeches/batch?ids=d1,d2", headers=_auth(token))

        assert resp.status_code == 200
        data = resp.json()
        assert "d1" in data["speeches"]
        assert "d2" in data["speeches"]
        assert data["speeches"]["d1"][0]["content"] == "Hi"

    def test_batch_endpoint_falls_back_to_sqlite(self, client):
        """When Redis misses all, batch endpoint falls back to SQLite."""
        mock_cache = MagicMock()
        mock_cache.enabled = True
        mock_cache.get_batch_summaries = AsyncMock(return_value=None)

        token = _register(client)
        debate_id = _create(client, token)

        with patch("main.get_redis", return_value=mock_cache):
            resp = client.get(
                f"/api/debate/speeches/batch?ids={debate_id}",
                headers=_auth(token),
            )

        assert resp.status_code == 200
        assert "speeches" in resp.json()

    def test_delete_invalidates_cache(self, client):
        """Delete debate calls invalidate_debate on Redis cache."""
        mock_cache = MagicMock()
        mock_cache.enabled = True
        mock_cache.invalidate_debate = AsyncMock()

        token = _register(client)
        debate_id = _create(client, token)

        with patch("main.get_redis", return_value=mock_cache):
            resp = client.delete(f"/api/debate/{debate_id}", headers=_auth(token))

        assert resp.status_code == 200
        mock_cache.invalidate_debate.assert_called_once_with(debate_id)
