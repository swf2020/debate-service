"""
Tests for main.py FastAPI application.

Mocks the Flow and LLM to avoid actual agent execution.
Uses a temporary SQLite database and patches DB functions where needed.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Set up test environment BEFORE importing the app module
# ---------------------------------------------------------------------------

_tmp_db = tempfile.mktemp(suffix=".debate_test.db")
os.environ["DEBATE_DB_PATH"] = _tmp_db
# Provide a dummy API key so LLM construction doesn't blow up if it's ever
# reached (though all Flow/agent calls are mocked in these tests).
os.environ["DEEPSEEK_API_KEY"] = "test-key-mock"

from debate_flow import _active_flows
from sse_bridge import sse_bridge

# Import the app after env vars are set so the lifespan sees the test DB path.
from main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_cleanup():
    """Reset global state between every test."""
    yield
    _active_flows.clear()
    sse_bridge._queues.clear()
    sse_bridge._loop = None


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient -- created once per module."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


class TestIndex:
    def test_index_returns_html(self, client):
        """GET / returns an HTML page."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_index_fallback_content(self, client):
        """Without static/index.html the fallback HTML is returned."""
        response = client.get("/")
        assert "Debate Service" in response.text


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestSkills:
    def test_get_skills_returns_list(self, client):
        """GET /api/skills returns a JSON list of available skills."""
        response = client.get("/api/skills")
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert isinstance(data["skills"], list)


# ---------------------------------------------------------------------------
# Start debate
# ---------------------------------------------------------------------------


class TestStartDebate:
    @patch("main.create_debate")  # async, patched as AsyncMock
    @patch("main.DebateFlow")
    @patch("main.asyncio.create_task")
    def test_start_creates_debate_and_returns_id(
        self, mock_create_task, mock_flow_cls, mock_create_db, client
    ):
        """POST /api/debate/start persists a debate and returns debate_id."""
        mock_create_db.side_effect = AsyncMock()
        mock_flow = MagicMock()
        mock_flow.state = MagicMock()
        mock_flow_cls.return_value = mock_flow
        mock_create_task.return_value = None

        payload = {"topic": "人工智能是否对人类有益", "rounds": 2}
        response = client.post("/api/debate/start", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "debate_id" in data
        assert data["status"] == "running"
        # Verify the debate was persisted
        mock_create_db.assert_called_once()

    @patch("main.create_debate")
    @patch("main.DebateFlow")
    @patch("main.asyncio.create_task")
    def test_start_with_skills(
        self, mock_create_task, mock_flow_cls, mock_create_db, client
    ):
        """Skills configs are accepted in the request body."""
        mock_create_db.side_effect = AsyncMock()
        mock_flow = MagicMock()
        mock_flow.state = MagicMock()
        mock_flow_cls.return_value = mock_flow
        mock_create_task.return_value = None

        payload = {
            "topic": "AI safety",
            "rounds": 2,
            "pro_skills": {"debater_1": "munger-perspective", "debater_2": "skill-b"},
            "con_skills": {"debater_1": "skill-c"},
            "judge_skill": "judge-perspective",
        }
        response = client.post("/api/debate/start", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "debate_id" in data


# ---------------------------------------------------------------------------
# Get debate detail
# ---------------------------------------------------------------------------


class TestGetDebate:
    @patch("main.get_debate")
    @patch("main.get_speeches")
    def test_get_detail(self, mock_speeches, mock_debate, client):
        """GET /api/debate/{id} returns debate with speeches."""
        mock_debate.side_effect = AsyncMock(return_value={
            "id": "deb-001",
            "topic": "test",
            "total_rounds": 2,
            "status": "running",
            "pro_skills": {},
            "con_skills": {},
            "judge_skill": None,
            "winner": None,
            "verdict": None,
            "created_at": "2025-01-01 00:00:00",
            "finished_at": None,
        })
        mock_speeches.side_effect = AsyncMock(return_value=[])

        response = client.get("/api/debate/deb-001")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "deb-001"
        assert "speeches" in data
        assert isinstance(data["speeches"], list)

    @patch("main.get_debate")
    def test_get_detail_not_found(self, mock_debate, client):
        """GET /api/debate/{id} returns 404 for non-existent debate."""
        mock_debate.side_effect = AsyncMock(return_value=None)

        response = client.get("/api/debate/nonexistent")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Pause
# ---------------------------------------------------------------------------


class TestPause:
    def test_pause_not_found(self, client):
        """POST /api/debate/{id}/pause returns 404 for non-existent debate."""
        response = client.post("/api/debate/nonexistent/pause")
        assert response.status_code == 404

    @patch("main.update_debate_status")
    def test_pause_existing(self, mock_update, client):
        """Pause sets the paused flag and updates DB status."""
        mock_update.side_effect = AsyncMock()

        mock_flow = MagicMock()
        mock_flow.state = MagicMock()
        mock_flow.state.paused = False
        _active_flows["deb-pause"] = mock_flow

        response = client.post("/api/debate/deb-pause/pause")
        assert response.status_code == 200
        assert response.json() == {"status": "paused"}
        assert mock_flow.state.paused is True
        mock_update.assert_called_once_with("deb-pause", "paused")


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_not_found(self, client):
        """POST /api/debate/{id}/resume returns 404 for non-existent debate."""
        response = client.post("/api/debate/nonexistent/resume")
        assert response.status_code == 404

    @patch("main.update_debate_status")
    def test_resume_existing(self, mock_update, client):
        """Resume clears the paused flag and updates DB status."""
        mock_update.side_effect = AsyncMock()

        mock_flow = MagicMock()
        mock_flow.state = MagicMock()
        mock_flow.state.paused = True
        _active_flows["deb-resume"] = mock_flow

        response = client.post("/api/debate/deb-resume/resume")
        assert response.status_code == 200
        assert response.json() == {"status": "running"}
        assert mock_flow.state.paused is False
        mock_update.assert_called_once_with("deb-resume", "running")


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


class TestStream:
    @patch("main.get_debate")
    def test_stream_not_found(self, mock_debate, client):
        """GET /api/debate/{id}/stream returns 404 for non-existent debate."""
        mock_debate.side_effect = AsyncMock(return_value=None)

        response = client.get("/api/debate/nonexistent/stream")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_rounds_zero(self, client):
        """rounds=0 is rejected (minimum 1)."""
        response = client.post(
            "/api/debate/start",
            json={"topic": "test", "rounds": 0},
        )
        assert response.status_code == 400

    def test_invalid_rounds_negative(self, client):
        """rounds=-1 is rejected."""
        response = client.post(
            "/api/debate/start",
            json={"topic": "test", "rounds": -1},
        )
        assert response.status_code == 400

    def test_invalid_rounds_too_large(self, client):
        """rounds=5 is rejected (max 3)."""
        response = client.post(
            "/api/debate/start",
            json={"topic": "test", "rounds": 5},
        )
        assert response.status_code == 400

    def test_missing_topic(self, client):
        """Omitting topic returns 400."""
        response = client.post(
            "/api/debate/start",
            json={"rounds": 2},
        )
        assert response.status_code == 400

    def test_empty_json(self, client):
        """Empty body returns 400."""
        response = client.post("/api/debate/start", json={})
        assert response.status_code == 400

    def test_non_json_body(self, client):
        """Non-JSON body returns 400."""
        response = client.post(
            "/api/debate/start",
            data=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
