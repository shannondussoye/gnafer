"""Tests for trigram matcher pure functions."""

from src.trigram_matcher import (
    extract_street_name,
    is_present,
    normalize_address,
    parse_address,
)

# --- is_present ---

def test_is_present_none():
    assert is_present(None) is False

def test_is_present_nan_string():
    assert is_present("NaN") is False
    assert is_present("nan") is False

def test_is_present_empty():
    assert is_present("") is False
    assert is_present("  ") is False

def test_is_present_valid():
    assert is_present("45") is True
    assert is_present("1704") is True
    assert is_present("MACQUARIE") is True


# --- parse_address ---

def test_parse_standard():
    postcode, suburb = parse_address("14 Smith St, Parramatta, NSW 2150")
    assert postcode == "2150"
    assert suburb == "PARRAMATTA"

def test_parse_multi_word_suburb():
    _postcode, suburb = parse_address("1 Main Rd, Surry Hills, NSW 2010")
    assert suburb == "SURRY HILLS"

def test_parse_no_match():
    postcode, suburb = parse_address("not an address")
    assert postcode is None
    assert suburb is None


# --- normalize_address ---

def test_normalize_expands_street_type():
    abbr = {"STREET": "ST"}
    result = normalize_address("14 Smith Street, Parramatta, NSW 2150", "2150", "PARRAMATTA", abbr)
    assert "ST" in result
    assert "PARRAMATTA" in result

def test_normalize_no_abbreviation():
    result = normalize_address("14 Smith Lane, Parramatta, NSW 2150", "2150", "PARRAMATTA", {})
    assert "PARRAMATTA" in result


# --- extract_street_name ---

def test_extract_simple():
    abbr = {"ST": "STREET", "STREET": "ST"}
    name = extract_street_name("14 Smith St, Parramatta, NSW 2150", "2150", "PARRAMATTA", abbr)
    assert name == "SMITH"

def test_extract_with_unit():
    abbr = {"ST": "STREET", "STREET": "ST"}
    name = extract_street_name("6/15 Barker St, Kensington, NSW 2033", "2033", "KENSINGTON", abbr)
    assert name == "BARKER"

def test_extract_no_postcode():
    result = extract_street_name("14 Smith St", None, None, {})
    assert result == ""
