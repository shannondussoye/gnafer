"""Weekly LLM verifier for Supabase `listings` table.

Designed for the powerful-machine tier.  Queries near-matches
(0.8 <= fuzzy_score < 1.0) that haven't been LLM-verified yet,
re-runs the match to get the candidate label, asks the local LLM
whether the addresses match, and records the verdict.

Crucially **fuzzy_score is never overwritten** — the original trigram
similarity is preserved alongside the LLM confirmation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.config import settings
from src.llm_verifier import LLMVerifier
from src.supabase_client import managed_supabase_client, with_retry
from src.trigram_matcher import TrigramAddressMatcher, get_connection_pool, load_street_types

logger = logging.getLogger(__name__)


def _fetch_near_matches(
    client: Any,
    threshold: float,
    batch_size: int,
) -> list[dict[str, Any]]:
    """Pull listings in the LLM-verification band."""

    def _do() -> list[dict[str, Any]]:
        response = (
            client.table("listings")
            .select("id, address, fuzzy_score, address_label")
            .eq("is_active", True)
            .gte("fuzzy_score", threshold)
            .lt("fuzzy_score", 1.0)
            .eq("llm_verified", False)
            .limit(batch_size)
            .execute()
        )
        return list(response.data)

    return with_retry(_do)


def _update_verdicts(
    client: Any,
    verdicts: list[tuple[int, bool]],
) -> None:
    """Write LLM verdicts back to listings."""
    now = datetime.now(UTC).isoformat()

    for listing_id, confirmed in verdicts:
        payload = {
            "llm_verified": True,
            "llm_confirmed": confirmed,
            "llm_verified_at": now,
        }

        def _do(_id: int = listing_id, _payload: dict[str, Any] = payload) -> None:
            client.table("listings").update(_payload).eq("id", _id).execute()

        with_retry(_do)


async def run_llm_verifier(
    threshold: float = 0.8,
    batch_size: int = 15,
    max_batches: int | None = None,
) -> dict[str, int]:
    """Run the LLM verification pass over near-matches.

    Parameters
    ----------
    threshold
        Minimum fuzzy_score to consider for LLM verification.
    batch_size
        How many near-matches to verify in one LLM batch.
    max_batches
        Safety limit — stop after this many batches.  ``None`` = unlimited.

    Returns
    -------
    dict[str, int]
        ``{"verified": int, "confirmed": int, "rejected": int}``.
    """
    verifier = LLMVerifier()
    llm_available = await verifier.check_available()
    if not llm_available:
        logger.error("Ollama LLM is not available. Aborting.")
        return {"verified": 0, "confirmed": 0, "rejected": 0}

    verified_total = 0
    confirmed_total = 0
    batch_count = 0

    with managed_supabase_client() as client:
        while True:
            if max_batches is not None and batch_count >= max_batches:
                logger.info("Reached max_batches limit (%d). Stopping.", max_batches)
                break

            listings = _fetch_near_matches(client, threshold, batch_size)
            if not listings:
                logger.info("No more near-matches to verify.")
                break

            logger.info("Verifying %d near-match(es) with LLM...", len(listings))

            # Re-run trigram match to get the candidate label
            # (address_label may be stale if the matcher logic changed)
            addresses = [listing["address"] for listing in listings]
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

            # Build (input_address, candidate_label) pairs for LLM
            pairs: list[tuple[str, str]] = []
            for listing, match in zip(listings, matches, strict=True):
                # Only verify if we still have a valid candidate
                if match.similarity_score > 0 and match.address_label:
                    pairs.append((listing["address"], match.address_label))
                else:
                    # No valid candidate — mark as verified but not confirmed
                    pairs.append(("", ""))  # placeholder, will be skipped

            # Run LLM verification
            # Filter out empty pairs
            valid_pairs = [p for p in pairs if p[0] and p[1]]
            if valid_pairs:
                verdicts = await verifier.verify_batch_async(valid_pairs)
            else:
                verdicts = []

            # Map verdicts back to listing IDs
            verdict_map: list[tuple[int, bool]] = []
            verdict_idx = 0
            for listing, pair in zip(listings, pairs, strict=True):
                if pair[0] and pair[1]:
                    confirmed = verdicts[verdict_idx]
                    verdict_idx += 1
                else:
                    confirmed = False
                verdict_map.append((listing["id"], confirmed))

            _update_verdicts(client, verdict_map)

            confirmed_in_batch = sum(1 for _, c in verdict_map if c)
            rejected_in_batch = len(verdict_map) - confirmed_in_batch

            verified_total += len(verdict_map)
            confirmed_total += confirmed_in_batch
            batch_count += 1

            logger.info(
                "Batch %d: %d confirmed, %d rejected (total verified: %d)",
                batch_count,
                confirmed_in_batch,
                rejected_in_batch,
                verified_total,
            )

    logger.info(
        "LLM verifier complete. %d verified, %d confirmed, %d rejected.",
        verified_total,
        confirmed_total,
        verified_total - confirmed_total,
    )
    return {
        "verified": verified_total,
        "confirmed": confirmed_total,
        "rejected": verified_total - confirmed_total,
    }
