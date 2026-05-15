import os
import psycopg2
from typing import Optional, Tuple
from src.models import ParsedAddress, GeocodedResult
from dotenv import load_dotenv

load_dotenv()

# Standard Australian Street Type Mappings
STREET_TYPE_MAP = {
    "ST": "STREET",
    "RD": "ROAD",
    "AVE": "AVENUE",
    "CRT": "COURT",
    "DR": "DRIVE",
    "PL": "PLACE",
    "LNE": "LANE",
    "GR": "GROVE",
    "HWY": "HIGHWAY",
    "CL": "CLOSE",
    "BVD": "BOULEVARD",
    "BVDE": "BOULEVARDE",
    "PKWY": "PARKWAY",
    "TCE": "TERRACE",
    "WAY": "WAY",
    "PDE": "PARADE",
    "CCT": "CIRCUIT",
    "CRES": "CRESCENT",
    "ESP": "ESPLANADE",
    "SQ": "SQUARE",
    "ARC": "ARCADE",
    "MWS": "MEWS",
    "CIRC": "CIRCLE",
    "CDS": "CUL-DE-SAC",
    "CTH": "CENTREWAY",
    "LDG": "LANDING",
    "LNWY": "LANEWAY",
    "MTWY": "MOTORWAY",
    "PROM": "PROMENADE",
    "QY": "QUAY",
    "QYS": "QUAYS",
    "RTRT": "RETREAT",
    "TWAY": "THROUGHWAY",
    "WKW": "WALKWAY",
    "WTRS": "WATERS",
    "WTRW": "WATERWAY"
}

# Inverse map to find abbreviations from full types
STREET_ABBR_MAP = {v: k for k, v in STREET_TYPE_MAP.items()}

class AddressMatcher:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "gnafer"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432")
        )

    def _get_clean_number(self, number: str) -> str:
        if not number: return ""
        return str(number).split('-')[0].split('/')[0].strip()

    def _get_full_street_type(self, st_type: str) -> str:
        if not st_type: return ""
        u_type = st_type.upper().strip(".")
        return STREET_TYPE_MAP.get(u_type, u_type)

    def match(self, parsed: ParsedAddress) -> Optional[GeocodedResult]:
        if not parsed or not (parsed.street or parsed.suburb):
            return None

        raw_street = parsed.street.upper()
        suburb_name = parsed.suburb.upper() if parsed.suburb else ""
        street_type = self._get_full_street_type(parsed.street_type)
        st_abbr = STREET_ABBR_MAP.get(street_type, "")
        clean_number = self._get_clean_number(parsed.number)

        with self.conn.cursor() as cur:
            # Smart Name Variations
            name_variations = [raw_street]
            
            if street_type and raw_street.endswith(f" {street_type}"):
                name_variations.append(raw_street.replace(f" {street_type}", "").strip())
            
            if st_abbr and raw_street.endswith(f" {st_abbr}"):
                name_variations.append(raw_street.replace(f" {st_abbr}", "").strip())

            if street_type and street_type not in raw_street:
                name_variations.append(f"{raw_street} {street_type}")

            name_variations = list(set(v for v in name_variations if v))

            for name_var in name_variations:
                # Precision matching stages (Confidence 1.0)
                if parsed.unit and clean_number:
                    row = self._query(cur, """
                        SELECT address_detail_pid, street_name, suburb_name, postcode, latitude, longitude, mb_code
                        FROM gnaf_core
                        WHERE street_name = %s AND suburb_name = %s AND street_type = %s
                          AND number_first = %s AND flat_number = %s
                        LIMIT 1
                    """, (name_var, suburb_name, street_type, clean_number, parsed.unit))
                    if row: return self._to_result(parsed, row, 1.0, "PRECISION_UNIT")

                if clean_number:
                    row = self._query(cur, """
                        SELECT address_detail_pid, street_name, suburb_name, postcode, latitude, longitude, mb_code
                        FROM gnaf_core
                        WHERE street_name = %s AND suburb_name = %s AND street_type = %s
                          AND number_first = %s
                        LIMIT 1
                    """, (name_var, suburb_name, street_type, clean_number))
                    if row: return self._to_result(parsed, row, 1.0, "PRECISION_NUMBER")

                row = self._query(cur, """
                    SELECT address_detail_pid, street_name, suburb_name, postcode, latitude, longitude, mb_code
                    FROM gnaf_core
                    WHERE street_name = %s AND suburb_name = %s AND street_type = %s
                    LIMIT 1
                """, (name_var, suburb_name, street_type))
                if row: return self._to_result(parsed, row, 0.9, "STREET_CENTROID")

            # Final Fallback: Fuzzy Match
            row = self._query(cur, """
                SELECT address_detail_pid, street_name, suburb_name, postcode, latitude, longitude, mb_code,
                       (similarity(street_name, %s) + similarity(suburb_name, %s)) / 2 as score
                FROM gnaf_core
                WHERE street_name %% %s AND suburb_name %% %s
                ORDER BY score DESC
                LIMIT 1
            """, (raw_street, suburb_name, raw_street, suburb_name))
            if row and row[7] > 0.4:
                return self._to_result(parsed, row[:7], float(row[7]), "FUZZY_MATCH")

        return None

    def _query(self, cur, sql: str, params: tuple) -> Optional[tuple]:
        cur.execute(sql, params)
        return cur.fetchone()

    def _to_result(self, parsed: ParsedAddress, row: tuple, confidence: float, match_type: str) -> GeocodedResult:
        pid, street, suburb, postcode, lat, lon, mb_code = row
        return GeocodedResult(
            **parsed.model_dump(),
            latitude=lat,
            longitude=lon,
            confidence=confidence,
            match_type=match_type,
            address_detail_pid=pid,
            mb_code=mb_code
        )

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()
