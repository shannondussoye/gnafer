from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import pytest

# Mock psycopg2 to prevent AddressMatcher from connecting on import
with patch("psycopg2.connect", MagicMock()):
    from src.api import app
    from src.models import GeocodedResult

@pytest.fixture(autouse=True)
def mock_api_dependencies():
    mock_matcher = MagicMock()
    mock_obs = MagicMock()
    with patch("src.api.matcher", mock_matcher), patch("src.api.obs", mock_obs):
        yield mock_matcher, mock_obs

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}

@patch("src.api.parse_address_simple")
def test_geocode_single_success_regex(mock_parse, mock_api_dependencies):
    mock_matcher_api, mock_obs = mock_api_dependencies
    # Setup mock
    mock_parse.return_value = MagicMock()
    mock_result = GeocodedResult(
        input_address="123 George St, Sydney",
        confidence=1.0,
        match_type="PRECISION_NUMBER"
    )
    mock_matcher_api.match.return_value = mock_result
    
    response = client.post("/geocode", json={"address": "123 George St, Sydney"})
    assert response.status_code == 200
    data = response.json()
    assert data["confidence"] == 1.0
    assert data["match_type"] == "PRECISION_NUMBER"
    assert data["parse_method"] == "REGEX"

@patch("src.api.parse_address_simple")
def test_geocode_single_min_confidence_filter(mock_parse, mock_api_dependencies):
    mock_matcher_api, mock_obs = mock_api_dependencies
    # Setup mock with low confidence
    mock_parse.return_value = MagicMock()
    mock_result = GeocodedResult(
        input_address="123 George St, Sydney",
        confidence=0.3,
        match_type="FUZZY_MATCH"
    )
    mock_matcher_api.match.return_value = mock_result
    
    # Require 0.8 minimum confidence
    response = client.post("/geocode?min_confidence=0.8", json={"address": "123 George St, Sydney"})
    # It will fallback to LLM which is not mocked here (or rather, async LLM will return None and fail)
    assert response.status_code == 404

def test_batch_geocode_endpoint(mock_api_dependencies):
    mock_matcher_api, mock_obs = mock_api_dependencies
    mock_result = GeocodedResult(
        input_address="123 George St",
        confidence=1.0,
        match_type="PRECISION_NUMBER"
    )
    mock_matcher_api.match.return_value = mock_result
    
    response = client.post("/geocode/batch", json={"addresses": ["123 George St"]})
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    
    job_id = data["job_id"]
    
    status_response = client.get(f"/jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] in ["processing", "completed"]

def test_job_not_found():
    response = client.get("/jobs/invalid_id")
    assert response.status_code == 404
