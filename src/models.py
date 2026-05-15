from pydantic import BaseModel
from typing import Optional

class ParsedAddress(BaseModel):
    input_address: str
    unit: Optional[str] = ""
    level: Optional[str] = ""
    number: Optional[str] = ""
    street: Optional[str] = ""
    street_type: Optional[str] = ""
    suburb: Optional[str] = ""
    state: Optional[str] = ""
    postcode: Optional[str] = ""

class GeocodedResult(BaseModel):
    unit: Optional[str] = ""
    level: Optional[str] = ""
    number: Optional[str] = ""
    street: Optional[str] = ""
    street_type: Optional[str] = ""
    suburb: Optional[str] = ""
    state: Optional[str] = ""
    postcode: Optional[str] = ""
    input_address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: float = 0.0
    match_type: str = "FAILED"
    address_detail_pid: Optional[str] = None
    mb_code: Optional[str] = None
    parse_method: Optional[str] = None
