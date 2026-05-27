"""GNAF data ingestion.

Loads the G-NAF CORE PSV/CSV into the PostgreSQL database.
"""

import logging
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from tqdm import tqdm

from src.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
GNAF_PATH = Path(settings.gnaf_csv_path)


def init_db(conn: "psycopg2.extensions.connection") -> None:
    """Create schema from SQL file."""
    logger.info("Initialising database schema...")
    with conn.cursor() as cur, open(SCHEMA_FILE) as f:
        cur.execute(f.read())
    conn.commit()
    logger.info("Schema initialised.")


def ingest_gnaf(conn: "psycopg2.extensions.connection", file_path: Path) -> None:
    """Load GNAF CORE data into PostgreSQL."""
    if not file_path.exists():
        logger.warning("GNAF data file not found at %s. Skipping ingestion.", file_path)
        return

    # Detect delimiter
    ext = file_path.suffix.lower()
    if ext == '.tsv':
        delimiter = '\t'
    elif ext == '.psv':
        delimiter = '|'
    else:
        with open(file_path, encoding='utf-8-sig') as f:
            first_line = f.readline()
            delimiter = '|' if '|' in first_line else ','

    logger.info("Reading %s using delimiter '%s'...", file_path, delimiter)

    chunk_size = 50000

    # Pre-count rows for progress bar (subtract 1 for header)
    with open(file_path, encoding='utf-8-sig') as fh:
        total_rows = sum(1 for _ in fh) - 1
    total_chunks = (total_rows // chunk_size) + (1 if total_rows % chunk_size else 0)
    logger.info("Total rows: %s (~%d chunks of %d)", f"{total_rows:,}", total_chunks, chunk_size)

    reader = pd.read_csv(file_path, sep=delimiter, chunksize=chunk_size, low_memory=False)

    mapping = {
        'ADDRESS_DETAIL_PID': 'address_detail_pid',
        'DATE_CREATED': 'date_created',
        'ADDRESS_LABEL': 'address_label',
        'ADDRESS_SITE_NAME': 'address_site_name',
        'BUILDING_NAME': 'building_name',
        'FLAT_TYPE': 'flat_type',
        'FLAT_NUMBER': 'flat_number',
        'LEVEL_TYPE': 'level_type',
        'LEVEL_NUMBER': 'level_number',
        'NUMBER_FIRST': 'number_first',
        'NUMBER_LAST': 'number_last',
        'LOT_NUMBER': 'lot_number',
        'STREET_NAME': 'street_name',
        'STREET_TYPE': 'street_type',
        'STREET_SUFFIX': 'street_suffix',
        'LOCALITY_NAME': 'suburb_name',
        'STATE': 'state',
        'POSTCODE': 'postcode',
        'LEGAL_PARCEL_ID': 'legal_parcel_id',
        'MB_CODE': 'mb_code',
        'ALIAS_PRINCIPAL': 'alias_principal',
        'PRINCIPAL_PID': 'principal_pid',
        'PRIMARY_SECONDARY': 'primary_secondary',
        'PRIMARY_PID': 'primary_pid',
        'GEOCODE_TYPE': 'geocode_type',
        'LONGITUDE': 'longitude',
        'LATITUDE': 'latitude'
    }

    rows_inserted = 0
    with conn.cursor() as cur:
        for _i, chunk in enumerate(tqdm(reader, total=total_chunks, desc="Ingesting", unit="chunk")):

            chunk.columns = [c.upper().strip().lstrip('\ufeff') for c in chunk.columns]

            available_mapping = {src: target for src, target in mapping.items() if src in chunk.columns}
            data = chunk[list(available_mapping.keys())].rename(columns=available_mapping)

            # Format Date Field
            if 'date_created' in data.columns:
                data['date_created'] = pd.to_datetime(data['date_created'], dayfirst=True, errors='coerce').dt.date

            # Clean coordinates (must be numeric for SQL)
            coord_cols = ['latitude', 'longitude']
            for col in coord_cols:
                if col in data.columns:
                    data[col] = pd.to_numeric(data[col], errors='coerce')
                    data[col] = data[col].where(pd.notnull(data[col]), None)

            # Keep everything else as strings/objects to avoid range errors
            tuples = [tuple(x) for x in data.to_numpy()]

            cols = list(data.columns)
            query = f"""
                INSERT INTO gnaf_core ({', '.join(cols)})
                VALUES %s
                ON CONFLICT (address_detail_pid) DO NOTHING
            """
            execute_values(cur, query, tuples)
            conn.commit()
            rows_inserted += len(tuples)

    logger.info("Ingestion complete. %s rows inserted.", f"{rows_inserted:,}")


def main() -> None:
    """Run schema init + data ingestion."""
    conn = None
    try:
        conn = psycopg2.connect(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
        )
        init_db(conn)
        ingest_gnaf(conn, GNAF_PATH)
    except psycopg2.OperationalError:
        logger.exception("Cannot connect to database")
        exit(1)
    except psycopg2.Error:
        logger.exception("Database error during ingestion")
        exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
