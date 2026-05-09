from pydantic import BaseModel, Field
from typing import Optional

class ParsedAddress(BaseModel):
    """Structured representation of an Australian address."""
    unit: Optional[str] = Field(None, description="Unit or apartment number")
    number: Optional[str] = Field(None, description="Street number")
    street: Optional[str] = Field(None, description="Street name")
    street_type: Optional[str] = Field(None, description="Street type (e.g., ST, RD, AVE)")
    suburb: Optional[str] = Field(None, description="Suburb or locality")
    state: Optional[str] = Field(None, description="State abbreviation (e.g., NSW, VIC)")
    postcode: Optional[str] = Field(None, description="4-digit postcode")

class GeocodedResult(ParsedAddress):
    """Parsed address enriched with coordinates and confidence scoring."""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    match_type: Optional[str] = Field(None, description="Type of match (e.g., EXACT, RELAXED, FUZZY)")
    address_detail_pid: Optional[str] = None
