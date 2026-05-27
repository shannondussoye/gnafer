"""Tests for the API endpoints."""

from unittest.mock import MagicMock, patch

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
