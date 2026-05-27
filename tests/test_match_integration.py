"""Integration tests for TrigramAddressMatcher.match() (#20).

Uses a mock connection pool that returns pre-built named tuple rows,
simulating what PostgreSQL would return without needing a live database.
"""

from collections import namedtuple
from unittest.mock import MagicMock

import psycopg2
import pytest

from src.trigram_matcher import TrigramAddressMatcher

# Simulate a psycopg2 NamedTupleCursor row
Row = namedtuple("Row", [
    "address_detail_pid", "address_label", "similarity_score",
    "flat_number", "level_type", "level_number",
    "number_first", "number_last", "lot_number",
    "street_name", "street_type", "street_suffix",
    "suburb_name", "state", "postcode",
    "address_site_name", "building_name",
    "latitude", "longitude", "mb_code",
])


def _make_row(**overrides):
    """Create a row with sensible defaults."""
    defaults = {
        "address_detail_pid": "GAACT001",
        "address_label": "45 GEORGE STREET, SYDNEY NSW 2000",
        "similarity_score": 0.85,
        "flat_number": None,
        "level_type": None,
        "level_number": None,
        "number_first": "45",
        "number_last": None,
        "lot_number": None,
        "street_name": "GEORGE",
        "street_type": "STREET",
        "street_suffix": None,
        "suburb_name": "SYDNEY",
        "state": "NSW",
        "postcode": "2000",
        "address_site_name": None,
        "building_name": None,
        "latitude": -33.8688,
        "longitude": 151.2093,
        "mb_code": "MB001",
    }
    defaults.update(overrides)
    return Row(**defaults)


ABBREVIATIONS = {"ST": "STREET", "RD": "ROAD", "AVE": "AVENUE"}


@pytest.fixture
def mock_pool():
    """Create a mock ThreadedConnectionPool."""
    pool = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()

    pool.getconn.return_value = conn
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    return pool, cursor


class TestMatchSingleAddress:
    """Integration tests for the match() method."""

    def test_match_returns_best_candidate(self, mock_pool):
        """When DB returns candidates, match() returns the best one."""
        pool, cursor = mock_pool
        high_score_row = _make_row(similarity_score=0.95)

        # Stage 0 (street query) returns the candidate
        cursor.fetchall.return_value = [high_score_row]

        matcher = TrigramAddressMatcher(pool=pool, abbreviations=ABBREVIATIONS)
        result = matcher.match("45 George St, Sydney, NSW 2000")

        assert result.similarity_score >= 0.95
        assert result.address_detail_pid == "GAACT001"
        assert result.suburb_name == "SYDNEY"
        assert result.postcode == "2000"
        pool.putconn.assert_called_once()

    def test_match_no_results_returns_zero(self, mock_pool):
        """When DB returns nothing, match() returns a zero-score result."""
        pool, cursor = mock_pool
        cursor.fetchall.return_value = []

        matcher = TrigramAddressMatcher(pool=pool, abbreviations=ABBREVIATIONS)
        result = matcher.match("999 Fake Road, Nowhere, NSW 0000")

        assert result.similarity_score == 0.0
        assert result.input_address == "999 Fake Road, Nowhere, NSW 0000"
        pool.putconn.assert_called_once()

    def test_match_always_returns_connection(self, mock_pool):
        """Connection is always returned to pool, even on error."""
        pool, cursor = mock_pool
        cursor.fetchall.side_effect = psycopg2.OperationalError("DB exploded")

        matcher = TrigramAddressMatcher(pool=pool, abbreviations=ABBREVIATIONS)
        result = matcher.match("45 George St, Sydney, NSW 2000")

        assert result.similarity_score == 0.0
        pool.putconn.assert_called_once()

    def test_match_picks_best_of_multiple_candidates(self, mock_pool):
        """When DB returns multiple candidates, the highest score wins."""
        pool, cursor = mock_pool
        rows = [
            _make_row(address_detail_pid="LOW", similarity_score=0.5, number_first="99"),
            _make_row(address_detail_pid="HIGH", similarity_score=0.9),
        ]
        cursor.fetchall.return_value = rows

        matcher = TrigramAddressMatcher(pool=pool, abbreviations=ABBREVIATIONS)
        result = matcher.match("45 George St, Sydney, NSW 2000")

        assert result.address_detail_pid == "HIGH"
        assert result.similarity_score >= 0.9


class TestMatchBatch:
    """Integration tests for match_batch()."""

    def test_batch_preserves_order(self, mock_pool):
        """Batch results maintain input order."""
        pool, cursor = mock_pool

        # Each call to match will return a result based on the row
        def make_result_for(addr):
            return [_make_row(address_label=addr.upper(), similarity_score=0.8)]

        cursor.fetchall.return_value = [_make_row(similarity_score=0.8)]

        matcher = TrigramAddressMatcher(pool=pool, abbreviations=ABBREVIATIONS)
        results = matcher.match_batch(
            ["addr1, Sydney, NSW 2000", "addr2, Sydney, NSW 2000"],
            workers=1,
            show_progress=False,
        )

        assert len(results) == 2
        assert all(r.similarity_score >= 0 for r in results)

    def test_batch_empty_input(self, mock_pool):
        """Empty input returns empty results."""
        pool, _ = mock_pool
        matcher = TrigramAddressMatcher(pool=pool, abbreviations=ABBREVIATIONS)
        results = matcher.match_batch([], workers=1, show_progress=False)
        assert results == []
