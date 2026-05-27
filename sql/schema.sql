-- GNAF Geocoder Schema
-- Safe to re-run: uses IF NOT EXISTS throughout

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS gnaf_core (
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
CREATE INDEX IF NOT EXISTS idx_gnaf_postcode ON gnaf_core(postcode);
CREATE INDEX IF NOT EXISTS idx_gnaf_suburb ON gnaf_core(suburb_name);
CREATE INDEX IF NOT EXISTS idx_gnaf_street ON gnaf_core(street_name);
CREATE INDEX IF NOT EXISTS idx_gnaf_prec_search ON gnaf_core(street_name, suburb_name, number_first);

-- Composite index for Stage 0 queries (postcode + suburb_name + street_name)
CREATE INDEX IF NOT EXISTS idx_gnaf_stage0_composite ON gnaf_core(postcode, suburb_name, street_name);

-- Trigram Indexes for Fuzzy Matching
CREATE INDEX IF NOT EXISTS idx_gnaf_street_trgm ON gnaf_core USING gin (street_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_gnaf_suburb_trgm ON gnaf_core USING gin (suburb_name gin_trgm_ops);

-- Trigram index on address_label for Stage 2 fallback (was missing — caused full seq scans)
CREATE INDEX IF NOT EXISTS idx_gnaf_label_trgm ON gnaf_core USING gin (address_label gin_trgm_ops);
