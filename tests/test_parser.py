import pytest
from src.simple_parser import parse_address_simple

@pytest.mark.parametrize("address,expected", [
    ("123 George St, Sydney NSW 2000", {
        "unit": None, "number": "123", "street": "GEORGE", "street_type": "ST", 
        "suburb": "SYDNEY", "state": "NSW", "postcode": "2000"
    }),
    ("5/10 Main Rd, Melbourne VIC 3000", {
        "unit": "5", "number": "10", "street": "MAIN", "street_type": "RD", 
        "suburb": "MELBOURNE", "state": "VIC", "postcode": "3000"
    }),
    ("Unit 5, 10 Main Rd, Melbourne VIC 3000", {
        "unit": "5", "number": "10", "street": "MAIN", "street_type": "RD", 
        "suburb": "MELBOURNE", "state": "VIC", "postcode": "3000"
    }),
    ("10-12 High Ave, Brisbane QLD 4000", {
        "unit": None, "number": "10-12", "street": "HIGH", "street_type": "AVE", 
        "suburb": "BRISBANE", "state": "QLD", "postcode": "4000"
    }),
    ("10 Main Rd, Melbourne 3000", {  # No state
        "unit": None, "number": "10", "street": "MAIN", "street_type": "RD",
        "suburb": "MELBOURNE", "state": None, "postcode": "3000"
    }),
    ("10 Main Rd, Melbourne VIC", {  # No postcode
        "unit": None, "number": "10", "street": "MAIN", "street_type": "RD",
        "suburb": "MELBOURNE", "state": "VIC", "postcode": None
    }),
    ("10 Main Rd, Melbourne", {  # Only suburb
        "unit": None, "number": "10", "street": "MAIN", "street_type": "RD",
        "suburb": "MELBOURNE", "state": None, "postcode": None
    }),
    ("123 Fake CCT, Springfield", {  # Additional street type
        "unit": None, "number": "123", "street": "FAKE", "street_type": "CCT",
        "suburb": "SPRINGFIELD", "state": None, "postcode": None
    }),
])
def test_parse_address_simple_success(address, expected):
    parsed = parse_address_simple(address)
    assert parsed is not None
    assert parsed.unit == expected["unit"]
    assert parsed.number == expected["number"]
    assert parsed.street == expected["street"]
    assert parsed.street_type == expected["street_type"]
    assert parsed.suburb == expected["suburb"]
    assert parsed.state == expected["state"]
    assert parsed.postcode == expected["postcode"]

def test_parse_address_simple_failure():
    assert parse_address_simple("Invalid Address String") is None
    assert parse_address_simple("123 Fake Street Type") is None
