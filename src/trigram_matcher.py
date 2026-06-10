"""GNAF Trigram Address Matcher.

Matches free-text Australian addresses against a G-NAF PostgreSQL table
using pg_trgm similarity with a three-stage fallback strategy:
  Stage 0 — Street-level lookup (postcode + suburb + street_name)
  Stage 1 — Suburb + postcode lookup
  Stage 2 — Full trigram fallback on address_label
"""

import csv
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Protocol

import psycopg2
from psycopg2.extras import NamedTupleCursor
from psycopg2.pool import ThreadedConnectionPool
from tqdm import tqdm

from src.models import MatchResult

logger = logging.getLogger(__name__)


class _Row(Protocol):
    """Protocol for a GNAF row returned by NamedTupleCursor."""
    address_detail_pid: str
    address_label: str
    similarity_score: float
    flat_number: str | None
    level_type: str | None
    level_number: str | None
    number_first: str | None
    number_last: str | None
    lot_number: str | None
    street_name: str | None
    street_type: str | None
    street_suffix: str | None
    suburb_name: str
    state: str
    postcode: str
    address_site_name: str | None
    building_name: str | None
    latitude: float | None
    longitude: float | None
    mb_code: str | None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_SIMILARITY = 0.3

STREET_SUFFIXES = frozenset({
    "NORTH", "SOUTH", "EAST", "WEST", "CENTRAL",
    "DEVIATION", "EXTENSION", "MALL", "ON",
    "N", "S", "E", "W", "NE", "NW", "SE", "SW",
})

UNIT_PREFIXES = frozenset({
    "UNIT", "U", "FLAT", "LEVEL", "L", "SHOP", "SUITE", "LOT",
})

# Regex to parse suburb and postcode from Australian address strings.
# Expects: "..., [SUBURB], [STATE] [POSTCODE]"
ADDR_RE = re.compile(
    r",\s*([^,]+),\s*(?:NSW|VIC|QLD|WA|SA|TAS|ACT|NT|OT)\s+(\d{4})$",
    re.IGNORECASE,
)

_STATE_POSTCODE_RE = re.compile(
    r",\s*((?:NSW|VIC|QLD|WA|SA|TAS|ACT|NT|OT)\s+\d{4})$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# SQL — column list defined once, shared across all queries
# ---------------------------------------------------------------------------

_SELECT_COLUMNS = """\
    address_detail_pid,
    address_label,
    GREATEST(
        similarity(address_label, %s),
        similarity(
            CASE
                WHEN address_site_name != 'NaN' AND address_site_name != '' AND address_label LIKE address_site_name || ' %%'
                    THEN trim(substring(address_label from length(address_site_name) + 2))
                WHEN building_name != 'NaN' AND building_name != '' AND address_label LIKE building_name || ' %%'
                    THEN trim(substring(address_label from length(building_name) + 2))
                ELSE address_label
            END,
            %s
        )
    ) AS similarity_score,
    flat_number,
    level_type,
    level_number,
    number_first,
    number_last,
    lot_number,
    street_name,
    street_type,
    street_suffix,
    suburb_name,
    state,
    postcode,
    address_site_name,
    building_name,
    latitude,
    longitude,
    mb_code"""

STREET_QUERY = f"""
SELECT {_SELECT_COLUMNS}
FROM gnaf_core
WHERE postcode = %s AND suburb_name = %s AND street_name = %s
ORDER BY similarity_score DESC
LIMIT 150;
"""

FAST_QUERY = f"""
SELECT {_SELECT_COLUMNS}
FROM gnaf_core
WHERE postcode = %s AND suburb_name = %s
ORDER BY similarity_score DESC
LIMIT 10;
"""

FALLBACK_QUERY = f"""
SELECT {_SELECT_COLUMNS}
FROM gnaf_core
WHERE address_label %% %s
ORDER BY similarity_score DESC
LIMIT 10;
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_present(val: object) -> bool:
    """Return True if *val* is a meaningful non-null value."""
    return val is not None and str(val).strip() not in ("", "NaN", "nan", "None")


def _expand_word_abbreviation(words: list[str], idx: int, abbreviations: dict[str, str]) -> None:
    """Expand abbreviation at index `idx` in word list `words` in-place."""
    w = words[idx].rstrip(",")
    if w in abbreviations:
        words[idx] = abbreviations[w]


def load_street_types(psv_path: str) -> dict[str, str]:
    """Load street type CODE → NAME mapping from the G-NAF authority PSV file."""
    mapping: dict[str, str] = {}
    if not os.path.exists(psv_path):
        logger.warning(
            "Street type authority file '%s' not found — no normalisation will be applied.",
            psv_path,
        )
        return mapping
    try:
        with open(psv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="|")
            for row in reader:
                code = row.get("CODE")
                name = row.get("NAME")
                if code and name and code.strip() != name.strip():
                    mapping[code.strip().upper()] = name.strip().upper()
    except Exception:
        logger.exception("Failed to load street types from '%s'", psv_path)
    return mapping


def parse_address(address: str) -> tuple[str | None, str | None]:
    """Extract postcode and suburb from an Australian address string."""
    match = ADDR_RE.search(address)
    if match:
        return match.group(2).strip(), match.group(1).strip().upper()
    return None, None


def normalize_address(address: str, postcode: str | None, suburb: str | None, abbreviations: dict[str, str]) -> str:
    """Normalise *address* for trigram comparison against G-NAF labels."""
    addr_upper = address.upper().strip()

    if postcode and suburb:
        match = ADDR_RE.search(addr_upper)
        if match:
            suburb_start = match.start(1)
            street_part = addr_upper[:suburb_start].strip().rstrip(",")
            remaining_part = _STATE_POSTCODE_RE.sub(r" \1", addr_upper[suburb_start:])

            words = street_part.split()
            if words:
                target_idx = -2 if (words[-1] in STREET_SUFFIXES and len(words) >= 2) else -1
                _expand_word_abbreviation(words, target_idx, abbreviations)
                street_part = " ".join(words)

            return f"{street_part}, {remaining_part}"

    # Fallback
    addr_upper = _STATE_POSTCODE_RE.sub(r" \1", addr_upper)
    words = addr_upper.split()
    if words:
        for idx in [-1, -2]:
            if abs(idx) <= len(words):
                _expand_word_abbreviation(words, idx, abbreviations)
        addr_upper = " ".join(words)
    return addr_upper


def normalize_street_words(text: str, abbreviations: dict[str, str]) -> str:
    """Expand all street type abbreviations in *text*."""
    words = text.upper().split()
    for i in range(len(words)):
        _expand_word_abbreviation(words, i, abbreviations)
    return " ".join(words)


def extract_street_name(address: str, postcode: str | None, suburb: str | None, abbreviations: dict[str, str], _abbreviation_values: frozenset[str] | None = None) -> str:
    """Extract the street name component from *address*.

    Parameters
    ----------
    _abbreviation_values : frozenset | None
        Pre-computed ``frozenset(abbreviations.values())``.  When *None* the
        set is built on the fly (backwards-compatible but slower in hot loops).
    """
    if not (postcode and suburb):
        return ""

    addr_upper = address.upper().strip()
    match = ADDR_RE.search(addr_upper)
    if not match:
        return ""

    street_part = addr_upper[: match.start(1)].strip().rstrip(",")
    words = street_part.split()
    if not words:
        return ""

    start_idx = 0
    while start_idx < len(words):
        w = words[start_idx].rstrip(",")
        if w in UNIT_PREFIXES or re.search(r"\d", w) or w.startswith("#"):
            start_idx += 1
        else:
            break

    if start_idx >= len(words):
        start_idx = 0

    abbreviation_values = _abbreviation_values or frozenset(abbreviations.values())
    end_idx = len(words)
    for i in range(len(words) - 1, start_idx - 1, -1):
        w_clean = words[i].rstrip(",")
        if w_clean in abbreviations or w_clean in abbreviation_values:
            end_idx = i
            break

    if end_idx == len(words) and len(words) - start_idx >= 2:
        if words[-1].rstrip(",") in STREET_SUFFIXES:
            end_idx -= 1
        if end_idx - start_idx >= 2:
            end_idx -= 1

    return " ".join(words[start_idx:end_idx]).strip().rstrip(",")


# ---------------------------------------------------------------------------
# Re-scoring
# ---------------------------------------------------------------------------


def _strip_site_or_building_prefix(label_upper: str, site_name: str | None, building_name: str | None) -> tuple[int, str]:
    """Strip address_site_name or building_name prefix from G-NAF label.

    Returns (prefix_offset, clean_label).
    """
    site_upper = site_name.upper() if site_name is not None else ""
    bldg_upper = building_name.upper() if building_name is not None else ""

    if site_upper and label_upper.startswith(site_upper + " "):
        offset = len(site_upper) + 1
        return offset, label_upper[offset:]
    if bldg_upper and label_upper.startswith(bldg_upper + " "):
        offset = len(bldg_upper) + 1
        return offset, label_upper[offset:]
    return 0, label_upper


def _match_house_number(input_num_str: str, number_first: str | None, number_last: str | None) -> bool:
    """Check if input house number matches G-NAF number_first and number_last."""
    num_match = re.search(r"\d+", input_num_str)
    if not num_match:
        return False

    input_number = int(num_match.group())
    first_match = re.search(r"\d+", number_first or "") if number_first is not None else None
    last_match = re.search(r"\d+", number_last or "") if number_last is not None else None

    if first_match:
        first_int = int(first_match.group())
        if last_match:
            last_int = int(last_match.group())
            return min(first_int, last_int) <= input_number <= max(first_int, last_int)
        return input_number == first_int
    return False


def rescore_candidate(addr_normalized: str, row: Any, abbreviations: dict[str, str]) -> float:
    """Re-score a candidate via structural matching of number, unit, and lot."""
    score = float(row.similarity_score)
    street_name_upper = row.street_name.upper() if row.street_name else ""
    if not street_name_upper:
        return score

    input_idx = addr_normalized.upper().find(street_name_upper)
    if input_idx == -1:
        return score

    # Strip site name / building name from G-NAF label for accurate index
    prefix_offset, clean_label = _strip_site_or_building_prefix(
        row.address_label.upper(), row.address_site_name, row.building_name
    )

    clean_gnaf_idx = clean_label.find(street_name_upper)
    if clean_gnaf_idx == -1:
        return score

    gnaf_idx = prefix_offset + clean_gnaf_idx
    input_prefix = addr_normalized[:input_idx].strip()
    gnaf_prefix = row.address_label[:gnaf_idx].strip()

    # Parse input unit and street number
    if "/" in input_prefix:
        input_unit = input_prefix.split("/")[0].strip()
        input_num_str = input_prefix.split("/")[-1].strip()
    else:
        prefix_words = input_prefix.split()
        input_unit = None
        input_num_str = prefix_words[-1].strip() if prefix_words else ""

    # 1. House number matching
    num_matches = _match_house_number(input_num_str, row.number_first, row.number_last)

    # 2. Unit / flat matching
    if is_present(row.flat_number):
        unit_matches = bool(input_unit and input_unit.upper() == row.flat_number.upper())
    else:
        # G-NAF has no unit data for this address — accept the match
        unit_matches = True

    # 3. Lot matching
    lot_matches = True  # Default: pass if lot is not relevant
    if is_present(row.lot_number) and "LOT" in input_prefix.upper():
        input_lot = re.search(r"\d+", input_prefix)
        db_lot = re.search(r"\d+", row.lot_number)
        lot_matches = bool(input_lot and db_lot and input_lot.group() == db_lot.group())

    # 4. Label reconstruction
    if not (num_matches and unit_matches and lot_matches):
        return score

    simplified = row.address_label.upper().replace(gnaf_prefix.upper(), input_prefix.upper())

    has_range = (
        is_present(row.number_first)
        and is_present(row.number_last)
        and row.number_first != row.number_last
    )
    if has_range:
        range_str = f"{row.number_first}-{row.number_last}".upper()
        simplified = simplified.replace(range_str, input_num_str.upper())

    input_street = normalize_street_words(addr_normalized.split(",")[0].strip(), abbreviations)
    gnaf_street = normalize_street_words(simplified.split(",")[0].strip(), abbreviations)

    if input_street == gnaf_street:
        return 1.0

    return score


# ---------------------------------------------------------------------------
# Connection pool factory
# ---------------------------------------------------------------------------


def get_connection_pool(max_conn: int | None = None) -> ThreadedConnectionPool:
    """Create a threaded connection pool from centralised settings."""
    from src.config import settings
    return ThreadedConnectionPool(
        minconn=1,
        maxconn=max_conn or settings.pool_size,
        user=settings.db_user,
        password=settings.db_password,
        dbname=settings.db_name,
        host=settings.db_host,
        port=settings.db_port,
    )


# ---------------------------------------------------------------------------
# Matcher class
# ---------------------------------------------------------------------------


class TrigramAddressMatcher:
    """Trigram-based address matcher against the G-NAF database."""

    def __init__(self, pool: ThreadedConnectionPool, abbreviations: dict):
        self._pool = pool
        self._abbreviations = abbreviations
        self._abbreviation_values = frozenset(abbreviations.values())

    def match(self, address: str) -> MatchResult:
        """Match a single address against G-NAF."""
        conn = None
        try:
            conn = self._pool.getconn()
            with conn.cursor(cursor_factory=NamedTupleCursor) as cur:
                postcode, suburb = parse_address(address)
                addr_normalized = normalize_address(
                    address, postcode, suburb, self._abbreviations
                )

                rows = []

                # Stage 0: street-level lookup
                if postcode and suburb:
                    street_name = extract_street_name(
                        address, postcode, suburb, self._abbreviations,
                        _abbreviation_values=self._abbreviation_values,
                    )
                    if street_name:
                        cur.execute(STREET_QUERY, (
                            addr_normalized, addr_normalized,
                            postcode, suburb, street_name,
                        ))
                        rows = [r for r in cur.fetchall() if r.similarity_score >= MIN_SIMILARITY]

                # Stage 1: suburb + postcode lookup
                if not rows and postcode and suburb:
                    cur.execute(FAST_QUERY, (addr_normalized, addr_normalized, postcode, suburb))
                    rows = [r for r in cur.fetchall() if r.similarity_score >= MIN_SIMILARITY]

                # Stage 2: full trigram fallback
                if not rows:
                    cur.execute(FALLBACK_QUERY, (addr_normalized, addr_normalized, addr_normalized))
                    rows = list(cur.fetchall())

                if not rows:
                    return MatchResult(input_address=address)

                # Re-score candidates
                scored = []
                for row in rows:
                    try:
                        score = rescore_candidate(addr_normalized, row, self._abbreviations)
                    except (ValueError, TypeError, AttributeError):
                        logger.debug(
                            "Re-scoring failed for '%s' against '%s'",
                            address, row.address_label, exc_info=True,
                        )
                        score = float(row.similarity_score)
                    scored.append((score, row))

                has_unit_in_input = "/" in addr_normalized.split(",")[0]
                scored.sort(
                    key=lambda x: (
                        x[0],
                        1 if (has_unit_in_input and is_present(x[1].flat_number)) else 0,
                        x[1].similarity_score,
                    ),
                    reverse=True,
                )
                best_score, best = scored[0]

                return MatchResult(
                    input_address=address,
                    similarity_score=best_score,
                    address_detail_pid=best.address_detail_pid,
                    address_label=best.address_label,
                    flat_number=best.flat_number,
                    level_type=best.level_type,
                    level_number=best.level_number,
                    number_first=best.number_first,
                    number_last=best.number_last,
                    lot_number=best.lot_number,
                    street_name=best.street_name,
                    street_type=best.street_type,
                    street_suffix=best.street_suffix,
                    suburb_name=best.suburb_name,
                    state=best.state,
                    postcode=best.postcode,
                    latitude=float(best.latitude) if best.latitude else None,
                    longitude=float(best.longitude) if best.longitude else None,
                    mb_code=best.mb_code,
                )

        except psycopg2.OperationalError:
            logger.exception("Database connection error matching address: '%s'", address)
            return MatchResult(input_address=address)
        except psycopg2.Error:
            logger.exception("Database error matching address: '%s'", address)
            return MatchResult(input_address=address)
        finally:
            if conn:
                self._pool.putconn(conn)

    def match_batch(
        self, addresses: list[str], workers: int = 16, show_progress: bool = True,
    ) -> list[MatchResult]:
        """Match a list of addresses in parallel. Preserves input order."""
        results: list[MatchResult | None] = [None] * len(addresses)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.match, addr): idx
                for idx, addr in enumerate(addresses)
            }
            iterator = as_completed(futures)
            if show_progress:
                iterator = tqdm(iterator, total=len(futures), desc="Matching")

            for future in iterator:
                results[futures[future]] = future.result()

        # All slots should be filled; assert to satisfy the type checker
        assert all(r is not None for r in results), "Unexpected None in match results"
        return results  # type: ignore[return-value]
