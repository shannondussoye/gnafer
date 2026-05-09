-- Enable trigram extension for fuzzy matching (Stage 3/4)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- GNAF CORE Table Structure
CREATE TABLE IF NOT EXISTS gnaf_core (
    address_detail_pid VARCHAR(25) PRIMARY KEY,
    street_name TEXT,
    street_type TEXT,
    suburb_name TEXT,
    state VARCHAR(10),
    postcode VARCHAR(10),
    latitude NUMERIC(10, 8),
    longitude NUMERIC(11, 8),
    address_label TEXT -- Full formatted address for fallback/display
);

-- Phase 2 B-Tree Indexes for fast exact/prefix matching
CREATE INDEX IF NOT EXISTS idx_gnaf_postcode ON gnaf_core(postcode);
CREATE INDEX IF NOT EXISTS idx_gnaf_suburb ON gnaf_core(suburb_name);
CREATE INDEX IF NOT EXISTS idx_gnaf_state ON gnaf_core(state);
CREATE INDEX IF NOT EXISTS idx_gnaf_composite ON gnaf_core(street_name, suburb_name);
