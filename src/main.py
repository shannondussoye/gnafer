import asyncio
import pandas as pd
import os
import time
from typing import List
from tqdm import tqdm
from src.simple_parser import parse_address_simple
from src.llm_parser import parse_address_llm_async
from src.matcher import AddressMatcher
from src.models import GeocodedResult
from src.observability import GeocoderObservability
from dotenv import load_dotenv
import logging
import uuid

# Setup logging
logger = logging.getLogger("gnafer")

load_dotenv()

INPUT_FILE = "input.txt"
OUTPUT_FILE = "geocoded.csv"
BATCH_SIZE = 15  # Concurrent LLM requests

async def check_ollama():
    from ollama import AsyncClient
    client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    try:
        await client.list()
        return True
    except:
        return False

async def main():
    run_id = str(uuid.uuid4())
    matcher = AddressMatcher()
    obs = GeocoderObservability(run_id=run_id)
    obs.ping_healthcheck("/start")
    
    try:
        if not os.path.exists(INPUT_FILE):
            logger.error(f"Input file {INPUT_FILE} not found.")
            obs.ping_healthcheck("/fail")
            return

        with open(INPUT_FILE, "r") as f:
            addresses = [line.strip() for line in f if line.strip()]

    # Check for LLM availability
    llm_available = await check_ollama()
    obs.log_progress("Starting geocoding process", {"total_addresses": len(addresses), "llm_available": llm_available})

    print(f"--- Starting Two-Pass Geocoding ({len(addresses)} addresses) ---")
    
    results = []
    pending_llm = []

    # --- PASS 1: REGEX SPRINT ---
    print("\n[Pass 1] Running Regex Sprint...")
    start_p1 = time.time()
    for addr in tqdm(addresses, desc="Regex Progress"):
        parsed = parse_address_simple(addr)
        if parsed:
            match = matcher.match(parsed)
            if match:
                match.parse_method = "REGEX"
                results.append(match)
                continue
        
        # If regex fails or match fails, queue for LLM
        pending_llm.append(addr)
    
    dur_p1 = time.time() - start_p1
    obs.log_progress("Pass 1 (Regex) Complete", {"matched": len(results), "pending": len(pending_llm), "duration": dur_p1})
    print(f"Pass 1 Complete: {len(results)} matched, {len(pending_llm)} pending LLM.")

    # --- PASS 2: LLM BACKFILL ---
    if pending_llm and llm_available:
        print(f"\n[Pass 2] Running Async LLM Backfill ({len(pending_llm)} addresses)...")
        start_p2 = time.time()
        
        # Process in batches for concurrency
        for i in range(0, len(pending_llm), BATCH_SIZE):
            batch = pending_llm[i:i + BATCH_SIZE]
            print(f"  Processing LLM batch {i//BATCH_SIZE + 1}...")
            
            # Run concurrent LLM parses
            tasks = [parse_address_llm_async(addr) for addr in batch]
            parsed_batch = await asyncio.gather(*tasks)
            
            # Match results
            for addr, parsed in zip(batch, parsed_batch):
                if parsed:
                    match = matcher.match(parsed)
                    if match:
                        match.parse_method = "LLM"
                        results.append(match)
                        continue
                
                # Final Fallback: Mark as failed
                results.append(GeocodedResult(input_address=addr, confidence=0, match_type="FAILED"))

        dur_p2 = time.time() - start_p2
        print(f"Pass 2 Complete in {dur_p2:.2f}s.")
    elif pending_llm:
        logger.info("Marking remaining addresses as FAILED (LLM refinement skipped).")
        for addr in pending_llm:
            results.append(GeocodedResult(input_address=addr, confidence=0, match_type="FAILED"))

    # --- SAVE RESULTS ---
    df = pd.DataFrame([r.model_dump() for r in results])
    df.to_csv(OUTPUT_FILE, index=False)
    
    # --- FINAL SUMMARY ---
    summary = {
        "total": len(addresses),
        "success": len(df[df.confidence > 0]),
        "failed": len(df[df.confidence == 0]),
    }
    obs.log_completion(summary)
    obs.ping_healthcheck()
    
    print("\n--- Geocoding Summary ---")
    print(f"Total Addresses: {len(addresses)}")
    print(f"Successfully Geocoded: {len(df[df.confidence > 0])}")
    print(f"Failed: {len(df[df.confidence == 0])}")
    if not df.empty and 'parse_method' in df.columns:
        print(f"Methods: {df['parse_method'].value_counts().to_dict()}")
    print(f"Results saved to {OUTPUT_FILE}")

    except Exception as e:
        obs.ping_healthcheck("/fail")
        raise

if __name__ == "__main__":
    asyncio.run(main())
