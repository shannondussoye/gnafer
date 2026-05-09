-- GNAF Geocoder Schema - Final TEXT-First Version
-- Maximum robustness for large-scale ingestion

CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP TABLE IF EXISTS gnaf_core;

CREATE TABLE gnaf_core (
    address_detail_pid TEXT PRIMARY KEY,
    date_created DATE,
    address_label TEXT,
    address_site_name TEXT,
    building_name TEXT,
    flat_type TEXT,
    flat_number TEXT,
    level_type TEXT,
    level_number TEXT,
    number_first TEXT,     -- Using TEXT to prevent any "out of range" errors
    number_last TEXT,      -- Using TEXT to prevent any "out of range" errors
    lot_number TEXT,
    street_name TEXT,
    street_type TEXT,
    street_suffix TEXT,
    suburb_name TEXT, 
    state TEXT,
    postcode TEXT,
    legal_parcel_id TEXT,
    mb_code TEXT,
    alias_principal TEXT,
    principal_pid TEXT,
    primary_secondary TEXT,
    primary_pid TEXT,
    geocode_type TEXT,
    longitude NUMERIC,     -- Keeping numeric for spatial precision
    latitude NUMERIC       -- Keeping numeric for spatial precision
);

-- Performance Indexes
CREATE INDEX idx_gnaf_postcode ON gnaf_core(postcode);
CREATE INDEX idx_gnaf_suburb ON gnaf_core(suburb_name);
CREATE INDEX idx_gnaf_street ON gnaf_core(street_name);
CREATE INDEX idx_gnaf_prec_search ON gnaf_core(street_name, suburb_name, number_first);

-- Trigram Indexes for Fuzzy Matching
CREATE INDEX idx_gnaf_street_trgm ON gnaf_core USING gin (street_name gin_trgm_ops);
CREATE INDEX idx_gnaf_suburb_trgm ON gnaf_core USING gin (suburb_name gin_trgm_ops);
