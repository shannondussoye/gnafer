"""GNAF Geocoder — CLI batch pipeline.

Trigram-first matching with optional LLM verification for high-confidence candidates.
"""

import asyncio
import csv
import logging
import uuid
from pathlib import Path

from src.config import settings
from src.llm_verifier import LLMVerifier
from src.models import MatchResult
from src.observability import GeocoderObservability
from src.trigram_matcher import TrigramAddressMatcher, get_connection_pool, load_street_types

logger = logging.getLogger("gnafer")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "input.txt"
OUTPUT_FILE = PROJECT_ROOT / "geocoded.csv"


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_id = str(uuid.uuid4())
    obs = GeocoderObservability(run_id=run_id)
    obs.ping_healthcheck("/start")

    try:
        if not INPUT_FILE.exists():
            logger.error("Input file %s not found.", INPUT_FILE)
            obs.ping_healthcheck("/fail")
            return

        with open(INPUT_FILE) as f:
            addresses = [
                line.strip().strip('"').strip()
                for line in f
                if line.strip() and not line.startswith("address")
            ]

        abbreviations = load_street_types(settings.psv_path)
        pool = get_connection_pool()
        matcher = TrigramAddressMatcher(pool=pool, abbreviations=abbreviations)
        verifier = LLMVerifier()
        llm_available = await verifier.check_available()

        obs.log_progress("Starting geocoding", {
            "total_addresses": len(addresses),
            "llm_available": llm_available,
        })
        print(f"--- Starting Geocoding ({len(addresses)} addresses) ---")

        # --- Pass 1: Trigram matching ---
        print("\n[Pass 1] Trigram matching...")
        try:
            matches = matcher.match_batch(addresses, workers=settings.trigram_workers, show_progress=True)
        finally:
            pool.closeall()

        matched = sum(1 for m in matches if m.similarity_score > 0)
        print(f"Pass 1 complete: {matched} matched, {len(addresses) - matched} unmatched.")

        # --- Pass 2: LLM verification for scores in [threshold, 1.0) ---
        pending = [
            (i, m) for i, m in enumerate(matches)
            if settings.llm_verify_threshold <= m.similarity_score < 1.0
        ]

        if pending and llm_available:
            print(f"\n[Pass 2] LLM verification ({len(pending)} candidates)...")
            pairs = [(m.input_address, m.address_label) for _, m in pending]
            verdicts = await verifier.verify_batch_async(pairs)

            upgraded = 0
            for (idx, match), verdict in zip(pending, verdicts, strict=True):
                if verdict:
                    matches[idx] = match.model_copy(update={
                        "similarity_score": 1.0,
                        "llm_verified": True,
                        "match_method": "TRIGRAM+LLM",
                    })
                    upgraded += 1
            print(f"Pass 2 complete: {upgraded}/{len(pending)} upgraded to 1.0.")
        elif pending:
            logger.info("Skipping LLM verification — Ollama not available.")

        # --- Assign match methods and save ---
        for m in matches:
            if m.match_method is None:
                m.match_method = "TRIGRAM" if m.similarity_score > 0 else "FAILED"

        fieldnames = list(MatchResult.model_fields.keys())
        with open(OUTPUT_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(m.model_dump() for m in matches)

        success = sum(1 for m in matches if m.similarity_score > 0)
        verified = sum(1 for m in matches if m.llm_verified)

        obs.log_completion({"total": len(addresses), "success": success, "failed": len(addresses) - success})
        obs.ping_healthcheck()

        print(f"\n--- Summary: {success} matched, {len(addresses) - success} failed, {verified} LLM verified ---")
        print(f"Results saved to {OUTPUT_FILE}")

    except Exception as e:
        logger.error("Geocoding process failed: %s", e)
        obs.ping_healthcheck("/fail")
        raise


if __name__ == "__main__":
    asyncio.run(main())
