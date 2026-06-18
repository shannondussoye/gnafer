"""Supabase-backed geocoding pipeline.

Pulls pending addresses from Supabase, runs them through the existing
GNAFER trigram + LLM pipeline, and writes the results back.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.config import settings
from src.llm_verifier import LLMVerifier
from src.models import PendingAddress, SupabaseGeocodeResult
from src.supabase_client import managed_supabase_client, with_retry
from src.trigram_matcher import TrigramAddressMatcher, get_connection_pool, load_street_types

logger = logging.getLogger(__name__)


def _pull_pending(client: Any, page_size: int, limit: int | None = None) -> list[PendingAddress]:
    """Fetch all pending rows with stable pagination."""
    all_rows: list[dict[str, Any]] = []
    start = 0

    while True:
        end = start + page_size - 1

        def _fetch(_start: int = start, _end: int = end) -> list[dict[str, Any]]:
            response = (
                client.table("pending_addresses")
                .select("*")
                .eq("status", "pending")
                .order("id")
                .range(_start, _end)
                .execute()
            )
            return list(response.data)

        rows = with_retry(_fetch)
        if not rows:
            break
        all_rows.extend(rows)
        if limit and len(all_rows) >= limit:
            all_rows = all_rows[:limit]
            break
        if len(rows) < page_size:
            break
        start += page_size

    logger.info("Pulled %d pending address(es) from Supabase.", len(all_rows))
    return [PendingAddress.model_validate(r) for r in all_rows]


def _mark_status(client: Any, ids: list[int], status: str) -> None:
    """Bulk-update status on pending_addresses."""
    if not ids:
        return

    chunk_size = 500
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]

        def _update(_chunk: list[int] = chunk) -> None:
            client.table("pending_addresses").update({"status": status}).in_("id", _chunk).execute()

        with_retry(_update)


def _geocode_batch(addresses: list[PendingAddress]) -> list[SupabaseGeocodeResult]:
    """Run the existing GNAFER engine over a list of pending addresses."""
    abbreviations = load_street_types(settings.psv_path)
    pool = get_connection_pool()
    matcher = TrigramAddressMatcher(pool=pool, abbreviations=abbreviations)

    try:
        matches = matcher.match_batch(
            [a.input_address for a in addresses],
            workers=settings.trigram_workers,
            show_progress=True,
        )
    finally:
        pool.closeall()

    results: list[SupabaseGeocodeResult] = []
    for addr, match in zip(addresses, matches, strict=True):
        results.append(
            SupabaseGeocodeResult(
                address_detail_pid=match.address_detail_pid,
                input_address=addr.input_address,
                address_label=match.address_label,
                similarity_score=match.similarity_score,
                latitude=match.latitude,
                longitude=match.longitude,
                flat_number=match.flat_number,
                level_type=match.level_type,
                level_number=match.level_number,
                number_first=match.number_first,
                number_last=match.number_last,
                lot_number=match.lot_number,
                street_name=match.street_name,
                street_type=match.street_type,
                street_suffix=match.street_suffix,
                suburb_name=match.suburb_name,
                state=match.state,
                postcode=match.postcode,
                mb_code=match.mb_code,
                llm_verified=match.llm_verified,
                match_method=match.match_method,
            )
        )
    return results


def _writeback_results(client: Any, results: list[SupabaseGeocodeResult], chunk_size: int) -> int:
    """Upsert geocoded results in chunks."""
    written = 0
    dicts = [r.model_dump(mode="json") for r in results]

    for i in range(0, len(dicts), chunk_size):
        chunk = dicts[i : i + chunk_size]

        def _upsert(_chunk: list[dict[str, Any]] = chunk) -> None:
            client.table("geocoded_results").upsert(_chunk, default_to_null=False).execute()

        with_retry(_upsert)
        written += len(chunk)
        logger.info("Wrote %d/%d results to Supabase.", written, len(dicts))

    return written


def run_pipeline(limit: int | None = None) -> dict[str, int]:
    """Run the full Supabase pull → geocode → writeback pipeline.

    Returns
    -------
    dict[str, int]
        Statistics: ``{"pulled": int, "geocoded": int, "written": int}``.
    """
    page_size = settings.supabase_read_page_size
    chunk_size = settings.supabase_batch_size

    with managed_supabase_client() as client:
        pending = _pull_pending(client, page_size=page_size, limit=limit)
        if not pending:
            logger.info("No pending addresses found.")
            return {"pulled": 0, "geocoded": 0, "written": 0}

        ids = [p.id for p in pending]
        _mark_status(client, ids, "processing")

        results = _geocode_batch(pending)
        written = _writeback_results(client, results, chunk_size=chunk_size)
        _mark_status(client, ids, "done")

        return {"pulled": len(pending), "geocoded": len(results), "written": written}
