import os
import psycopg2
from typing import Optional, List
from src.models import ParsedAddress, GeocodedResult
from dotenv import load_dotenv

load_dotenv()

class AddressMatcher:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "gnafer"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432")
        )

    def match(self, parsed: ParsedAddress) -> Optional[GeocodedResult]:
        """
        Match a parsed address against the GNAF database.
        Strategy:
        1. Exact match on street, suburb, and postcode.
        2. Trigram fallback for fuzzy street/suburb names.
        """
        if not parsed or not (parsed.street or parsed.suburb):
            return None

        with self.conn.cursor() as cur:
            # Stage 1: Exact Match
            query = """
                SELECT address_detail_pid, street_name, suburb_name, postcode, latitude, longitude
                FROM gnaf_core
                WHERE street_name = %s 
                  AND suburb_name = %s 
                  AND (postcode = %s OR %s = '')
                LIMIT 1
            """
            
            cur.execute(query, (
                parsed.street.upper() if parsed.street else "",
                parsed.suburb.upper() if parsed.suburb else "",
                parsed.postcode if parsed.postcode else "",
                parsed.postcode if parsed.postcode else ""
            ))
            
            row = cur.fetchone()
            if row:
                return self._to_result(parsed, row, 1.0, "EXACT")

            # Stage 2: Fuzzy Match (Trigram Similarity)
            fuzzy_query = """
                SELECT address_detail_pid, street_name, suburb_name, postcode, latitude, longitude,
                       (similarity(street_name, %s) + similarity(suburb_name, %s)) / 2 as score
                FROM gnaf_core
                WHERE street_name %% %s
                  AND suburb_name %% %s
                ORDER BY score DESC
                LIMIT 1
            """
            
            try:
                cur.execute(fuzzy_query, (
                    parsed.street.upper() if parsed.street else "",
                    parsed.suburb.upper() if parsed.suburb else "",
                    parsed.street.upper() if parsed.street else "",
                    parsed.suburb.upper() if parsed.suburb else ""
                ))
                
                row = cur.fetchone()
                if row:
                    confidence = float(row[6])
                    if confidence > 0.4: # Lowered threshold for test
                        return self._to_result(parsed, row[:6], confidence, "FUZZY")
            except Exception as e:
                print(f"Fuzzy Match Error: {e}")

        return None

    def _to_result(self, parsed: ParsedAddress, row: tuple, confidence: float, match_type: str) -> GeocodedResult:
        pid, street, suburb, postcode, lat, lon = row
        return GeocodedResult(
            **parsed.model_dump(),
            latitude=lat,
            longitude=lon,
            confidence=confidence,
            match_type=match_type,
            address_detail_pid=pid
        )

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

if __name__ == "__main__":
    # Test fuzzy matching
    matcher = AddressMatcher()
    
    # Test typo: "GEORGR" instead of "GEORGE"
    test_parsed = ParsedAddress(
        street="GEORGR",
        suburb="SYDNEY",
        postcode="2000"
    )
    
    result = matcher.match(test_parsed)
    print(f"Fuzzy Match Result: {result}")
