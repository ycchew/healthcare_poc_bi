-- ============================================================================
-- ST-06: Geospatial Analytics
-- File: 04_materialized_views.sql
-- Description: Materialized views for geospatial analytics caching
-- Schema: dk
-- Dependencies: 
--   - Views from 03_analytical_views.sql
--   - Tables: dk.patient_geo_clusters, dk.branch_overlap_analysis
-- ============================================================================

-- ============================================================================
-- SECTION 1: MATERIALIZED VIEWS FOR GEOSPATIAL CACHING
-- ============================================================================

-- ============================================================
-- Materialized View: mvw_patient_geo_enriched
-- Purpose: Cached patient geo data with distances
-- Unique Key: mrn (one row per patient)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_patient_geo_enriched AS
SELECT 
    mrn,
    registered_branch,
    gender_clean,
    age,
    age_band,
    race_clean,
    city_name,
    state_name,
    zip,
    patient_lat,
    patient_lng,
    geocode_quality,
    geocode_source,
    nearest_branch,
    dist_to_nearest_km,
    nearest_branch_dist_band,
    est_drive_min_to_nearest,
    is_within_catchment,
    total_visits,
    lifetime_revenue,
    skincare_revenue,
    package_revenue,
    last_visit_date,
    first_visit_date,
    visited_branches,
    computed_at
FROM dk.vw_patient_geo_enriched;

-- Unique index required for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_patient_geo_mrn 
    ON dk.mvw_patient_geo_enriched (mrn);

-- Additional indexes for common queries
CREATE INDEX IF NOT EXISTS idx_mvw_patient_geo_nearest 
    ON dk.mvw_patient_geo_enriched (nearest_branch);
CREATE INDEX IF NOT EXISTS idx_mvw_patient_geo_dist_band 
    ON dk.mvw_patient_geo_enriched (nearest_branch_dist_band);
CREATE INDEX IF NOT EXISTS idx_mvw_patient_geo_state 
    ON dk.mvw_patient_geo_enriched (state_name);
CREATE INDEX IF NOT EXISTS idx_mvw_patient_geo_within_catchment 
    ON dk.mvw_patient_geo_enriched (is_within_catchment);

COMMENT ON MATERIALIZED VIEW dk.mvw_patient_geo_enriched IS 
    'ST-06 cached patient geo data with nearest branch distances. Refresh after distance calculation.';

-- ============================================================
-- Materialized View: mvw_branch_patient_summary
-- Purpose: Cached branch-level patient metrics
-- Unique Key: branch_code (one row per branch)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_branch_patient_summary AS
SELECT 
    branch_code,
    branch_name,
    entity,
    city,
    state,
    branch_lat,
    branch_lng,
    catchment_radius_km,
    is_active,
    opened_date,
    branch_type,
    primary_patients,
    total_reached_patients,
    avg_dist_km,
    median_dist_km,
    max_dist_km,
    patients_under_2km,
    patients_2_5km,
    patients_5_10km,
    patients_10_20km,
    patients_over_20km,
    catchment_patients,
    beyond_catchment_patients,
    catchment_coverage_pct,
    transacting_patients,
    total_transactions,
    total_revenue,
    skincare_revenue,
    package_revenue,
    avg_basket,
    last_txn_date,
    revenue_per_patient,
    computed_at
FROM dk.vw_branch_patient_summary;

-- Unique index required for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_branch_summary_code 
    ON dk.mvw_branch_patient_summary (branch_code);

-- Additional indexes
CREATE INDEX IF NOT EXISTS idx_mvw_branch_summary_state 
    ON dk.mvw_branch_patient_summary (state);
CREATE INDEX IF NOT EXISTS idx_mvw_branch_summary_coverage 
    ON dk.mvw_branch_patient_summary (catchment_coverage_pct DESC);

COMMENT ON MATERIALIZED VIEW dk.mvw_branch_patient_summary IS 
    'ST-06 cached branch patient metrics. Refresh after distance calculation.';

-- ============================================================
-- Materialized View: mvw_catchment_analysis
-- Purpose: Cached distance band distribution by branch
-- Unique Key: branch_code, distance_band, is_within_catchment, 
--             gender_clean, age_band, race_clean, state_name
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_catchment_analysis AS
SELECT 
    pbd.branch_code,
    bm.branch_name,
    bm.entity,
    bm.branch_city,
    bm.catchment_radius_km,
    pbd.distance_band,
    pbd.is_within_catchment,
    pa.gender_clean,
    pa.age_band,
    pa.race_clean,
    pa.state_name                                                AS patient_state,
    COUNT(DISTINCT pbd.mrn)                                      AS patient_count,
    SUM(txn.lifetime_revenue)                                    AS total_revenue,
    AVG(txn.lifetime_revenue)                                    AS avg_patient_revenue,
    SUM(txn.skincare_revenue)                                    AS skincare_revenue,
    SUM(txn.package_revenue)                                     AS package_revenue,
    AVG(txn.total_visits)                                        AS avg_visits,
    AVG(pbd.distance_km)                                        AS avg_dist_km,
    AVG(pbd.est_drive_min)                                       AS avg_drive_min,
    ROUND(AVG(txn.lifetime_revenue) /
          NULLIF(AVG(pbd.distance_km), 0), 2)                   AS revenue_per_km_travelled,
    CURRENT_TIMESTAMP                                            AS computed_at
FROM dk.patient_branch_distance pbd
JOIN dk.branch_master bm ON pbd.branch_code = bm.branch_code
LEFT JOIN (
    SELECT
        p.mrn,
        CASE WHEN LOWER(p.gender) IN ('m','male') THEN 'Male'
             WHEN LOWER(p.gender) IN ('f','female') THEN 'Female'
             ELSE 'Other/Unknown' END                            AS gender_clean,
        CASE
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 25 THEN '18-24'
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 35 THEN '25-34'
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 45 THEN '35-44'
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 55 THEN '45-54'
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 65 THEN '55-64'
            ELSE '65+'
        END                                                      AS age_band,
        COALESCE(NULLIF(TRIM(p.race_name),''), 'Unknown')       AS race_clean,
        p.state_name
    FROM dk.patient p
) pa ON pbd.mrn = pa.mrn
LEFT JOIN (
    SELECT
        cr.mrn,
        COUNT(DISTINCT cr.sale_order_no)                         AS total_visits,
        SUM(COALESCE(cr.standalone_sales_subtotal_rm,0) +
            COALESCE(cr.package_sales_subtotal_rm,0))            AS lifetime_revenue,
        SUM(COALESCE(cr.standalone_sales_skincare_product_amount_rm,0) +
            COALESCE(cr.package_sales_skincare_product_amount_rm,0)) AS skincare_revenue,
        SUM(COALESCE(cr.package_sales_subtotal_rm,0))            AS package_revenue
    FROM dk.collection_report cr
    WHERE cr.status NOT ILIKE '%void%'
    GROUP BY cr.mrn
) txn ON pbd.mrn = txn.mrn
WHERE pbd.is_nearest_branch = TRUE
GROUP BY
    pbd.branch_code, bm.branch_name, bm.entity, bm.branch_city,
    bm.catchment_radius_km, pbd.distance_band, pbd.is_within_catchment,
    pa.gender_clean, pa.age_band, pa.race_clean, pa.state_name;

-- Unique index for CONCURRENTLY refresh - use DISTINCT ON pattern
CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_catchment_unique 
    ON dk.mvw_catchment_analysis (
        branch_code, distance_band, is_within_catchment, 
        gender_clean, age_band, race_clean, patient_state
    );

-- Additional indexes
CREATE INDEX IF NOT EXISTS idx_mvw_catchment_branch 
    ON dk.mvw_catchment_analysis (branch_code);
CREATE INDEX IF NOT EXISTS idx_mvw_catchment_dist_band 
    ON dk.mvw_catchment_analysis (distance_band);
CREATE INDEX IF NOT EXISTS idx_mvw_catchment_catchment 
    ON dk.mvw_catchment_analysis (is_within_catchment);

COMMENT ON MATERIALIZED VIEW dk.mvw_catchment_analysis IS 
    'ST-06 cached distance band analysis by branch. Refresh after distance calculation.';

-- ============================================================
-- Materialized View: mvw_cannibalization_summary
-- Purpose: Cached cannibalization metrics
-- Unique Key: branch_a, branch_b (branch pair)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_cannibalization_summary AS
SELECT 
    boa.branch_a,
    bm_a.branch_name                                             AS branch_a_name,
    bm_a.city                                                    AS branch_a_city,
    boa.branch_b,
    bm_b.branch_name                                             AS branch_b_name,
    bm_b.city                                                    AS branch_b_city,
    boa.branch_distance_km,
    boa.shared_patient_count,
    boa.shared_patient_pct_of_a,
    boa.shared_patient_pct_of_b,
    boa.shared_revenue_total,
    boa.cannibalization_index,
    boa.cannibalization_severity,
    boa.computed_at,
    CASE
        WHEN boa.cannibalization_severity IN ('Moderate','Severe')
             AND boa.shared_patient_count > 10                 THEN 'ACTION REQUIRED'
        WHEN boa.cannibalization_severity = 'Severe'             THEN 'MONITOR CLOSELY'
        ELSE 'OK'
    END                                                          AS alert_status,
    bm_a.branch_lat                                              AS branch_a_lat,
    bm_a.branch_lng                                              AS branch_a_lng,
    bm_b.branch_lat                                              AS branch_b_lat,
    bm_b.branch_lng                                              AS branch_b_lng
FROM dk.branch_overlap_analysis boa
JOIN dk.branch_master bm_a ON boa.branch_a = bm_a.branch_code
JOIN dk.branch_master bm_b ON boa.branch_b = bm_b.branch_code;

-- Unique index for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_cannib_unique 
    ON dk.mvw_cannibalization_summary (branch_a, branch_b);

-- Additional indexes
CREATE INDEX IF NOT EXISTS idx_mvw_cannib_severity 
    ON dk.mvw_cannibalization_summary (cannibalization_severity);
CREATE INDEX IF NOT EXISTS idx_mvw_cannib_alert 
    ON dk.mvw_cannibalization_summary (alert_status);
CREATE INDEX IF NOT EXISTS idx_mvw_cannib_shared_patients 
    ON dk.mvw_cannibalization_summary (shared_patient_count DESC);

COMMENT ON MATERIALIZED VIEW dk.mvw_cannibalization_summary IS 
    'ST-06 cached cannibalization metrics. Refresh after overlap analysis.';

-- ============================================================
-- Materialized View: mvw_patient_geo_clusters
-- Purpose: Cached DBSCAN cluster results
-- Unique Key: cluster_id (one row per cluster)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_patient_geo_clusters AS
SELECT 
    cluster_id,
    cluster_label,
    centroid_lat,
    centroid_lng,
    patient_count,
    cluster_radius_km,
    dominant_state,
    dominant_city,
    total_revenue,
    avg_revenue_per_patient,
    nearest_branch,
    distance_to_nearest_branch_km,
    is_underserved,
    computed_at
FROM dk.patient_geo_clusters
WHERE cluster_id >= 0;

-- Unique index for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_clusters_unique 
    ON dk.mvw_patient_geo_clusters (cluster_id);

-- Additional indexes
CREATE INDEX IF NOT EXISTS idx_mvw_clusters_underserved 
    ON dk.mvw_patient_geo_clusters (is_underserved);
CREATE INDEX IF NOT EXISTS idx_mvw_clusters_patients 
    ON dk.mvw_patient_geo_clusters (patient_count DESC);
CREATE INDEX IF NOT EXISTS idx_mvw_clusters_distance 
    ON dk.mvw_patient_geo_clusters (distance_to_nearest_branch_km DESC);

COMMENT ON MATERIALIZED VIEW dk.mvw_patient_geo_clusters IS 
    'ST-06 cached patient geo cluster results. Refresh after clustering algorithm.';

-- ============================================================
-- Materialized View: mvw_whitespace_opportunity
-- Purpose: Cached expansion site recommendations
-- Unique Key: cluster_id (one row per opportunity)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_whitespace_opportunity AS
SELECT 
    cl.cluster_id,
    cl.cluster_label,
    cl.centroid_lat,
    cl.centroid_lng,
    cl.patient_count,
    cl.cluster_radius_km,
    cl.dominant_state,
    cl.dominant_city,
    cl.total_revenue,
    cl.avg_revenue_per_patient,
    cl.nearest_branch,
    cl.distance_to_nearest_branch_km,
    cl.is_underserved,
    bm.branch_name                                               AS nearest_branch_name,
    bm.city                                                      AS nearest_branch_city,
    ROUND(cl.patient_count * cl.avg_revenue_per_patient * 12, 0) AS est_annual_market_rm,
    ROUND(
        (cl.patient_count::NUMERIC / NULLIF(MAX(cl.patient_count) OVER(),0))
        * (cl.distance_to_nearest_branch_km / NULLIF(MAX(cl.distance_to_nearest_branch_km) OVER(),0))
        * 100, 1
    )                                                            AS site_priority_score,
    CASE
        WHEN cl.patient_count > 50 AND cl.distance_to_nearest_branch_km > 20 THEN 'High Priority'
        WHEN cl.patient_count > 20 AND cl.distance_to_nearest_branch_km > 10 THEN 'Medium Priority'
        ELSE 'Monitor'
    END                                                          AS expansion_priority,
    cl.computed_at
FROM dk.patient_geo_clusters cl
LEFT JOIN dk.branch_master bm ON cl.nearest_branch = bm.branch_code
WHERE cl.cluster_id >= 0
ORDER BY site_priority_score DESC;

-- Unique index for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_whitespace_unique 
    ON dk.mvw_whitespace_opportunity (cluster_id);

-- Additional indexes
CREATE INDEX IF NOT EXISTS idx_mvw_whitespace_priority 
    ON dk.mvw_whitespace_opportunity (expansion_priority);
CREATE INDEX IF NOT EXISTS idx_mvw_whitespace_score 
    ON dk.mvw_whitespace_opportunity (site_priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_mvw_whitespace_underserved 
    ON dk.mvw_whitespace_opportunity (is_underserved);

COMMENT ON MATERIALIZED VIEW dk.mvw_whitespace_opportunity IS 
    'ST-06 cached expansion site recommendations. Refresh after clustering.';

-- ============================================================================
-- SECTION 2: REFRESH FUNCTION
-- ============================================================================

-- ============================================================
-- Function: refresh_geo_mvws()
-- Purpose: Refresh all 6 ST-06 materialized views concurrently
-- Returns: Table with view name, status, and duration
-- ============================================================

CREATE OR REPLACE FUNCTION dk.refresh_geo_mvws()
RETURNS TABLE (
    mvw_name VARCHAR(100),
    status VARCHAR(50),
    duration_ms FLOAT
) AS $$
DECLARE
    view_record RECORD;
    start_time TIMESTAMP;
    duration_ms FLOAT;
BEGIN
    -- Array of materialized views to refresh (in dependency order)
    FOR view_record IN 
        SELECT unnest(ARRAY[
            'mvw_patient_geo_enriched',      -- Base patient data
            'mvw_branch_patient_summary',    -- Branch metrics (depends on patient data)
            'mvw_catchment_analysis',        -- Distance bands (depends on branch data)
            'mvw_cannibalization_summary',   -- Cannibalization (depends on branch data)
            'mvw_patient_geo_clusters',      -- Clusters (base clustering)
            'mvw_whitespace_opportunity'     -- Expansion (depends on clusters)
        ]) AS view_name
    LOOP
        start_time := clock_timestamp();
        
        BEGIN
            -- Try CONCURRENTLY refresh first (non-blocking)
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', 
                          'dk.' || view_record.view_name);
            duration_ms := EXTRACT(EPOCH FROM (clock_timestamp() - start_time)) * 1000;
            
            mvw_name := view_record.view_name;
            status := 'SUCCESS';
            duration_ms := duration_ms;
            RETURN NEXT;
            
        EXCEPTION 
            WHEN feature_not_supported THEN
                -- Fall back to non-concurrent refresh if concurrently not supported
                BEGIN
                    EXECUTE format('REFRESH MATERIALIZED VIEW %I', 
                                  'dk.' || view_record.view_name);
                    duration_ms := EXTRACT(EPOCH FROM (clock_timestamp() - start_time)) * 1000;
                    
                    mvw_name := view_record.view_name;
                    status := 'SUCCESS (non-concurrent)';
                    duration_ms := duration_ms;
                    RETURN NEXT;
                EXCEPTION WHEN OTHERS THEN
                    mvw_name := view_record.view_name;
                    status := 'FAILED: ' || SQLERRM;
                    duration_ms := 0;
                    RETURN NEXT;
                END;
            WHEN OTHERS THEN
                -- Handle other errors
                BEGIN
                    EXECUTE format('REFRESH MATERIALIZED VIEW %I', 
                                  'dk.' || view_record.view_name);
                    duration_ms := EXTRACT(EPOCH FROM (clock_timestamp() - start_time)) * 1000;
                    
                    mvw_name := view_record.view_name;
                    status := 'SUCCESS (fallback)';
                    duration_ms := duration_ms;
                    RETURN NEXT;
                EXCEPTION WHEN OTHERS THEN
                    mvw_name := view_record.view_name;
                    status := 'FAILED: ' || SQLERRM;
                    duration_ms := 0;
                    RETURN NEXT;
                END;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.refresh_geo_mvws() IS 
    'Refreshes all 6 ST-06 geospatial materialized views. Uses CONCURRENTLY where supported.';

-- ============================================================================
-- SECTION 3: GRANT PERMISSIONS
-- ============================================================================

-- Grant execute on refresh function
GRANT EXECUTE ON FUNCTION dk.refresh_geo_mvws() TO healthcare_bi_admin;
GRANT EXECUTE ON FUNCTION dk.refresh_geo_mvws() TO healthcare_bi_app;

-- Grant SELECT on materialized views
GRANT SELECT ON dk.mvw_patient_geo_enriched TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_branch_patient_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_catchment_analysis TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_cannibalization_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_patient_geo_clusters TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_whitespace_opportunity TO healthcare_bi_reader;

GRANT SELECT ON dk.mvw_patient_geo_enriched TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_branch_patient_summary TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_catchment_analysis TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_cannibalization_summary TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_patient_geo_clusters TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_whitespace_opportunity TO healthcare_bi_app;

-- ============================================================================
-- END OF MATERIALIZED VIEWS
-- ============================================================================