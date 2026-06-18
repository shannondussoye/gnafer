"""Shared utilities for GNAFER."""

from datetime import datetime
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")


def generate_run_id(mode: str, service: str = "scraper") -> str:
    """Generate a standard run_id: YYYYMMDD-HHMMSS-MODE.

    Parameters
    ----------
    mode
        Operating mode (e.g. ``"BOTH"``, ``"GEO"``).
    service
        Ignored — kept for backward compatibility with the upstream
        ``generate_run_id`` signature.

    Returns
    -------
    str
        ``YYYYMMDD-HHMMSS-MODE`` in Australia/Sydney time.
    """
    timestamp = datetime.now(SYDNEY_TZ).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{mode.upper()}"
