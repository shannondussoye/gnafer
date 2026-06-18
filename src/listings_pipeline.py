"""Fast geocoder for Supabase `listings` table (no LLM).

Designed for the small-machine / Docker tier.  Polls continuously for
active listings that lack coordinates, runs trigram-only matching, and
writes the results back.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.config import settings
from src.supabase_client import managed_supabase_client, with_retry
from src.trigram_matcher import TrigramAddressMatcher, get_connection_pool, load_street_types
from src.utils import generate_run_id

logger = logging.getLogger(__name__)


def _fetch_batch(client: Any, batch_size: int) -> list[dict[str, Any]]:
    """Pull listings needing geocoding."""

    def _do() -> list[dict[str, Any]]:
        response = (
            client.table("listings")
            .select("id, address")
            .eq("is_active", True)
            .is_("lat", "null")
            .not_.is_("address", "null")
            .or_("geocode_status.is.null,geocode_status.neq.NOT_FOUND")
            .limit(batch_size)
            .execute()
        )
        return list(response.data)

    return with_retry(_do)


def _write_batch(
    client: Any,
    updates: list[dict[str, Any]],
) -> None:
    """Update listings one-by-one to match the user's existing pattern.

    We avoid `.in_()` bulk updates because `geocode_status` and error
    messages differ per row.  If throughput becomes an issue we can
    switch to chunked `.in_()` updates later.
    """
    for update in updates:
        listing_id = update.pop("id")

        def _do(_id: int = listing_id, _payload: dict[str, Any] = update) -> None:
            client.table("listings").update(_payload).eq("id", _id).execute()

        with_retry(_do)


def _geocode_batch(
    listings: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    """Run trigram matching (no LLM) and build update payloads."""
    addresses = [listing["address"] for listing in listings]
    ids = [listing["id"] for listing in listings]

    abbreviations = load_street_types(settings.psv_path)
    pool = get_connection_pool()
    matcher = TrigramAddressMatcher(pool=pool, abbreviations=abbreviations)

    try:
        matches = matcher.match_batch(
            addresses,
            workers=settings.trigram_workers,
            show_progress=False,
        )
    finally:
        pool.closeall()

    updates: list[dict[str, Any]] = []
    for listing_id, match in zip(ids, matches, strict=True):
        update: dict[str, Any] = {
            "id": listing_id,
            "fuzzy_score": match.similarity_score,
            "address_detail_pid": match.address_detail_pid,
            "address_label": match.address_label,
            "match_method": "TRIGRAM",
            "last_geocoded_run_id": run_id,
        }

        if match.similarity_score > 0:
            update.update({
                "lat": match.latitude,
                "lng": match.longitude,
                "geocode_status": "SUCCESS",
                "geocode_error": None,
                "geocode_attempts": 0,
            })
        else:
            update.update({
                "geocode_status": "NOT_FOUND",
                "geocode_error": "No G-NAF match found",
            })

        updates.append(update)

    return updates


def run_fast_geocoder(
    mode: str = "GEO",
    interval: int = 60,
    batch_size: int = 100,
    max_idle_time: int = 600,
) -> dict[str, int]:
    """Continuously poll and geocode listings until idle timeout.

    Parameters
    ----------
    mode
        Operating mode passed to ``generate_run_id``.
    interval
        Seconds to sleep between polls when no work is found.
    batch_size
        Rows to fetch per poll.
    max_idle_time
        Exit after this many seconds with no new listings.

    Returns
    -------
    dict[str, int]
        ``{"total_geocoded": int, "total_failed": int}``.
    """
    run_id = f"{generate_run_id(mode)}-GEO"
    total_geocoded = 0
    total_failed = 0
    idle_time = 0

    with managed_supabase_client() as client:
        while idle_time < max_idle_time:
            listings = _fetch_batch(client, batch_size)

            if listings:
                idle_time = 0
                logger.info("Found %d listing(s) to geocode.", len(listings))

                updates = _geocode_batch(listings, run_id)
                _write_batch(client, updates)

                geocoded = sum(1 for u in updates if u.get("geocode_status") == "SUCCESS")
                failed = len(updates) - geocoded
                total_geocoded += geocoded
                total_failed += failed

                logger.info(
                    "Batch complete: %d geocoded, %d failed (run total: %d/%d)",
                    geocoded,
                    failed,
                    total_geocoded,
                    total_failed,
                )
            else:
                logger.info("No pending listings. Sleeping %d s...", interval)
                time.sleep(interval)
                idle_time += interval

    logger.info(
        "Fast geocoder exiting. Total: %d geocoded, %d failed.",
        total_geocoded,
        total_failed,
    )
    return {"total_geocoded": total_geocoded, "total_failed": total_failed}
