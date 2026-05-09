import os
import pandas as pd
from tqdm import tqdm
from src.parser import parse_address
from src.matcher import AddressMatcher
from dotenv import load_dotenv

load_dotenv()

def process_geocoding(input_file: str, output_file: str):
    """
    Main processing loop for geocoding.
    """
    print(f"Starting geocoding process...")
    print(f"Input: {input_file}")
    print(f"Output: {output_file}")

    # Read input addresses
    if not os.path.exists(input_file):
        # Create a sample input file if it doesn't exist
        with open(input_file, 'w') as f:
            f.write("123 George St, Sydney NSW 2000\n")
            f.write("Main St, Melbourne 3000\n")
            f.write("GEORGR ST, SYDNEY 2000\n")
            f.write("Level 5, 10 Main Rd, Melbourne 3000\n")
        print(f"Created sample input file: {input_file}")

    with open(input_file, 'r') as f:
        addresses = [line.strip() for line in f if line.strip()]

    matcher = AddressMatcher()
    results = []

    for addr_str in tqdm(addresses, desc="Geocoding"):
        # 1. Parse (Waterfall: Regex -> LLM)
        parsed, method = parse_address(addr_str)
        
        if not parsed:
            results.append({"address": addr_str, "status": "PARSING_FAILED"})
            continue

        # 2. Match (Waterfall: Exact -> Fuzzy)
        match_result = matcher.match(parsed)
        
        if match_result:
            results.append({
                "input_address": addr_str,
                "parsed_street": match_result.street,
                "parsed_suburb": match_result.suburb,
                "latitude": match_result.latitude,
                "longitude": match_result.longitude,
                "confidence": match_result.confidence,
                "match_type": match_result.match_type,
                "parse_method": method,
                "pid": match_result.address_detail_pid
            })
        else:
            results.append({
                "input_address": addr_str,
                "status": "MATCH_FAILED",
                "parse_method": method
            })

    # Save to CSV
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False)
    print(f"\nGeocoding complete! Results saved to {output_file}")

if __name__ == "__main__":
    process_geocoding("input.txt", "geocoded.csv")
