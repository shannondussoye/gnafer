-- Supabase Integration Schema
-- Safe to re-run: uses IF NOT EXISTS throughout
-- These tables live in the Supabase cloud project, not the local G-NAF Postgres.

-- Queue of addresses waiting to be geocoded
CREATE TABLE IF NOT EXISTS pending_addresses (
    id BIGSERIAL PRIMARY KEY,
    input_address TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_pending_status CHECK (status IN ('pending', 'processing', 'done', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_addresses(status);
CREATE INDEX IF NOT EXISTS idx_pending_created_at ON pending_addresses(created_at);

-- Sink for geocoded results produced by GNAFER
CREATE TABLE IF NOT EXISTS geocoded_results (
    address_detail_pid TEXT PRIMARY KEY,
    input_address TEXT NOT NULL,
    address_label TEXT,
    similarity_score REAL DEFAULT 0.0,
    latitude NUMERIC,
    longitude NUMERIC,
    flat_number TEXT,
    level_type TEXT,
    level_number TEXT,
    number_first TEXT,
    number_last TEXT,
    lot_number TEXT,
    street_name TEXT,
    street_type TEXT,
    street_suffix TEXT,
    suburb_name TEXT,
    state TEXT,
    postcode TEXT,
    mb_code TEXT,
    llm_verified BOOLEAN DEFAULT FALSE,
    match_method TEXT,
    geocoded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_geocoded_input_address ON geocoded_results(input_address);
CREATE INDEX IF NOT EXISTS idx_geocoded_geocoded_at ON geocoded_results(geocoded_at);
