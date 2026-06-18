"""Tests for Supabase batch API endpoints."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config import settings


@pytest.fixture
def client():
    """Create a test client with mocked dependencies."""
    mock_pool = MagicMock()
    mock_matcher = MagicMock()
    mock_verifier = MagicMock()
    mock_obs = MagicMock()

    with (
        patch("src.api._pool", mock_pool),
        patch("src.api._matcher", mock_matcher),
        patch("src.api._verifier", mock_verifier),
        patch("src.api._obs", mock_obs),
    ):
        from src.api import app
        yield TestClient(app, raise_server_exceptions=False)


class TestSupabaseBatchEndpoint:
    def test_returns_job_id_when_configured(self, client):
        with (
            patch.object(settings, "supabase_url", "https://test.supabase.co"),
            patch.object(settings, "supabase_key", "test-key"),
        ):
            response = client.post("/geocode/supabase-batch", json={"limit": 100})

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["message"] == "Supabase batch job started"

    def test_returns_503_when_not_configured(self, client):
        with (
            patch.object(settings, "supabase_url", ""),
            patch.object(settings, "supabase_key", ""),
        ):
            response = client.post("/geocode/supabase-batch", json={"limit": 0})

        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()

    def test_returns_429_when_job_store_full(self, client):
        with (
            patch.object(settings, "supabase_url", "https://test.supabase.co"),
            patch.object(settings, "supabase_key", "test-key"),
            patch.object(settings, "job_max_store_size", 1),
            patch.dict("src.api.jobs", {"existing": {"status": "processing"}}, clear=True),
        ):
            response = client.post("/geocode/supabase-batch", json={"limit": 0})

        assert response.status_code == 429
        assert "full" in response.json()["detail"].lower()


class TestProcessSupabaseBatch:
    def test_completes_successfully(self):
        with (
            patch("src.api.run_supabase_batch") as mock_run,
            patch.dict("src.api.jobs", clear=True),
        ):
            from src.api import _process_supabase_batch, jobs

            mock_run.return_value = {
                "total": 10,
                "success": 8,
                "failed": 2,
                "verified": 1,
            }

            job_id = "sb-test"
            jobs[job_id] = {
                "status": "processing",
                "total": 0,
                "processed": 0,
                "successful": 0,
                "results": [],
                "created_at": 0,
            }

            asyncio.run(_process_supabase_batch(job_id, 100))

            assert jobs[job_id]["status"] == "completed"
            assert jobs[job_id]["processed"] == 10
            assert jobs[job_id]["successful"] == 8
            mock_run.assert_awaited_once_with(workers=settings.trigram_workers, limit=100)

    def test_handles_failure(self):
        with (
            patch("src.api.run_supabase_batch") as mock_run,
            patch.dict("src.api.jobs", clear=True),
        ):
            from src.api import _process_supabase_batch, jobs

            mock_run.side_effect = RuntimeError("Supabase down")

            job_id = "sb-fail"
            jobs[job_id] = {
                "status": "processing",
                "total": 0,
                "processed": 0,
                "successful": 0,
                "results": [],
                "created_at": 0,
            }

            asyncio.run(_process_supabase_batch(job_id, 0))

            assert jobs[job_id]["status"] == "failed"
            assert "completed_at" in jobs[job_id]
