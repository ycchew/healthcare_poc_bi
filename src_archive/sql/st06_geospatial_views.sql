-- ============================================================
-- ST-06: Geospatial Analytics
-- geospatial_views.sql
-- Views for Patient Geography and Catchment Analysis
-- ============================================================

-- Enable PostGIS if not already enabled
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- TABLE: Patient Geocoding
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.patient_geocoding (
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(50) REFERENCES dk.patient(mrn) UNIQUE,
    address TEXT,
    postcode VARCHAR(20),
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100) DEFAULT 'Malaysia',
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    -- PostGIS geometry point
    geom GEOMETRY(POINT, 4326),
    geocoding_source VARCHAR(50),  -- 'google', 'nominatim', 'manual'
    geocoding_confidence VARCHAR(20),  -- 'high', 'medium', 'low'
    geocoded_at TIMESTAMP,
    last_visit_date DATE,
    total_visits INTEGER DEFAULT 0,
    total_revenue DECIMAL(15, 2) DEFAULT 0,
    nearest_branch_code VARCHAR(50),
    distance_to_nearest_branch_km DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_geo_mrn ON dk.patient_geocoding(mrn);
CREATE INDEX IF NOT EXISTS idx_patient_geo_geom ON dk.patient_geocoding USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_patient_geo_postcode ON dk.patient_geocoding(postcode);

-- ============================================================
-- TABLE: Branch Locations
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.branch_locations (
    branch_code VARCHAR(50) PRIMARY KEY,
    branch_name VARCHAR(200),
    address TEXT,
    postcode VARCHAR(20),
    city VARCHAR(100),
    state VARCHAR(100),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    geom GEOMETRY(POINT, 4326),
    catchment_radius_km DECIMAL(5, 2) DEFAULT 10.0,
    target_patients INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    opening_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample branch locations (replace with actual data)
INSERT INTO dk.branch_locations (branch_code, branch_name, address, city, latitude, longitude, geom)
VALUES 
    ('AMP', 'Ampang Branch', 'Jalan Ampang', 'Kuala Lumpur', 3.1597, 101.7400, 
     ST_SetSRID(ST_MakePoint(101.7400, 3.1597), 4326)),
    ('KJG', 'Kajang Branch', 'Jalan Reko', 'Kajang', 2.9927, 101.7900, 
     ST_SetSRID(ST_MakePoint(101.7900, 2.9927), 4326))
ON CONFLICT (branch_code) DO UPDATE SET
    branch_name = EXCLUDED.branch_name,
    geom = EXCLUDED.geom;

-- ============================================================
-- VIEW: Patient Geographic Distribution
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_patient_geographic_distribution AS
WITH patient_locations AS (
    SELECT 
        pg.mrn,
        pg.postcode,
        pg.city,
        pg.state,
        pg.latitude,
        pg.longitude,
        pg.geom,
        pg.nearest_branch_code,
        pg.distance_to_nearest_branch_km,
        pg.total_visits,
        pg.total_revenue,
        bl.branch_name AS nearest_branch_name,
        bl.catchment_radius_km
    FROM dk.patient_geocoding pg
    LEFT JOIN dk.branch_locations bl ON pg.nearest_branch_code = bl.branch_code
    WHERE pg.latitude IS NOT NULL 
      AND pg.longitude IS NOT NULL
)
SELECT 
    pl.*,
    CASE 
        WHEN pl.distance_to_nearest_branch_km <= 5 THEN '0-5km'
        WHEN pl.distance_to_nearest_branch_km <= 10 THEN '5-10km'
        WHEN pl.distance_to_nearest_branch_km <= 20 THEN '10-20km'
        WHEN pl.distance_to_nearest_branch_km <= 50 THEN '20-50km'
        ELSE '>50km'
    END AS distance_band,
    CASE 
        WHEN pl.distance_to_nearest_branch_km <= pl.catchment_radius_km 
        THEN 'Within Catchment'
        ELSE 'Outside Catchment'
    END AS catchment_status
FROM patient_locations pl;

-- ============================================================
-- VIEW: Catchment Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_catchment_analysis AS
WITH branch_catchments AS (
    SELECT 
        bl.branch_code,
        bl.branch_name,
        bl.city AS branch_city,
        bl.catchment_radius_km,
        ST_Buffer(
            bl.geom::geography,
            bl.catchment_radius_km * 1000
        )::geometry AS catchment_area
    FROM dk.branch_locations bl
),
patients_in_catchments AS (
    SELECT 
        bc.branch_code,
        bc.branch_name,
        bc.catchment_radius_km,
        pg.mrn,
        pg.total_revenue,
        pg.total_visits,
        pg.distance_to_nearest_branch_km
    FROM branch_catchments bc
    JOIN dk.patient_geocoding pg ON ST_DWithin(
        bc.catchment_area::geography,
        pg.geom::geography,
        bc.catchment_radius_km * 1000
    )
)
SELECT 
    branch_code,
    branch_name,
    catchment_radius_km,
    COUNT(*) AS patients_in_catchment,
    SUM(total_revenue) AS total_revenue_in_catchment,
    AVG(total_revenue) AS avg_revenue_per_patient,
    SUM(total_visits) AS total_visits_in_catchment,
    AVG(distance_to_nearest_branch_km) AS avg_distance_km
FROM patients_in_catchments
GROUP BY branch_code, branch_name, catchment_radius_km;

-- ============================================================
-- VIEW: Cannibalization Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_cannibalization_analysis AS
WITH branch_pairs AS (
    SELECT 
        b1.branch_code AS branch_a,
        b1.branch_name AS branch_a_name,
        b2.branch_code AS branch_b,
        b2.branch_name AS branch_b_name,
        ST_Distance(b1.geom::geography, b2.geom::geography) / 1000 AS distance_km
    FROM dk.branch_locations b1
    JOIN dk.branch_locations b2 ON b1.branch_code < b2.branch_code
    WHERE b1.is_active = TRUE AND b2.is_active = TRUE
),
overlapping_patients AS (
    SELECT 
        bp.*,
        pg.mrn,
        pg.total_revenue,
        pg.total_visits
    FROM branch_pairs bp
    JOIN dk.patient_geocoding pg ON 
        pg.distance_to_nearest_branch_km <= 10 AND
        EXISTS (
            SELECT 1 FROM dk.branch_locations bl
            WHERE bl.branch_code = bp.branch_a
            AND ST_DWithin(bl.geom::geography, pg.geom::geography, 10000)
        ) AND
        EXISTS (
            SELECT 1 FROM dk.branch_locations bl
            WHERE bl.branch_code = bp.branch_b
            AND ST_DWithin(bl.geom::geography, pg.geom::geography, 10000)
        )
)
SELECT 
    branch_a,
    branch_a_name,
    branch_b,
    branch_b_name,
    ROUND(distance_km, 2) AS distance_km,
    COUNT(*) AS overlapping_patients,
    SUM(total_revenue) AS overlapping_revenue,
    AVG(total_revenue) AS avg_revenue_per_patient,
    CASE 
        WHEN distance_km < 5 THEN 'High Risk'
        WHEN distance_km < 10 THEN 'Medium Risk'
        ELSE 'Low Risk'
    END AS cannibalization_risk
FROM overlapping_patients
GROUP BY branch_a, branch_a_name, branch_b, branch_b_name, distance_km
HAVING COUNT(*) > 10
ORDER BY overlapping_patients DESC;

-- ============================================================
-- VIEW: Geographic Hotspots
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_geographic_hotspots AS
SELECT 
    postcode,
    city,
    state,
    COUNT(*) AS patient_count,
    SUM(total_revenue) AS total_revenue,
    AVG(total_revenue) AS avg_revenue_per_patient,
    AVG(latitude) AS centroid_lat,
    AVG(longitude) AS centroid_lon,
    ST_SetSRID(ST_MakePoint(AVG(longitude), AVG(latitude)), 4326) AS centroid_geom,
    -- Create a convex hull for the area
    ST_ConvexHull(ST_Collect(geom)) AS area_boundary
FROM dk.patient_geocoding
WHERE latitude IS NOT NULL AND longitude IS NOT NULL
GROUP BY postcode, city, state
HAVING COUNT(*) >= 5
ORDER BY patient_count DESC;

-- ============================================================
-- VIEW: Expansion Opportunity Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_expansion_opportunities AS
WITH postcode_analysis AS (
    SELECT 
        pg.postcode,
        pg.city,
        pg.state,
        COUNT(*) AS patient_count,
        SUM(pg.total_revenue) AS total_revenue,
        AVG(pg.total_revenue) AS avg_patient_value,
        MIN(bl.branch_code) AS nearest_branch,
        MIN(ST_Distance(pg.geom::geography, bl.geom::geography)) / 1000 AS distance_to_nearest_branch_km
    FROM dk.patient_geocoding pg
    CROSS JOIN dk.branch_locations bl
    WHERE pg.latitude IS NOT NULL
    GROUP BY pg.postcode, pg.city, pg.state
),
scored_postcodes AS (
    SELECT 
        *,
        -- Opportunity score based on patient count, revenue, and distance
        (patient_count * 0.3 + 
         (total_revenue / 1000) * 0.5 + 
         distance_to_nearest_branch_km * 2 * 0.2) AS opportunity_score
    FROM postcode_analysis
)
SELECT 
    postcode,
    city,
    state,
    patient_count,
    ROUND(total_revenue, 2) AS total_revenue,
    ROUND(avg_patient_value, 2) AS avg_patient_value,
    nearest_branch,
    ROUND(distance_to_nearest_branch_km, 2) AS distance_to_nearest_branch_km,
    ROUND(opportunity_score, 2) AS opportunity_score,
    CASE 
        WHEN opportunity_score >= 100 THEN 'High Priority'
        WHEN opportunity_score >= 50 THEN 'Medium Priority'
        ELSE 'Low Priority'
    END AS priority_level
FROM scored_postcodes
WHERE distance_to_nearest_branch_km > 10
ORDER BY opportunity_score DESC;

-- ============================================================
-- MATERIALIZED VIEW: Geographic Intelligence
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_geographic_intelligence CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_geographic_intelligence AS
SELECT 
    pg.mrn,
    pg.postcode,
    pg.city,
    pg.state,
    pg.latitude,
    pg.longitude,
    pg.geom,
    pg.nearest_branch_code,
    pg.distance_to_nearest_branch_km,
    pg.total_visits,
    pg.total_revenue,
    vd.distance_band,
    vd.catchment_status,
    bl.branch_name AS nearest_branch_name,
    bl.catchment_radius_km,
    -- Calculate density proxy
    COUNT(*) OVER (PARTITION BY pg.postcode) AS patients_in_same_postcode
FROM dk.patient_geocoding pg
LEFT JOIN dk.vw_patient_geographic_distribution vd ON pg.mrn = vd.mrn
LEFT JOIN dk.branch_locations bl ON pg.nearest_branch_code = bl.branch_code
WHERE pg.latitude IS NOT NULL AND pg.longitude IS NOT NULL;

CREATE UNIQUE INDEX idx_mvw_geo_intel_mrn ON dk.mvw_geographic_intelligence(mrn);
CREATE INDEX idx_mvw_geo_intel_geom ON dk.mvw_geographic_intelligence USING GIST(geom);
CREATE INDEX idx_mvw_geo_intel_postcode ON dk.mvw_geographic_intelligence(postcode);

-- ============================================================
-- FUNCTION: Update Patient Distance to Nearest Branch
-- ============================================================

CREATE OR REPLACE FUNCTION dk.update_patient_distances()
RETURNS void AS $$
BEGIN
    UPDATE dk.patient_geocoding pg
    SET 
        nearest_branch_code = nearest.branch_code,
        distance_to_nearest_branch_km = nearest.distance_km
    FROM (
        SELECT 
            pg.mrn,
            bl.branch_code,
            ST_Distance(pg.geom::geography, bl.geom::geography) / 1000 AS distance_km,
            ROW_NUMBER() OVER (PARTITION BY pg.mrn ORDER BY ST_Distance(pg.geom::geography, bl.geom::geography)) AS rn
        FROM dk.patient_geocoding pg
        CROSS JOIN dk.branch_locations bl
        WHERE pg.geom IS NOT NULL
    ) nearest
    WHERE pg.mrn = nearest.mrn AND nearest.rn = 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE dk.patient_geocoding IS 'Patient addresses with geocoded coordinates';
COMMENT ON TABLE dk.branch_locations IS 'Branch locations with geographic coordinates';
COMMENT ON VIEW dk.vw_patient_geographic_distribution IS 'Patient locations with distance bands and catchment status';
COMMENT ON VIEW dk.vw_catchment_analysis IS 'Catchment area analysis for each branch';
COMMENT ON VIEW dk.vw_cannibalization_analysis IS 'Inter-branch cannibalization analysis';
COMMENT ON VIEW dk.vw_geographic_hotspots IS 'Geographic hotspots by postcode';
COMMENT ON VIEW dk.vw_expansion_opportunities IS 'Expansion opportunity scoring by location';
COMMENT ON MATERIALIZED VIEW dk.mvw_geographic_intelligence IS 'Consolidated geographic intelligence';
