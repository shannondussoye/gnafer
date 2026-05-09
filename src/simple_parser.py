import re
from typing import Optional
from src.models import ParsedAddress

# Regex patterns for Australian address components
# Format: [Unit/][Number] [Street Name] [Street Type], [Suburb] [State] [Postcode]
# Examples: 
# "123 George St, Sydney NSW 2000"
# "Unit 5, 10-12 Main Rd, Melbourne VIC 3000"
# "5/10 Main Rd, Melbourne VIC 3000"

ADDRESS_PATTERN = re.compile(
    r"^(?:(?:UNIT|U|APT|SUITE)\s*(?P<unit1>\d+[\w-]*)[,\s]+|(?P<unit2>\d+[\w-]*)/)?" # Optional Unit
    r"(?P<number>\d+[\w-]*)\s+"                                                     # Street Number
    r"(?P<street>.+?)\s+"                                                           # Street Name
    r"(?P<type>ST|RD|AVE|CRT|DR|PL|LNE|GR|HWY|CL|BVD|PKWY|TCE|WAY)\.?"             # Street Type
    r"(?:[,\s]+(?P<suburb>.+?))?"                                                   # Suburb (Optional if followed by State/Postcode)
    r"(?:\s+(?P<state>NSW|VIC|QLD|WA|SA|TAS|ACT|NT))?"                             # State
    r"(?:\s+(?P<postcode>\d{4}))?$",                                                # Postcode
    re.IGNORECASE
)

def parse_address_simple(address_string: str) -> Optional[ParsedAddress]:
    """
    Perform fast regex-based parsing of an address string.
    Returns ParsedAddress if successful, else None.
    """
    address_string = address_string.strip().upper()
    match = ADDRESS_PATTERN.match(address_string)
    
    if not match:
        return None
    
    groups = match.groupdict()
    
    return ParsedAddress(
        unit=groups.get('unit1') or groups.get('unit2'),
        number=groups.get('number'),
        street=groups.get('street').strip(),
        street_type=groups.get('type').replace('.', ''),
        suburb=groups.get('suburb').strip() if groups.get('suburb') else None,
        state=groups.get('state'),
        postcode=groups.get('postcode')
    )

if __name__ == "__main__":
    # Test cases
    test_cases = [
        "123 George St, Sydney NSW 2000",
        "5/10 Main Rd, Melbourne VIC 3000",
        "Unit 5, 10 Main Rd, Melbourne VIC 3000",
        "10-12 High Ave, Brisbane QLD 4000"
    ]
    
    for tc in test_cases:
        parsed = parse_address_simple(tc)
        print(f"Input: {tc}")
        print(f"Parsed: {parsed}\n")
