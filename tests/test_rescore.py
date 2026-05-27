"""Unit tests for rescore_candidate() (#21).

Uses simple named tuples to simulate psycopg2 NamedTupleCursor rows.
"""

from collections import namedtuple

from src.trigram_matcher import rescore_candidate

# Simulate a database row returned by NamedTupleCursor
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
    """Create a row with sensible defaults, overriding any fields."""
    defaults = {
        "address_detail_pid": "PID001",
        "address_label": "45 GEORGE STREET, SYDNEY NSW 2000",
        "similarity_score": 0.75,
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
        "mb_code": None,
    }
    defaults.update(overrides)
    return Row(**defaults)


# Standard abbreviations for test use
ABBREVIATIONS = {"ST": "STREET", "RD": "ROAD", "AVE": "AVENUE", "DR": "DRIVE"}


class TestRescoreExactMatch:
    """Tests where rescore_candidate should upgrade to 1.0."""

    def test_exact_number_and_street(self):
        """Simple case: input matches exactly."""
        row = _make_row()
        result = rescore_candidate("45 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 1.0

    def test_number_in_range(self):
        """Input number falls within GNAF range → should match."""
        row = _make_row(
            address_label="40-50 GEORGE STREET, SYDNEY NSW 2000",
            number_first="40",
            number_last="50",
        )
        result = rescore_candidate("45 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 1.0


class TestRescoreNoUpgrade:
    """Tests where rescore_candidate should return the original score."""

    def test_no_street_name(self):
        """Row has no street_name → return original score."""
        row = _make_row(street_name=None)
        result = rescore_candidate("45 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 0.75

    def test_wrong_number(self):
        """House number doesn't match → should not upgrade."""
        row = _make_row()
        result = rescore_candidate("99 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 0.75

    def test_number_outside_range(self):
        """Input number is outside the GNAF range → no upgrade."""
        row = _make_row(
            address_label="40-50 GEORGE STREET, SYDNEY NSW 2000",
            number_first="40",
            number_last="50",
        )
        result = rescore_candidate("99 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 0.75


class TestRescoreUnits:
    """Tests for unit/flat matching logic."""

    def test_unit_matches(self):
        """Input unit matches GNAF flat_number → upgrade."""
        row = _make_row(
            address_label="UNIT 3 45 GEORGE STREET, SYDNEY NSW 2000",
            flat_number="3",
        )
        result = rescore_candidate("3/45 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 1.0

    def test_unit_mismatch(self):
        """Input unit differs from GNAF flat_number → no upgrade."""
        row = _make_row(
            address_label="UNIT 3 45 GEORGE STREET, SYDNEY NSW 2000",
            flat_number="3",
        )
        result = rescore_candidate("5/45 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 0.75

    def test_gnaf_has_no_unit_data(self):
        """GNAF has no flat_number → accept the match."""
        row = _make_row(flat_number=None)
        result = rescore_candidate("45 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 1.0


class TestRescoreLots:
    """Tests for lot matching logic."""

    def test_lot_match(self):
        """LOT number matches → should upgrade."""
        row = _make_row(
            address_label="LOT 7 45 GEORGE STREET, SYDNEY NSW 2000",
            lot_number="7",
            number_first="45",
        )
        result = rescore_candidate("LOT 7 45 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 1.0

    def test_lot_mismatch(self):
        """LOT number differs → should not upgrade."""
        row = _make_row(
            address_label="LOT 7 45 GEORGE STREET, SYDNEY NSW 2000",
            lot_number="7",
            number_first="45",
        )
        result = rescore_candidate("LOT 9 45 GEORGE STREET, SYDNEY, NSW 2000", row, ABBREVIATIONS)
        assert result == 0.75
