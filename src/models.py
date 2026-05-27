
from pydantic import BaseModel, Field


class MatchResult(BaseModel):
    """Result from address matching against G-NAF."""
    input_address: str
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    address_detail_pid: str = ""
    address_label: str = ""
    flat_number: str | None = None
    level_type: str | None = None
    level_number: str | None = None
    number_first: str | None = None
    number_last: str | None = None
    lot_number: str | None = None
    street_name: str | None = None
    street_type: str | None = None
    street_suffix: str | None = None
    suburb_name: str | None = None
    state: str | None = None
    postcode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    mb_code: str | None = None
    llm_verified: bool = False
    match_method: str | None = None
