from pydantic import BaseModel
from typing import Optional

class ParsedAddress(BaseModel):
    unit: Optional[str] = None
    number: Optional[str] = None
    street: Optional[str] = None
    street_type: Optional[str] = None
    suburb: Optional[str] = None
    state: Optional[str] = None
    postcode: Optional[str] = None
    input_address: Optional[str] = None

class GeocodedResult(ParsedAddress):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: float
    match_type: str
    address_detail_pid: Optional[str] = None
    parse_method: Optional[str] = None  # Added to track REGEX vs LLM
