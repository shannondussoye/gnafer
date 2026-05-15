from unittest.mock import patch, MagicMock
import pytest
from src.matcher import AddressMatcher
from src.models import ParsedAddress

@patch("src.matcher.psycopg2.connect")
def test_matcher_get_clean_number(mock_connect):
    matcher = AddressMatcher()
    assert matcher._get_clean_number("123-125") == "123"
    assert matcher._get_clean_number("5/10") == "5"
    assert matcher._get_clean_number("12A") == "12A"
    assert matcher._get_clean_number(None) == ""

@patch("src.matcher.psycopg2.connect")
def test_matcher_get_full_street_type(mock_connect):
    matcher = AddressMatcher()
    assert matcher._get_full_street_type("ST") == "STREET"
    assert matcher._get_full_street_type("st.") == "STREET"
    assert matcher._get_full_street_type("RD") == "ROAD"
    assert matcher._get_full_street_type("INVALID") == "INVALID"
    assert matcher._get_full_street_type(None) == ""

@patch("src.matcher.psycopg2.connect")
def test_matcher_match_empty(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    matcher = AddressMatcher()
    parsed = ParsedAddress(input_address="Empty")
    assert matcher.match(parsed) is None
    
    parsed_no_street = ParsedAddress(input_address="No Street", suburb="SYDNEY")
    assert matcher.match(parsed_no_street) is None

@patch("src.matcher.psycopg2.connect")
def test_matcher_precision_match(mock_connect):
    # Mock database connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Mock database returning a precision match row
    mock_cursor.fetchone.return_value = (
        "pid123", "GEORGE", "SYDNEY", "2000", -33.8688, 151.2093, "mb123"
    )
    
    matcher = AddressMatcher()
    parsed = ParsedAddress(
        input_address="123 George St, Sydney",
        number="123",
        street="GEORGE",
        street_type="ST",
        suburb="SYDNEY"
    )
    
    result = matcher.match(parsed)
    assert result is not None
    assert result.confidence == 1.0
    assert result.match_type == "PRECISION_NUMBER"
    assert result.address_detail_pid == "pid123"
