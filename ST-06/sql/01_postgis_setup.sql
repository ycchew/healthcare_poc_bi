-- ============================================================
-- HEALTHCARE GROUP — GEOSPATIAL ANALYTICS SOLUTION
-- FILE 01: PostGIS Setup & Geospatial Tables
-- Database: PostgreSQL + PostGIS  |  Schema: dk
-- ============================================================
-- PRE-REQUISITE: PostGIS extension must be installed
--   sudo apt install postgresql-16-postgis-3   (on server)
--   Then run: CREATE EXTENSION IF NOT EXISTS postgis;
--             CREATE EXTENSION IF NOT EXISTS postgis_topology;
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- STEP 0: Enable PostGIS Extensions
-- ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;   -- for address fuzzy matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;          -- for trigram address search

-- ─────────────────────────────────────────────────────────────
-- STEP 1: BRANCH MASTER TABLE
-- Branch addresses with lat/lng and geometry columns
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dk.branch_master (
    branch_id       SERIAL PRIMARY KEY,
    branch_code     VARCHAR(50) UNIQUE NOT NULL,
    branch_name     VARCHAR(200) NOT NULL,
    entity          VARCHAR(100),
    address_line1   TEXT,
    address_line2   TEXT,
    city            VARCHAR(100),
    state           VARCHAR(100),
    postcode        VARCHAR(20),
    country         VARCHAR(50) DEFAULT 'Malaysia',
    branch_lat      NUMERIC(10,7),
    branch_lng      NUMERIC(10,7),
    geo_point       GEOMETRY(Point, 4326),
    is_active       BOOLEAN DEFAULT TRUE,
    opened_date     DATE,
    branch_type     VARCHAR(50) DEFAULT 'Clinic',
    catchment_radius_km  NUMERIC(5,2) DEFAULT 10.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger: auto-update geo_point whenever lat/lng changes
CREATE OR REPLACE FUNCTION dk.fn_update_branch_geo()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.branch_lat IS NOT NULL AND NEW.branch_lng IS NOT NULL THEN
        NEW.geo_point := ST_SetSRID(
            ST_MakePoint(NEW.branch_lng, NEW.branch_lat), 4326
        );
    END IF;
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_branch_geo ON dk.branch_master;
CREATE TRIGGER trg_branch_geo
    BEFORE INSERT OR UPDATE ON dk.branch_master
    FOR EACH ROW EXECUTE FUNCTION dk.fn_update_branch_geo();

-- GIST spatial index on branch geo_point
CREATE INDEX IF NOT EXISTS idx_branch_geo
    ON dk.branch_master USING GIST (geo_point);

-- ─────────────────────────────────────────────────────────────
-- STEP 2: PATIENT GEOCODE CACHE TABLE
-- Patient geocode cache with lat/lng and geometry
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dk.patient_geocode (
    mrn             VARCHAR(50) NOT NULL,
    location        VARCHAR(50) NOT NULL,
    full_address    TEXT,
    zip             VARCHAR(20),
    city_name       VARCHAR(100),
    state_name      VARCHAR(100),
    country_name    VARCHAR(50),
    patient_lat     NUMERIC(10,7),
    patient_lng     NUMERIC(10,7),
    geo_point       GEOMETRY(Point, 4326),
    geocode_source  VARCHAR(50) DEFAULT 'nominatim',
    geocode_quality VARCHAR(20),
    geocode_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT pk_patient_geocode PRIMARY KEY (mrn, location)
);

-- Auto-update geo_point from lat/lng
CREATE OR REPLACE FUNCTION dk.fn_update_patient_geo()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.patient_lat IS NOT NULL AND NEW.patient_lng IS NOT NULL THEN
        NEW.geo_point := ST_SetSRID(
            ST_MakePoint(NEW.patient_lng, NEW.patient_lat), 4326
        );
    END IF;
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_patient_geo ON dk.patient_geocode;
CREATE TRIGGER trg_patient_geo
    BEFORE INSERT OR UPDATE ON dk.patient_geocode
    FOR EACH ROW EXECUTE FUNCTION dk.fn_update_patient_geo();

-- GIST spatial index — critical for fast radius queries
CREATE INDEX IF NOT EXISTS idx_patient_geo
    ON dk.patient_geocode USING GIST (geo_point);

-- Composite unique index for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_geocode_mrn_loc
    ON dk.patient_geocode (mrn, location);

CREATE INDEX IF NOT EXISTS idx_patient_geocode_zip
    ON dk.patient_geocode (zip);

-- ─────────────────────────────────────────────────────────────
-- STEP 3: MALAYSIA POSTCODE REFERENCE TABLE
-- Malaysia postcode reference with lat/lng and generated geometry
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dk.my_postcode_ref (
    postcode        VARCHAR(10) PRIMARY KEY,
    state           VARCHAR(100),
    city            VARCHAR(100),
    lat             NUMERIC(10,7),
    lng             NUMERIC(10,7),
    geo_point       GEOMETRY(Point, 4326)
        GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lng, lat), 4326)) STORED
);

CREATE INDEX IF NOT EXISTS idx_postcode_geo
    ON dk.my_postcode_ref USING GIST (geo_point);

-- ─────────────────────────────────────────────────────────────
-- STEP 4: PATIENT–BRANCH DISTANCE TABLE
-- Pre-computed patient-branch distance matrix
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dk.patient_branch_distance (
    mrn                 VARCHAR(50) NOT NULL,
    patient_location    VARCHAR(50) NOT NULL,
    branch_code         VARCHAR(50) NOT NULL,
    distance_km         NUMERIC(10,3),
    distance_band       VARCHAR(30),
    est_drive_min       NUMERIC(8,1),
    is_nearest_branch   BOOLEAN DEFAULT FALSE,
    is_within_catchment BOOLEAN DEFAULT FALSE,
    route_line          GEOMETRY(LineString, 4326),
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT pk_pbd PRIMARY KEY (mrn, patient_location, branch_code)
);

-- Indexes for distance queries
CREATE INDEX IF NOT EXISTS idx_pbd_mrn
    ON dk.patient_branch_distance (mrn, patient_location);

CREATE INDEX IF NOT EXISTS idx_pbd_branch
    ON dk.patient_branch_distance (branch_code);

CREATE INDEX IF NOT EXISTS idx_pbd_near
    ON dk.patient_branch_distance (is_nearest_branch) WHERE is_nearest_branch = TRUE;

CREATE INDEX IF NOT EXISTS idx_pbd_geo
    ON dk.patient_branch_distance USING GIST (route_line);

-- ─────────────────────────────────────────────────────────────
-- STEP 5: GEOSPATIAL CLUSTER TABLE (DBSCAN)
-- DBSCAN cluster results
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dk.patient_geo_clusters (
    cluster_id          INT NOT NULL,
    cluster_label       VARCHAR(100),
    centroid_lat        NUMERIC(10,7),
    centroid_lng        NUMERIC(10,7),
    centroid_point      GEOMETRY(Point, 4326)
        GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(centroid_lng, centroid_lat), 4326)) STORED,
    patient_count       INT,
    cluster_radius_km   NUMERIC(8,3),
    dominant_state      VARCHAR(100),
    dominant_city       VARCHAR(100),
    dominant_zip        VARCHAR(20),
    total_revenue       NUMERIC(14,2),
    avg_revenue_per_patient  NUMERIC(10,2),
    nearest_branch      VARCHAR(50),
    distance_to_nearest_branch_km  NUMERIC(8,3),
    is_underserved      BOOLEAN DEFAULT FALSE,
    computed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cluster_geo
    ON dk.patient_geo_clusters USING GIST (centroid_point);

-- Composite unique index for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_cluster_id
    ON dk.patient_geo_clusters (cluster_id);

-- ─────────────────────────────────────────────────────────────
-- STEP 6: BRANCH CANNIBALIZATION / OVERLAP ANALYSIS TABLE
-- Branch-pair level overlap metrics computed by Python DBSCAN
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dk.branch_overlap_analysis (
    analysis_id         SERIAL PRIMARY KEY,
    branch_a            VARCHAR(50) REFERENCES dk.branch_master(branch_code),
    branch_b            VARCHAR(50) REFERENCES dk.branch_master(branch_code),
    branch_distance_km  NUMERIC(8,3),   -- distance between the two branches
    -- Shared patient metrics
    shared_patient_count        INT,
    shared_patient_pct_of_a     NUMERIC(5,2),  -- % of branch A patients also at B
    shared_patient_pct_of_b     NUMERIC(5,2),  -- % of branch B patients also at A
    -- Revenue impact
    shared_revenue_total        NUMERIC(14,2),
    cannibalization_index       NUMERIC(5,3),  -- 0–1; >0.3 = moderate, >0.6 = severe
    cannibalization_severity    VARCHAR(20),   -- None / Low / Moderate / Severe
    -- Catchment overlap
    catchment_overlap_km2       NUMERIC(10,3),
    catchment_overlap_pct       NUMERIC(5,2),
    -- Trend
    shared_patients_3m_ago      INT,
    shared_patients_now         INT,
    cannibalization_trend       VARCHAR(20),   -- Growing / Stable / Shrinking
    computed_at                 TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for overlap analysis queries
CREATE INDEX IF NOT EXISTS idx_overlap_a ON dk.branch_overlap_analysis (branch_a);
CREATE INDEX IF NOT EXISTS idx_overlap_b ON dk.branch_overlap_analysis (branch_b);
CREATE INDEX IF NOT EXISTS idx_overlap_severity ON dk.branch_overlap_analysis (cannibalization_severity);

-- Composite unique index for CONCURRENTLY refresh (prevents duplicate branch pairs)
CREATE UNIQUE INDEX IF NOT EXISTS idx_overlap_branch_pair
    ON dk.branch_overlap_analysis (
        LEAST(branch_a, branch_b),
        GREATEST(branch_a, branch_b)
    ) WHERE branch_a IS NOT NULL AND branch_b IS NOT NULL;

-- ─────────────────────────────────────────────────────────────
-- STEP 7: GEOCODE EXECUTION LOG TABLE
-- Tracking geocoding pipeline runs for audit and monitoring
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dk.geocode_execution_log (
    run_id              SERIAL PRIMARY KEY,
    run_type            VARCHAR(50) NOT NULL,        -- 'full', 'incremental', 'retry'
    status              VARCHAR(20) NOT NULL,        -- 'running', 'completed', 'failed', 'cancelled'
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_seconds    INT,
    -- Processing stats
    records_total       INT DEFAULT 0,
    records_processed   INT DEFAULT 0,
    records_succeeded   INT DEFAULT 0,
    records_failed      INT DEFAULT 0,
    records_skipped     INT DEFAULT 0,
    -- Source details
    source_table        VARCHAR(100),
    source_query        TEXT,
    -- Geocoding details
    geocode_provider    VARCHAR(50) DEFAULT 'nominatim',
    batch_size          INT DEFAULT 100,
    rate_limit_delay_ms INT DEFAULT 1000,
    -- Error tracking
    error_message       TEXT,
    error_details       JSONB,
    -- Retry tracking
    retry_count         INT DEFAULT 0,
    parent_run_id       INT REFERENCES dk.geocode_execution_log(run_id),
    -- Metadata
    run_notes           TEXT,
    triggered_by        VARCHAR(100),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for execution log queries
CREATE INDEX IF NOT EXISTS idx_geocode_log_status ON dk.geocode_execution_log (status);
CREATE INDEX IF NOT EXISTS idx_geocode_log_started ON dk.geocode_execution_log (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_geocode_log_type ON dk.geocode_execution_log (run_type);

-- Composite unique index for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_geocode_log_run
    ON dk.geocode_execution_log (run_id);

-- ============================================================
-- STEP 8: GEOCODING QUALITY VIEWS
-- ============================================================

-- ------------------------------------------------------------
-- View: vw_geocode_quality_summary
-- Purpose: Summary statistics by geocode quality level
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_geocode_quality_summary AS
SELECT 
    geocode_quality AS quality_level,
    COUNT(*) AS total_records,
    COUNT(CASE WHEN geo_point IS NOT NULL THEN 1 END) AS records_with_geometry,
    COUNT(CASE WHEN geo_point IS NULL THEN 1 END) AS records_missing_geometry,
    
    -- Source breakdown
    COUNT(DISTINCT geocode_source) AS unique_sources,
    
    -- Geographic distribution
    COUNT(DISTINCT state_name) AS unique_states,
    COUNT(DISTINCT city_name) AS unique_cities,
    COUNT(DISTINCT zip) AS unique_postcodes,
    
    -- Temporal stats
    MIN(geocode_at) AS earliest_geocode,
    MAX(geocode_at) AS latest_geocode,
    
    -- Quality percentage
    CASE 
        WHEN COUNT(*) > 0 THEN 
            ROUND(COUNT(CASE WHEN geo_point IS NOT NULL THEN 1 END)::NUMERIC / COUNT(*) * 100, 2)
        ELSE 0 
    END AS geometry_completion_pct,
    
    CURRENT_TIMESTAMP AS computed_at

FROM dk.patient_geocode
WHERE geocode_quality IS NOT NULL
GROUP BY geocode_quality;

COMMENT ON VIEW dk.vw_geocode_quality_summary IS 'Summary statistics by geocode quality level. Shows count, geometry completion rate, and geographic distribution.';

-- ------------------------------------------------------------
-- View: vw_geocode_execution_status
-- Purpose: Pipeline execution tracking for geocoding runs
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_geocode_execution_status AS
SELECT 
    run_id,
    run_type,
    status,
    started_at,
    completed_at,
    duration_seconds,
    
    -- Processing stats
    records_total,
    records_processed,
    records_succeeded,
    records_failed,
    records_skipped,
    
    -- Success rate
    CASE 
        WHEN records_processed > 0 THEN 
            ROUND(records_succeeded::NUMERIC / records_processed * 100, 2)
        ELSE 0 
    END AS success_rate_pct,
    
    -- Failure rate
    CASE 
        WHEN records_processed > 0 THEN 
            ROUND(records_failed::NUMERIC / records_processed * 100, 2)
        ELSE 0 
    END AS failure_rate_pct,
    
    -- Geocoding details
    geocode_provider,
    batch_size,
    rate_limit_delay_ms,
    
    -- Error info
    error_message,
    
    -- Retry tracking
    retry_count,
    parent_run_id,
    
    -- Metadata
    run_notes,
    triggered_by,
    created_at
    
FROM dk.geocode_execution_log
ORDER BY started_at DESC;

COMMENT ON VIEW dk.vw_geocode_execution_status IS 'Pipeline execution tracking for geocoding runs. Shows status, processing stats, and error details.';

-- ------------------------------------------------------------
-- View: vw_patient_geo_enriched
-- Purpose: Patient + geocode join for analytics (PII-safe)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_patient_geo_enriched AS
SELECT DISTINCT ON (pg.mrn, pg.location)
    pg.mrn AS patient_id,
    pg.location AS patient_location,
    
    -- Geographic data (no full addresses - PII safe)
    pg.zip AS postcode,
    pg.city_name AS city,
    pg.state_name AS state,
    pg.country_name AS country,
    
    -- Geocode coordinates
    pg.patient_lat,
    pg.patient_lng,
    pg.geo_point,
    
    -- Geocode quality
    pg.geocode_quality,
    pg.geocode_source,
    pg.geocode_at,
    
    -- Has valid geometry flag
    CASE 
        WHEN pg.geo_point IS NOT NULL THEN TRUE 
        ELSE FALSE 
    END AS has_valid_geometry,
    
    -- Patient-demographic derived from patient table (join)
    p.gender,
    p.dob,
    p.race_name,
    
    -- Transaction summary (from patient_transactions if available)
    pt.total_transactions,
    pt.total_revenue,
    pt.last_transaction_date,
    
    -- Value tier derived
    CASE 
        WHEN COALESCE(pt.total_revenue, 0) >= 5000 THEN 'Platinum'
        WHEN COALESCE(pt.total_revenue, 0) >= 2500 THEN 'Gold'
        WHEN COALESCE(pt.total_revenue, 0) >= 1000 THEN 'Silver'
        WHEN COALESCE(pt.total_revenue, 0) >= 500 THEN 'Bronze'
        ELSE 'Standard'
    END AS value_tier,
    
    CURRENT_TIMESTAMP AS enriched_at

FROM dk.patient_geocode pg
LEFT JOIN dk.patient p ON pg.mrn = p.mrn
LEFT JOIN dk.vw_patient_transactions pt ON pg.mrn = pt.patient_id
WHERE pg.geo_point IS NOT NULL  -- Filter NULL geometries for analytics
ORDER BY pg.mrn, pg.location, pg.geocode_at DESC;

COMMENT ON VIEW dk.vw_patient_geo_enriched IS 'Patient + geocode join for analytics. Excludes PII (phone, full addresses). Filters NULL geometries.';

-- ============================================================
-- Grant Permissions for Geocoding Views
-- ============================================================
GRANT SELECT ON dk.vw_geocode_quality_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_geocode_execution_status TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_geo_enriched TO healthcare_bi_reader;

GRANT SELECT ON dk.vw_geocode_quality_summary TO healthcare_bi_app;
GRANT SELECT ON dk.vw_geocode_execution_status TO healthcare_bi_app;
GRANT SELECT ON dk.vw_patient_geo_enriched TO healthcare_bi_app;

-- ============================================================
-- END OF POSTGIS SETUP WITH VIEWS
-- ============================================================