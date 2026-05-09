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
GNAF_PATH = Path(os.getenv("GNAF_CSV_PATH", "data/GNAF_CORE.csv"))

def init_db(conn):
    """Create schema from SQL file."""
    logger.info("Initialising database schema...")
    with conn.cursor() as cur:
        with open(SCHEMA_FILE, "r") as f:
            cur.execute(f.read())
    conn.commit()
    logger.info("Schema initialised.")

def ingest_gnaf(conn, file_path):
    """Load GNAF CORE data into PostgreSQL."""
    if not file_path.exists():
        logger.warning(f"GNAF data file not found at {file_path}. Skipping ingestion.")
        return

    # Detect delimiter
    ext = file_path.suffix.lower()
    if ext == '.tsv':
        delimiter = '\t'
    elif ext == '.psv':
        delimiter = '|'
    else:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            first_line = f.readline()
            delimiter = '|' if '|' in first_line else ','
    
    logger.info(f"Reading {file_path} using delimiter '{delimiter}'...")
    
    chunk_size = 50000
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

    with conn.cursor() as cur:
        for i, chunk in enumerate(reader):
            logger.info(f"Processing chunk {i+1}...")
            
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

    logger.info("Ingestion complete.")

def main():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        init_db(conn)
        ingest_gnaf(conn, GNAF_PATH)
        conn.close()
    except Exception as e:
        logger.error(f"Error during ingestion: {e}")
        exit(1)

if __name__ == "__main__":
    main()
