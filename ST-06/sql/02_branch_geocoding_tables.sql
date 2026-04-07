-- ============================================================
-- HEALTHCARE GROUP — GEOSPATIAL ANALYTICS SOLUTION
-- FILE 02: Branch Geocoding Tables
-- Database: PostgreSQL + PostGIS  |  Schema: dk
-- ============================================================
-- Purpose: Support branch_geocoding.py module
-- Tables: branch_master extensions, branch_geocode_log (per-address)
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- STEP 1: ADD GEOCODING COLUMNS TO BRANCH_MASTER
-- ─────────────────────────────────────────────────────────────
-- These columns track geocoding results and metadata

-- Add geocoding coordinate columns (if not exist)
ALTER TABLE dk.branch_master 
ADD COLUMN IF NOT EXISTS lat NUMERIC(10,7);

ALTER TABLE dk.branch_master 
ADD COLUMN IF NOT EXISTS lng NUMERIC(10,7);

-- Add geocoding metadata
ALTER TABLE dk.branch_master 
ADD COLUMN IF NOT EXISTS geocoded_address TEXT;

ALTER TABLE dk.branch_master 
ADD COLUMN IF NOT EXISTS geocode_source VARCHAR(50);

ALTER TABLE dk.branch_master 
ADD COLUMN IF NOT EXISTS geocode_timestamp TIMESTAMPTZ;

-- Add index for geocoding queries
CREATE INDEX IF NOT EXISTS idx_branch_master_geo_source
    ON dk.branch_master (geocode_source);

-- ─────────────────────────────────────────────────────────────
-- STEP 2: CREATE PER-ADDRESS BRANCH GEOCODE LOG
-- ─────────────────────────────────────────────────────────────
-- This table tracks individual branch geocoding attempts (not batch runs)

CREATE TABLE IF NOT EXISTS dk.branch_geocode_log (
    log_id              SERIAL PRIMARY KEY,
    branch_code         VARCHAR(50) NOT NULL,
    original_address    TEXT NOT NULL,
    geocoded_address    TEXT,
    lat                 NUMERIC(10,7),
    lng                 NUMERIC(10,7),
    geocode_source      VARCHAR(50),  -- 'azure_maps', 'nominatim', or NULL
    status              VARCHAR(20) NOT NULL,  -- 'SUCCESS' or 'FAILED'
    error_message       TEXT,
    execution_timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for log queries
CREATE INDEX IF NOT EXISTS idx_branch_geocode_log_branch
    ON dk.branch_geocode_log (branch_code);

CREATE INDEX IF NOT EXISTS idx_branch_geocode_log_status
    ON dk.branch_geocode_log (status);

CREATE INDEX IF NOT EXISTS idx_branch_geocode_log_timestamp
    ON dk.branch_geocode_log (execution_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_branch_geocode_log_source
    ON dk.branch_geocode_log (geocode_source);

-- ─────────────────────────────────────────────────────────────
-- STEP 3: CREATE GEOCODING STATISTICS VIEW
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW dk.vw_geocode_stats AS
SELECT 
    branch_code,
    COUNT(*) AS total_attempts,
    COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) AS successful_attempts,
    COUNT(CASE WHEN status = 'FAILED' THEN 1 END) AS failed_attempts,
    MAX(CASE WHEN status = 'SUCCESS' THEN execution_timestamp END) AS last_successful_geocode,
    MAX(geocode_source) AS primary_source,
    CASE 
        WHEN COUNT(*) > 0 THEN 
            ROUND(COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END)::NUMERIC / COUNT(*) * 100, 2)
        ELSE 0 
    END AS success_rate_pct
FROM dk.branch_geocode_log
GROUP BY branch_code;

COMMENT ON VIEW dk.vw_geocode_stats IS 'Per-branch geocoding statistics showing attempts, success rate, and primary source.';

-- Grant permissions
GRANT SELECT ON dk.vw_geocode_stats TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_geocode_stats TO healthcare_bi_app;

-- ============================================================
-- END OF BRANCH GEOCODING TABLES
-- ============================================================
