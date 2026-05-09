import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "gnafer"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

SCHEMA_FILE = Path("sql/schema.sql")
GNAF_CSV = Path(os.getenv("GNAF_CSV_PATH", "data/GNAF_CORE.csv"))

def init_db(conn):
    """Create schema from SQL file."""
    logger.info("Initialising database schema...")
    with conn.cursor() as cur:
        with open(SCHEMA_FILE, "r") as f:
            cur.execute(f.read())
    conn.commit()
    logger.info("Schema initialised.")

def ingest_gnaf(conn, csv_path):
    """Load GNAF CORE CSV into PostgreSQL."""
    if not csv_path.exists():
        logger.warning(f"GNAF CSV not found at {csv_path}. Skipping ingestion.")
        return

    logger.info(f"Reading {csv_path}...")
    # Read CSV in chunks to handle large files (~15GB mentioned in plan)
    # Note: For testing, we might want to limit this or use a sample
    chunk_size = 50000
    reader = pd.read_csv(csv_path, sep="|", chunksize=chunk_size, low_memory=False)

    with conn.cursor() as cur:
        for i, chunk in enumerate(reader):
            logger.info(f"Processing chunk {i+1}...")
            
            # Map CSV columns to DB columns
            # Standard GNAF CORE headers are usually uppercase
            mapping = {
                'ADDRESS_DETAIL_PID': 'address_detail_pid',
                'STREET_NAME': 'street_name',
                'STREET_TYPE_CODE': 'street_type',
                'SUBURB_NAME': 'suburb_name',
                'STATE_ABBREVIATION': 'state',
                'POSTCODE': 'postcode',
                'LATITUDE': 'latitude',
                'LONGITUDE': 'longitude',
                'ADDRESS_LABEL': 'address_label'
            }
            
            # Filter and rename columns
            data = chunk[list(mapping.keys())].rename(columns=mapping)
            
            # Convert to list of tuples for psycopg2
            tuples = [tuple(x) for x in data.to_numpy()]
            
            query = """
                INSERT INTO gnaf_core (
                    address_detail_pid, street_name, street_type, suburb_name, 
                    state, postcode, latitude, longitude, address_label
                ) VALUES %s
                ON CONFLICT (address_detail_pid) DO NOTHING
            """
            execute_values(cur, query, tuples)
            conn.commit()

    logger.info("Ingestion complete.")

def main():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        init_db(conn)
        ingest_gnaf(conn, GNAF_CSV)
        conn.close()
    except Exception as e:
        logger.error(f"Error during ingestion: {e}")
        exit(1)

if __name__ == "__main__":
    main()
