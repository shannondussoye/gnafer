import re
from src.models import ParsedAddress

def parse_address_simple(address: str) -> ParsedAddress:
    """
    A fast regex-based parser for standard Australian addresses.
    Expected format: [Unit/][Number] [Street Name] [Type] [Suburb] [State] [Postcode]
    """
    
    # regex for standard addresses
    # (?:(?:UNIT|U|APT|SUITE)\s*(?P<unit1>\d+[\w-]*)[,\s]+|(?P<unit2>\d+[\w-]*)/)?(?P<number>\d+[\w-]*)\s+(?P<street>.+?)\s+(?P<type>ST|RD|AVE|CRT|DR|PL|LNE|GR|HWY|CL|BVD|PKWY|TCE|WAY)\.?(?:[,\s]+(?P<suburb>.+?))?(?:\s+(?P<state>NSW|VIC|QLD|WA|SA|TAS|ACT|NT))?(?:\s+(?P<postcode>\d{4}))?$
    pattern = r"^(?:(?:UNIT|U|APT|SUITE)\s*(?P<unit1>\d+[\w-]*)[,\s]+|(?P<unit2>\d+[\w-]*)/)?(?P<number>\d+[\w-]*)\s+(?P<street>.+?)\s+(?P<type>ST|RD|AVE|CRT|DR|PL|LNE|GR|HWY|CL|BVD|PKWY|TCE|WAY)\.?(?:[,\s]+(?P<suburb>.+?))?(?:\s+(?P<state>NSW|VIC|QLD|WA|SA|TAS|ACT|NT))?(?:\s+(?P<postcode>\d{4}))?$"
    
    match = re.match(pattern, address, re.IGNORECASE)
    if not match:
        return None
        
    groups = match.groupdict()
    
    return ParsedAddress(
        unit=groups.get("unit1") or groups.get("unit2"),
        number=groups.get("number"),
        street=groups.get("street").strip().upper() if groups.get("street") else None,
        street_type=groups.get("type").upper() if groups.get("type") else None,
        suburb=groups.get("suburb").strip().strip(",").upper() if groups.get("suburb") else None,
        state=groups.get("state").upper() if groups.get("state") else None,
        postcode=groups.get("postcode"),
        input_address=address  # Now preserving the input address
    )
