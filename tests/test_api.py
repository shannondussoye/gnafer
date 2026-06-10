"""Tests for the API endpoints."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models import MatchResult


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
        yield TestClient(app, raise_server_exceptions=False), mock_matcher, mock_verifier


def test_health_check(client):
    test_client, _, _ = client
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_geocode_single_success(client):
    test_client, mock_matcher, _mock_verifier = client
    mock_matcher.match.return_value = MatchResult(
        input_address="123 George St, Sydney, NSW 2000",
        similarity_score=1.0,
        address_detail_pid="pid123",
        address_label="123 GEORGE ST, SYDNEY NSW 2000",
    )

    response = test_client.post("/geocode", json={"address": "123 George St, Sydney, NSW 2000"})
    assert response.status_code == 200
    data = response.json()
    assert data["similarity_score"] == 1.0
    assert data["match_method"] == "TRIGRAM"


def test_geocode_single_not_found(client):
    test_client, mock_matcher, _ = client
    mock_matcher.match.return_value = MatchResult(
        input_address="not a real address",
        similarity_score=0.0,
    )

    response = test_client.post("/geocode", json={"address": "not a real address"})
    assert response.status_code == 404


def test_batch_returns_job_id(client):
    test_client, mock_matcher, _ = client
    mock_matcher.match_batch.return_value = [
        MatchResult(input_address="addr1", similarity_score=1.0),
    ]

    response = test_client.post("/geocode/batch", json={"addresses": ["addr1"]})
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_job_not_found(client):
    test_client, _, _ = client
    response = test_client.get("/jobs/invalid_id")
    assert response.status_code == 404


def test_process_batch_completes_successfully():
    mock_matcher = MagicMock()
    mock_verifier = MagicMock()
    mock_obs = MagicMock()

    mock_matcher.match_batch.return_value = [
        MatchResult(input_address="addr1", similarity_score=1.0, address_detail_pid="pid1"),
        MatchResult(input_address="addr2", similarity_score=0.85, address_detail_pid="pid2"),
    ]

    mock_verifier.check_available = AsyncMock(return_value=True)
    mock_verifier.verify_batch_async = AsyncMock(return_value=[True])

    with (
        patch("src.api._matcher", mock_matcher),
        patch("src.api._verifier", mock_verifier),
        patch("src.api._obs", mock_obs),
        patch.dict("src.api.jobs", clear=True),
    ):
        from src.api import _process_batch, jobs

        job_id = "test-job"
        jobs[job_id] = {
            "status": "processing",
            "total": 2,
            "processed": 0,
            "successful": 0,
            "results": [],
            "created_at": 0,
        }

        asyncio.run(_process_batch(job_id, ["addr1", "addr2"]))

        assert jobs[job_id]["status"] == "completed"
        assert jobs[job_id]["successful"] == 2
        assert len(jobs[job_id]["results"]) == 2
        mock_matcher.match_batch.assert_called_once()
        mock_verifier.verify_batch_async.assert_called_once()


def test_process_batch_handles_match_failure():
    mock_matcher = MagicMock()
    mock_verifier = MagicMock()
    mock_obs = MagicMock()

    mock_matcher.match_batch.side_effect = RuntimeError("DB error")

    with (
        patch("src.api._matcher", mock_matcher),
        patch("src.api._verifier", mock_verifier),
        patch("src.api._obs", mock_obs),
        patch.dict("src.api.jobs", clear=True),
    ):
        from src.api import _process_batch, jobs

        job_id = "fail-job"
        jobs[job_id] = {
            "status": "processing",
            "total": 1,
            "processed": 0,
            "successful": 0,
            "results": [],
            "created_at": 0,
        }

        asyncio.run(_process_batch(job_id, ["addr1"]))

        assert jobs[job_id]["status"] == "failed"
        assert "completed_at" in jobs[job_id]
