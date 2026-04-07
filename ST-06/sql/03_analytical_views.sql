-- ============================================================
-- HEALTHCARE GROUP — GEOSPATIAL ANALYTICS SOLUTION
-- FILE 03: Distance Matrix and Analytical Views
-- Database: PostgreSQL + PostGIS  |  Schema: dk
-- ============================================================
-- Purpose: Calculate patient-branch distances, distance bands,
--          nearest branch flags, and catchment analysis
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- STEP 1: DISTANCE MATRIX CALCULATION FUNCTION
-- Calculates Haversine distance between all patients and branches
-- ─────────────────────────────────────────────────────────────

-- Function to populate patient_branch_distance table
CREATE OR REPLACE FUNCTION dk.calculate_patient_branch_distances()
RETURNS INTEGER AS $$
DECLARE
    v_rows_inserted INTEGER;
    v_start_time TIMESTAMPTZ;
BEGIN
    v_start_time := NOW();
    
    -- Clear existing data (full refresh)
    TRUNCATE dk.patient_branch_distance;
    
    -- Calculate distances for all patient-branch pairs using Haversine formula
    -- Earth radius = 6371 km
    INSERT INTO dk.patient_branch_distance (
        mrn,
        patient_location,
        branch_code,
        distance_km,
        distance_band,
        est_drive_min,
        is_nearest_branch,
        is_within_catchment,
        route_line,
        computed_at
    )
    WITH patient_branch_pairs AS (
        SELECT 
            pg.mrn,
            pg.location AS patient_location,
            bm.branch_code,
            bm.catchment_radius_km,
            -- Haversine formula: calculates great-circle distance between two points
            -- Uses Earth radius of 6371 km
            6371.0 * ACOS(
                LEAST(1.0, GREATEST(-1.0,
                    SIN(RADIANS(pg.patient_lat)) * SIN(RADIANS(bm.branch_lat)) +
                    COS(RADIANS(pg.patient_lat)) * COS(RADIANS(bm.branch_lat)) *
                    COS(RADIANS(bm.branch_lng - pg.patient_lng))
                ))
            ) AS distance_km,
            pg.geo_point AS patient_point,
            bm.geo_point AS branch_point
        FROM dk.patient_geocode pg
        CROSS JOIN dk.branch_master bm
        WHERE pg.patient_lat IS NOT NULL 
          AND pg.patient_lng IS NOT NULL
          AND bm.branch_lat IS NOT NULL 
          AND bm.branch_lng IS NOT NULL
          AND bm.is_active = TRUE
    ),
    distance_with_bands AS (
        SELECT 
            mrn,
            patient_location,
            branch_code,
            catchment_radius_km,
            ROUND(distance_km::NUMERIC, 3) AS distance_km,
            -- Distance band classification
            CASE 
                WHEN distance_km < 2 THEN '<2km'
                WHEN distance_km >= 2 AND distance_km < 5 THEN '2-5km'
                WHEN distance_km >= 5 AND distance_km < 10 THEN '5-10km'
                WHEN distance_km >= 10 AND distance_km < 20 THEN '10-20km'
                ELSE '20km+'
            END AS distance_band,
            -- Drive time estimation: road distance ≈ 1.3× straight-line / 30 km/h average
            ROUND((distance_km * 1.3 / 30.0 * 60)::NUMERIC, 1) AS est_drive_min,
            patient_point,
            branch_point
        FROM patient_branch_pairs
    ),
    nearest_branch AS (
        -- Identify nearest branch for each patient using dense_rank
        SELECT 
            mrn,
            patient_location,
            branch_code,
            distance_km,
            distance_band,
            est_drive_min,
            patient_point,
            branch_point,
            catchment_radius_km,
            DENSE_RANK() OVER (
                PARTITION BY mrn, patient_location 
                ORDER BY distance_km ASC
            ) AS distance_rank
        FROM distance_with_bands
    )
    SELECT 
        mrn,
        patient_location,
        branch_code,
        distance_km,
        distance_band,
        est_drive_min,
        -- Flag nearest branch (rank = 1)
        CASE WHEN distance_rank = 1 THEN TRUE ELSE FALSE END AS is_nearest_branch,
        -- Flag if within branch's catchment radius
        CASE WHEN distance_km <= catchment_radius_km THEN TRUE ELSE FALSE END AS is_within_catchment,
        -- Line geometry for visualization
        ST_MakeLine(patient_point, branch_point) AS route_line,
        NOW() AS computed_at
    FROM nearest_branch;
    
    -- Get count of inserted rows
    SELECT COUNT(*) INTO v_rows_inserted FROM dk.patient_branch_distance;
    
    -- Log the execution
    RAISE NOTICE 'Distance matrix calculation completed: % patient-branch pairs inserted', v_rows_inserted;
    
    RETURN v_rows_inserted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.calculate_patient_branch_distances() IS 
'Calculates Haversine distances between all patients and branches. Populates dk.patient_branch_distance with distance bands, nearest branch flags, and catchment flags.';

-- ─────────────────────────────────────────────────────────────
-- STEP 2: ANALYTICAL VIEWS FOR POWER BI
-- ─────────────────────────────────────────────────────────────

-- ------------------------------------------------------------
-- View: vw_patient_nearest_branch
-- Purpose: Each patient with their nearest branch only
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_patient_nearest_branch AS
SELECT 
    pbd.mrn AS patient_id,
    pbd.patient_location,
    pbd.branch_code AS nearest_branch_code,
    bm.branch_name AS nearest_branch_name,
    bm.state AS nearest_branch_state,
    bm.city AS nearest_branch_city,
    ROUND(pbd.distance_km::NUMERIC, 2) AS distance_to_nearest_km,
    pbd.distance_band,
    pbd.est_drive_min AS drive_time_to_nearest_min,
    pbd.is_within_catchment,
    pg.zip AS patient_postcode,
    pg.city_name AS patient_city,
    pg.state_name AS patient_state
    
FROM dk.patient_branch_distance pbd
JOIN dk.branch_master bm ON pbd.branch_code = bm.branch_code
JOIN dk.patient_geocode pg ON pbd.mrn = pg.mrn AND pbd.patient_location = pg.location
WHERE pbd.is_nearest_branch = TRUE
  AND pg.geocode_at = (
      SELECT MAX(pg2.geocode_at) 
      FROM dk.patient_geocode pg2 
      WHERE pg2.mrn = pg.mrn AND pg2.location = pg.location
  );

COMMENT ON VIEW dk.vw_patient_nearest_branch IS 'Each patient with their nearest branch details. One row per patient.';

-- ------------------------------------------------------------
-- View: vw_branch_catchment_summary
-- Purpose: Branch-level catchment analysis
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_branch_catchment_summary AS
SELECT 
    bm.branch_code,
    bm.branch_name,
    bm.state,
    bm.city,
    bm.catchment_radius_km,
    
    -- Patient counts by distance band
    COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch THEN pbd.mrn END) AS total_patients_nearest,
    COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_band = '<2km' THEN pbd.mrn END) AS patients_0_2km,
    COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_band = '2-5km' THEN pbd.mrn END) AS patients_2_5km,
    COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_band = '5-10km' THEN pbd.mrn END) AS patients_5_10km,
    COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_band = '10-20km' THEN pbd.mrn END) AS patients_10_20km,
    COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_band = '20km+' THEN pbd.mrn END) AS patients_20km_plus,
    
    -- Catchment metrics
    COUNT(DISTINCT CASE WHEN pbd.is_within_catchment AND pbd.is_nearest_branch THEN pbd.mrn END) AS patients_within_catchment,
    COUNT(DISTINCT CASE WHEN NOT pbd.is_within_catchment AND pbd.is_nearest_branch THEN pbd.mrn END) AS patients_outside_catchment,
    
    -- Catchment penetration rate
    CASE 
        WHEN COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch THEN pbd.mrn END) > 0 THEN
            ROUND(
                COUNT(DISTINCT CASE WHEN pbd.is_within_catchment AND pbd.is_nearest_branch THEN pbd.mrn END)::NUMERIC /
                COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch THEN pbd.mrn END) * 100, 2
            )
        ELSE 0
    END AS catchment_penetration_pct,
    
    -- Average distance
    ROUND(AVG(CASE WHEN pbd.is_nearest_branch THEN pbd.distance_km END)::NUMERIC, 2) AS avg_distance_km,
    
    -- Median distance (using percentile_cont)
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pbd.distance_km) FILTER (WHERE pbd.is_nearest_branch)::NUMERIC, 2) AS median_distance_km
    
FROM dk.branch_master bm
LEFT JOIN dk.patient_branch_distance pbd ON bm.branch_code = pbd.branch_code
WHERE bm.is_active = TRUE
GROUP BY bm.branch_code, bm.branch_name, bm.state, bm.city, bm.catchment_radius_km;

COMMENT ON VIEW dk.vw_branch_catchment_summary IS 'Branch-level catchment analysis with patient counts by distance band and penetration rates.';

-- ------------------------------------------------------------
-- View: vw_distance_band_analysis
-- Purpose: Distance distribution analysis
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_distance_band_analysis AS
SELECT 
    pbd.distance_band,
    COUNT(DISTINCT pbd.mrn) AS unique_patients,
    COUNT(DISTINCT pbd.branch_code) AS unique_branches,
    COUNT(*) AS total_patient_branch_pairs,
    
    -- Average distance within band
    ROUND(AVG(pbd.distance_km)::NUMERIC, 2) AS avg_distance_km,
    ROUND(MIN(pbd.distance_km)::NUMERIC, 2) AS min_distance_km,
    ROUND(MAX(pbd.distance_km)::NUMERIC, 2) AS max_distance_km,
    
    -- Nearest branch counts
    COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch THEN pbd.mrn END) AS patients_with_nearest,
    
    -- Within catchment counts
    COUNT(DISTINCT CASE WHEN pbd.is_within_catchment AND pbd.is_nearest_branch THEN pbd.mrn END) AS patients_within_catchment,
    
    -- Percentage distribution
    ROUND(
        COUNT(DISTINCT pbd.mrn)::NUMERIC / 
        (SELECT COUNT(DISTINCT mrn) FROM dk.patient_geocode WHERE patient_lat IS NOT NULL) * 100, 2
    ) AS pct_of_total_patients
    
FROM dk.patient_branch_distance pbd
WHERE pbd.is_nearest_branch = TRUE
GROUP BY pbd.distance_band
ORDER BY 
    CASE pbd.distance_band
        WHEN '<2km' THEN 1
        WHEN '2-5km' THEN 2
        WHEN '5-10km' THEN 3
        WHEN '10-20km' THEN 4
        WHEN '20km+' THEN 5
    END;

COMMENT ON VIEW dk.vw_distance_band_analysis IS 'Distance band distribution analysis showing patient counts and percentages per band.';

-- ------------------------------------------------------------
-- View: vw_patient_multiple_branches
-- Purpose: Patients visiting multiple branches (cannibalization indicator)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_patient_multiple_branches AS
SELECT 
    pcd.mrn AS patient_id,
    pcd.location AS patient_location,
    COUNT(DISTINCT cr.branch) AS branches_visited,
    ARRAY_AGG(DISTINCT cr.branch) AS branch_list,
    pg.state_name AS patient_state,
    pg.city_name AS patient_city,
    
    -- Distance to nearest branch
    pbd_nearest.distance_km AS distance_to_nearest_km,
    pbd_nearest.branch_code AS nearest_branch_code,
    
    -- Is patient visiting non-nearest branches?
    CASE 
        WHEN COUNT(DISTINCT cr.branch) > 1 AND 
             NOT ARRAY[pbd_nearest.branch_code] <@ ARRAY_AGG(cr.branch) 
        THEN TRUE 
        ELSE FALSE 
    END AS visits_non_nearest_branch,
    
    -- Average distance of visited branches from patient home
    ROUND(AVG(pbd_all.distance_km)::NUMERIC, 2) AS avg_visited_branch_distance_km
    
FROM dk.patient_geocode pcd
JOIN (
    SELECT DISTINCT cr1.mrn, cr1.location, cr1.branch
    FROM dk.collection_report cr1
    WHERE cr1.branch IS NOT NULL
) cr ON pcd.mrn = cr.mrn AND pcd.location = cr.location
JOIN dk.patient_branch_distance pbd_all ON cr.mrn = pbd_all.mrn AND cr.location = pbd_all.patient_location AND cr.branch = pbd_all.branch_code
LEFT JOIN dk.patient_branch_distance pbd_nearest ON pcd.mrn = pbd_nearest.mrn AND pcd.location = pbd_nearest.patient_location AND pbd_nearest.is_nearest_branch = TRUE
JOIN dk.patient_geocode pg ON pcd.mrn = pg.mrn AND pcd.location = pg.location
WHERE pcd.patient_lat IS NOT NULL AND pcd.patient_lng IS NOT NULL
GROUP BY pcd.mrn, pcd.location, pg.state_name, pg.city_name, 
         pbd_nearest.distance_km, pbd_nearest.branch_code
HAVING COUNT(DISTINCT cr.branch) > 1;

COMMENT ON VIEW dk.vw_patient_multiple_branches IS 'Patients visiting multiple branches - key indicator for cannibalization analysis.';

-- ------------------------------------------------------------
-- View: vw_catchment_overlap
-- Purpose: Branch catchment area overlap analysis
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_catchment_overlap AS
SELECT 
    b1.branch_code AS branch_a_code,
    b1.branch_name AS branch_a_name,
    b1.state AS branch_a_state,
    b1.city AS branch_a_city,
    b2.branch_code AS branch_b_code,
    b2.branch_name AS branch_b_name,
    b2.state AS branch_b_state,
    b2.city AS branch_b_city,
    
    -- Distance between branches
    ROUND(
        6371.0 * ACOS(
            LEAST(1.0, GREATEST(-1.0,
                SIN(RADIANS(b1.branch_lat)) * SIN(RADIANS(b2.branch_lat)) +
                COS(RADIANS(b1.branch_lat)) * COS(RADIANS(b2.branch_lat)) *
                COS(RADIANS(b2.branch_lng - b1.branch_lng))
            ))
        )::NUMERIC, 2
    ) AS branch_distance_km,
    
    -- Combined catchment radius
    b1.catchment_radius_km + b2.catchment_radius_km AS combined_catchment_km,
    
    -- Do catchments overlap?
    CASE 
        WHEN 6371.0 * ACOS(
            LEAST(1.0, GREATEST(-1.0,
                SIN(RADIANS(b1.branch_lat)) * SIN(RADIANS(b2.branch_lat)) +
                COS(RADIANS(b1.branch_lat)) * COS(RADIANS(b2.branch_lat)) *
                COS(RADIANS(b2.branch_lng - b1.branch_lng))
            ))
        ) < (b1.catchment_radius_km + b2.catchment_radius_km)
        THEN TRUE 
        ELSE FALSE 
    END AS catchments_overlap,
    
    -- Shared patients (nearest to both)
    COUNT(DISTINCT CASE 
        WHEN p1.is_nearest_branch AND p2.is_nearest_branch 
        THEN p1.mrn 
    END) AS shared_nearest_patients
    
FROM dk.branch_master b1
CROSS JOIN dk.branch_master b2
LEFT JOIN dk.patient_branch_distance p1 ON b1.branch_code = p1.branch_code AND p1.is_nearest_branch
LEFT JOIN dk.patient_branch_distance p2 ON b2.branch_code = p2.branch_code AND p2.is_nearest_branch AND p1.mrn = p2.mrn AND p1.patient_location = p2.patient_location
WHERE b1.branch_code < b2.branch_code  -- Avoid duplicate pairs
  AND b1.is_active = TRUE 
  AND b2.is_active = TRUE
GROUP BY b1.branch_code, b1.branch_name, b1.state, b1.city, b1.catchment_radius_km,
         b2.branch_code, b2.branch_name, b2.state, b2.city, b2.catchment_radius_km,
         b1.branch_lat, b1.branch_lng, b2.branch_lat, b2.branch_lng
HAVING 6371.0 * ACOS(
        LEAST(1.0, GREATEST(-1.0,
            SIN(RADIANS(b1.branch_lat)) * SIN(RADIANS(b2.branch_lat)) +
            COS(RADIANS(b1.branch_lat)) * COS(RADIANS(b2.branch_lat)) *
            COS(RADIANS(b2.branch_lng - b1.branch_lng))
        ))
    ) < (b1.catchment_radius_km + b2.catchment_radius_km) * 2;  -- Only show relatively close pairs

COMMENT ON VIEW dk.vw_catchment_overlap IS 'Branch catchment area overlap analysis showing overlapping branches and shared patients.';

-- ─────────────────────────────────────────────────────────────
-- STEP 3: GRANT PERMISSIONS (Initial views)
-- ─────────────────────────────────────────────────────────────

GRANT EXECUTE ON FUNCTION dk.calculate_patient_branch_distances() TO healthcare_bi_admin;
GRANT EXECUTE ON FUNCTION dk.calculate_patient_branch_distances() TO healthcare_bi_app;

GRANT SELECT ON dk.vw_patient_nearest_branch TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_branch_catchment_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_distance_band_analysis TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_multiple_branches TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_catchment_overlap TO healthcare_bi_reader;

GRANT SELECT ON dk.vw_patient_nearest_branch TO healthcare_bi_app;
GRANT SELECT ON dk.vw_branch_catchment_summary TO healthcare_bi_app;
GRANT SELECT ON dk.vw_distance_band_analysis TO healthcare_bi_app;
GRANT SELECT ON dk.vw_patient_multiple_branches TO healthcare_bi_app;
GRANT SELECT ON dk.vw_catchment_overlap TO healthcare_bi_app;

-- ============================================================
-- TASK 11: ANALYTICAL VIEWS FOR POWER BI
-- 7 Required Views for Geospatial Analytics
-- ============================================================

-- ------------------------------------------------------------
-- View 1: vw_patient_geo_enriched
-- Patient + geocode + distance (NO PII: phone, full address)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_patient_geo_enriched AS
SELECT
    p.mrn,
    p.location                                                    AS registered_branch,
    -- Demographics (NO PII - no phone, no full address)
    CASE
        WHEN LOWER(p.gender) IN ('m','male')   THEN 'Male'
        WHEN LOWER(p.gender) IN ('f','female') THEN 'Female'
        ELSE 'Other/Unknown'
    END                                                           AS gender_clean,
    DATE_PART('year', AGE(CURRENT_DATE, p.dob))::INT             AS age,
    CASE
        WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 25   THEN '18-24'
        WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 35   THEN '25-34'
        WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 45   THEN '35-44'
        WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 55   THEN '45-54'
        WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 65   THEN '55-64'
        ELSE '65+'
    END                                                           AS age_band,
    COALESCE(NULLIF(TRIM(p.race_name),''), 'Unknown')            AS race_clean,
    -- Location (minimal - no full address line)
    p.city_name,
    p.state_name,
    p.zip,
    -- Geocode
    g.patient_lat,
    g.patient_lng,
    g.geocode_quality,
    g.geocode_source,
    -- Nearest branch assignment
    pbd.branch_code                                               AS nearest_branch,
    pbd.distance_km                                               AS dist_to_nearest_km,
    pbd.distance_band                                             AS nearest_branch_dist_band,
    pbd.est_drive_min                                             AS est_drive_min_to_nearest,
    pbd.is_within_catchment,
    -- Revenue summary
    txn.total_visits,
    txn.lifetime_revenue,
    txn.skincare_revenue,
    txn.package_revenue,
    txn.last_visit_date,
    txn.first_visit_date,
    txn.visited_branches,
    CURRENT_TIMESTAMP                                            AS computed_at

FROM dk.patient p
LEFT JOIN dk.patient_geocode g
    ON p.mrn = g.mrn AND p.location = g.location
LEFT JOIN dk.patient_branch_distance pbd
    ON p.mrn = pbd.mrn AND p.location = pbd.patient_location
    AND pbd.is_nearest_branch = TRUE
LEFT JOIN (
    SELECT
        mrn,
        COUNT(DISTINCT sale_order_no)                            AS total_visits,
        SUM(COALESCE(standalone_sales_subtotal_rm,0) + COALESCE(package_sales_subtotal_rm,0)) AS lifetime_revenue,
        SUM(COALESCE(standalone_sales_skincare_product_amount_rm,0) +
            COALESCE(package_sales_skincare_product_amount_rm,0)) AS skincare_revenue,
        SUM(COALESCE(package_sales_subtotal_rm,0))               AS package_revenue,
        MAX(csv_date)                                            AS last_visit_date,
        MIN(csv_date)                                            AS first_visit_date,
        ARRAY_AGG(DISTINCT branch ORDER BY branch)               AS visited_branches
    FROM dk.collection_report
    WHERE status NOT ILIKE '%void%'
      AND status NOT ILIKE '%cancel%'
    GROUP BY mrn
) txn ON p.mrn = txn.mrn
WHERE g.patient_lat IS NOT NULL AND g.patient_lng IS NOT NULL;

COMMENT ON VIEW dk.vw_patient_geo_enriched IS 'Patient data with geocode and nearest branch. Excludes PII (phone, full address). For Power BI geospatial analytics.';

-- ------------------------------------------------------------
-- View 2: vw_branch_patient_summary
-- Branch-level patient metrics
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_branch_patient_summary AS
WITH patient_branch_agg AS (
    SELECT
        pbd.branch_code,
        COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch THEN pbd.mrn END)   AS primary_patients,
        COUNT(DISTINCT pbd.mrn)                                              AS total_reached_patients,
        AVG(CASE WHEN pbd.is_nearest_branch THEN pbd.distance_km END)       AS avg_dist_km,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            CASE WHEN pbd.is_nearest_branch THEN pbd.distance_km END)       AS median_dist_km,
        MAX(CASE WHEN pbd.is_nearest_branch THEN pbd.distance_km END)       AS max_dist_km,
        COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_km < 2
                            THEN pbd.mrn END)                               AS patients_under_2km,
        COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_km BETWEEN 2 AND 5
                            THEN pbd.mrn END)                               AS patients_2_5km,
        COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_km BETWEEN 5 AND 10
                            THEN pbd.mrn END)                               AS patients_5_10km,
        COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_km BETWEEN 10 AND 20
                            THEN pbd.mrn END)                               AS patients_10_20km,
        COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.distance_km > 20
                            THEN pbd.mrn END)                               AS patients_over_20km,
        COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND pbd.is_within_catchment
                            THEN pbd.mrn END)                               AS catchment_patients,
        COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND NOT pbd.is_within_catchment
                            THEN pbd.mrn END)                               AS beyond_catchment_patients
    FROM dk.patient_branch_distance pbd
    GROUP BY pbd.branch_code
),
branch_revenue AS (
    SELECT
        cr.branch,
        COUNT(DISTINCT cr.mrn)                                               AS transacting_patients,
        COUNT(DISTINCT cr.sale_order_no)                                     AS total_transactions,
        SUM(COALESCE(cr.standalone_sales_subtotal_rm,0) +
            COALESCE(cr.package_sales_subtotal_rm,0))                        AS total_revenue,
        SUM(COALESCE(cr.standalone_sales_skincare_product_amount_rm,0) +
            COALESCE(cr.package_sales_skincare_product_amount_rm,0))         AS skincare_revenue,
        SUM(COALESCE(cr.package_sales_subtotal_rm,0))                        AS package_revenue,
        AVG(COALESCE(cr.standalone_sales_subtotal_rm,0) +
            COALESCE(cr.package_sales_subtotal_rm,0))                        AS avg_basket,
        MAX(cr.csv_date)                                                     AS last_txn_date
    FROM dk.collection_report cr
    WHERE cr.status NOT ILIKE '%void%'
    GROUP BY cr.branch
)
SELECT
    bm.branch_code,
    bm.branch_name,
    bm.entity,
    bm.city,
    bm.state,
    bm.branch_lat,
    bm.branch_lng,
    bm.catchment_radius_km,
    bm.is_active,
    bm.opened_date,
    bm.branch_type,
    pa.primary_patients,
    pa.total_reached_patients,
    ROUND(pa.avg_dist_km::NUMERIC, 2)                                      AS avg_dist_km,
    ROUND(pa.median_dist_km::NUMERIC, 2)                                    AS median_dist_km,
    ROUND(pa.max_dist_km::NUMERIC, 2)                                      AS max_dist_km,
    pa.patients_under_2km,
    pa.patients_2_5km,
    pa.patients_5_10km,
    pa.patients_10_20km,
    pa.patients_over_20km,
    pa.catchment_patients,
    pa.beyond_catchment_patients,
    ROUND(pa.catchment_patients::NUMERIC /
          NULLIF(pa.primary_patients,0) * 100, 1)                            AS catchment_coverage_pct,
    br.transacting_patients,
    br.total_transactions,
    br.total_revenue,
    br.skincare_revenue,
    br.package_revenue,
    ROUND(br.avg_basket::NUMERIC, 2)                                        AS avg_basket,
    br.last_txn_date,
    ROUND(br.total_revenue / NULLIF(br.transacting_patients,0), 2)           AS revenue_per_patient,
    CURRENT_TIMESTAMP                                                        AS computed_at
FROM dk.branch_master bm
LEFT JOIN patient_branch_agg pa ON bm.branch_code = pa.branch_code
LEFT JOIN branch_revenue br ON bm.branch_code = br.branch
WHERE bm.is_active = TRUE;

COMMENT ON VIEW dk.vw_branch_patient_summary IS 'Branch-level patient metrics including distance distribution and revenue. For Power BI dashboard KPIs.';

-- ------------------------------------------------------------
-- View 3: vw_new_patient_growth_geo
-- Geographic new patient acquisition
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_new_patient_growth_geo AS
WITH first_visits AS (
    SELECT
        cr.mrn,
        cr.branch,
        MIN(cr.csv_date)                                         AS first_visit_date,
        DATE_TRUNC('month', MIN(cr.csv_date))                   AS cohort_month
    FROM dk.collection_report cr
    WHERE cr.status NOT ILIKE '%void%'
      AND cr.status NOT ILIKE '%cancel%'
    GROUP BY cr.mrn, cr.branch
),
new_patients_with_geo AS (
    SELECT
        fv.mrn,
        fv.branch,
        fv.first_visit_date,
        fv.cohort_month,
        pbd.distance_km,
        pbd.distance_band,
        pbd.is_within_catchment,
        pg.geocode_quality,
        pa.gender_clean,
        pa.age_band,
        pa.race_clean,
        pa.state_name                                            AS patient_state,
        pa.city_name                                             AS patient_city,
        cr_first.first_visit_revenue,
        cr_first.first_skincare_spend
    FROM first_visits fv
    LEFT JOIN dk.patient_branch_distance pbd
        ON fv.mrn = pbd.mrn AND fv.branch = pbd.branch_code
    LEFT JOIN dk.patient_geocode pg
        ON fv.mrn = pg.mrn
    LEFT JOIN (
        SELECT
            p.mrn,
            CASE WHEN LOWER(p.gender) IN ('m','male') THEN 'Male'
                 WHEN LOWER(p.gender) IN ('f','female') THEN 'Female'
                 ELSE 'Other/Unknown' END                        AS gender_clean,
            CASE
                WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 25 THEN '18-24'
                WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 35 THEN '25-34'
                WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 45 THEN '35-44'
                WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 55 THEN '45-54'
                WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 65 THEN '55-64'
                ELSE '65+'
            END                                                  AS age_band,
            COALESCE(NULLIF(TRIM(p.race_name),''), 'Unknown')   AS race_clean,
            p.city_name,
            p.state_name
        FROM dk.patient p
    ) pa ON fv.mrn = pa.mrn
    LEFT JOIN (
        SELECT
            cr.mrn,
            cr.branch,
            MIN(cr.csv_date)                                     AS first_date,
            SUM(COALESCE(cr.standalone_sales_subtotal_rm,0) +
                COALESCE(cr.package_sales_subtotal_rm,0))       AS first_visit_revenue,
            SUM(COALESCE(cr.standalone_sales_skincare_product_amount_rm,0) +
                COALESCE(cr.package_sales_skincare_product_amount_rm,0)) AS first_skincare_spend
        FROM dk.collection_report cr
        GROUP BY cr.mrn, cr.branch
    ) cr_first ON fv.mrn = cr_first.mrn AND fv.branch = cr_first.branch
)
SELECT
    np.*,
    bm.branch_name,
    bm.entity,
    bm.city                                                      AS branch_city,
    bm.state                                                     AS branch_state,
    bm.branch_lat,
    bm.branch_lng,
    CURRENT_TIMESTAMP                                            AS computed_at
FROM new_patients_with_geo np
LEFT JOIN dk.branch_master bm ON np.branch = bm.branch_code;

COMMENT ON VIEW dk.vw_new_patient_growth_geo IS 'New patient acquisition by branch, month, and distance band. For Power BI geographic growth analysis.';

-- ------------------------------------------------------------
-- View 4: vw_catchment_analysis
-- Distance band analysis by branch
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_catchment_analysis AS
SELECT
    pbd.branch_code,
    bm.branch_name,
    bm.entity,
    bm.city                                                      AS branch_city,
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
    pbd.branch_code, bm.branch_name, bm.entity, bm.city,
    bm.catchment_radius_km, pbd.distance_band, pbd.is_within_catchment,
    pa.gender_clean, pa.age_band, pa.race_clean, pa.state_name;

COMMENT ON VIEW dk.vw_catchment_analysis IS 'Distance band analysis by branch. Shows revenue and demographics by catchment vs traveling patients.';

-- ------------------------------------------------------------
-- View 5: vw_cannibalization_detail
-- Detailed branch pair analysis
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_cannibalization_detail AS
WITH multi_branch_patients AS (
    SELECT
        cr.mrn,
        ARRAY_AGG(DISTINCT cr.branch ORDER BY cr.branch)        AS branches_visited,
        COUNT(DISTINCT cr.branch)                               AS branch_count,
        SUM(COALESCE(cr.standalone_sales_subtotal_rm,0) +
            COALESCE(cr.package_sales_subtotal_rm,0))           AS total_spend,
        MAX(cr.csv_date)                                        AS last_visit,
        MIN(cr.csv_date)                                        AS first_visit
    FROM dk.collection_report cr
    WHERE cr.status NOT ILIKE '%void%'
    GROUP BY cr.mrn
    HAVING COUNT(DISTINCT cr.branch) > 1
),
branch_pairs AS (
    SELECT
        mbp.mrn,
        mbp.branch_count,
        mbp.total_spend,
        b1.branch                                               AS branch_a,
        b2.branch                                               AS branch_b,
        a_rev.branch_revenue                                    AS revenue_at_branch_a,
        b_rev.branch_revenue                                    AS revenue_at_branch_b
    FROM multi_branch_patients mbp
    CROSS JOIN LATERAL UNNEST(mbp.branches_visited) AS b1(branch)
    CROSS JOIN LATERAL UNNEST(mbp.branches_visited) AS b2(branch)
    LEFT JOIN (
        SELECT mrn, branch,
               SUM(COALESCE(standalone_sales_subtotal_rm,0) +
                   COALESCE(package_sales_subtotal_rm,0)) AS branch_revenue
        FROM dk.collection_report
        WHERE status NOT ILIKE '%void%'
        GROUP BY mrn, branch
    ) a_rev ON mbp.mrn = a_rev.mrn AND b1.branch = a_rev.branch
    LEFT JOIN (
        SELECT mrn, branch,
               SUM(COALESCE(standalone_sales_subtotal_rm,0) +
                   COALESCE(package_sales_subtotal_rm,0)) AS branch_revenue
        FROM dk.collection_report
        WHERE status NOT ILIKE '%void%'
        GROUP BY mrn, branch
    ) b_rev ON mbp.mrn = b_rev.mrn AND b2.branch = b_rev.branch
    WHERE b1.branch < b2.branch
)
SELECT
    bp.mrn,
    bp.branch_count,
    bp.total_spend,
    bp.branch_a,
    bp.branch_b,
    bp.revenue_at_branch_a,
    bp.revenue_at_branch_b,
    pa.gender_clean,
    pa.age_band,
    pa.race_clean,
    pa.state_name,
    pg.patient_lat,
    pg.patient_lng,
    pbd_a.distance_km                                           AS dist_to_branch_a_km,
    pbd_b.distance_km                                           AS dist_to_branch_b_km,
    bm_dist.inter_branch_km,
    CASE
        WHEN pbd_a.distance_km <= pbd_b.distance_km THEN bp.branch_a
        ELSE bp.branch_b
    END                                                         AS geographically_closer_branch,
    CASE
        WHEN bp.revenue_at_branch_b > bp.revenue_at_branch_a
             AND pbd_b.distance_km > pbd_a.distance_km         THEN TRUE
        WHEN bp.revenue_at_branch_a > bp.revenue_at_branch_b
             AND pbd_a.distance_km > pbd_b.distance_km         THEN TRUE
        ELSE FALSE
    END                                                         AS prefers_farther_branch,
    CURRENT_TIMESTAMP                                           AS computed_at
FROM branch_pairs bp
LEFT JOIN (
    SELECT p.mrn,
        CASE WHEN LOWER(p.gender) IN ('m','male') THEN 'Male'
             WHEN LOWER(p.gender) IN ('f','female') THEN 'Female'
             ELSE 'Other/Unknown' END AS gender_clean,
        CASE
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 25 THEN '18-24'
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 35 THEN '25-34'
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 45 THEN '35-44'
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 55 THEN '45-54'
            WHEN DATE_PART('year', AGE(CURRENT_DATE, p.dob)) < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        COALESCE(NULLIF(TRIM(p.race_name),''), 'Unknown') AS race_clean,
        p.state_name
    FROM dk.patient p
) pa ON bp.mrn = pa.mrn
LEFT JOIN dk.patient_geocode pg ON bp.mrn = pg.mrn
LEFT JOIN dk.patient_branch_distance pbd_a
    ON bp.mrn = pbd_a.mrn AND bp.branch_a = pbd_a.branch_code
LEFT JOIN dk.patient_branch_distance pbd_b
    ON bp.mrn = pbd_b.mrn AND bp.branch_b = pbd_b.branch_code
LEFT JOIN (
    SELECT
        bm1.branch_code AS branch_a,
        bm2.branch_code AS branch_b,
        ROUND(
            6371.0 * ACOS(
                LEAST(1.0, GREATEST(-1.0,
                    SIN(RADIANS(bm1.branch_lat)) * SIN(RADIANS(bm2.branch_lat)) +
                    COS(RADIANS(bm1.branch_lat)) * COS(RADIANS(bm2.branch_lat)) *
                    COS(RADIANS(bm2.branch_lng - bm1.branch_lng))
                ))
            ), 3
        ) AS inter_branch_km
    FROM dk.branch_master bm1
    CROSS JOIN dk.branch_master bm2
    WHERE bm1.branch_code < bm2.branch_code
      AND bm1.branch_lat IS NOT NULL
      AND bm2.branch_lat IS NOT NULL
) bm_dist ON bp.branch_a = bm_dist.branch_a AND bp.branch_b = bm_dist.branch_b;

COMMENT ON VIEW dk.vw_cannibalization_detail IS 'Detailed branch pair analysis showing patients visiting multiple branches. For Power BI cannibalization drill-down.';

-- ------------------------------------------------------------
-- View 6: vw_cannibalization_summary
-- Aggregated cannibalization metrics
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_cannibalization_summary AS
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
    -- Alert flag
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

COMMENT ON VIEW dk.vw_cannibalization_summary IS 'Aggregated cannibalization metrics by branch pair. For Power BI cannibalization dashboard.';

-- ------------------------------------------------------------
-- View 7: vw_whitespace_opportunity
-- Expansion site recommendations
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dk.vw_whitespace_opportunity AS
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

COMMENT ON VIEW dk.vw_whitespace_opportunity IS 'Top expansion site recommendations based on patient clusters and distance from existing branches. For Power BI strategic planning.';

-- ============================================================
-- GRANT PERMISSIONS FOR TASK 11 VIEWS
-- ============================================================

GRANT SELECT ON dk.vw_patient_geo_enriched TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_branch_patient_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_new_patient_growth_geo TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_catchment_analysis TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_cannibalization_detail TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_cannibalization_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_whitespace_opportunity TO healthcare_bi_reader;

GRANT SELECT ON dk.vw_patient_geo_enriched TO healthcare_bi_app;
GRANT SELECT ON dk.vw_branch_patient_summary TO healthcare_bi_app;
GRANT SELECT ON dk.vw_new_patient_growth_geo TO healthcare_bi_app;
GRANT SELECT ON dk.vw_catchment_analysis TO healthcare_bi_app;
GRANT SELECT ON dk.vw_cannibalization_detail TO healthcare_bi_app;
GRANT SELECT ON dk.vw_cannibalization_summary TO healthcare_bi_app;
GRANT SELECT ON dk.vw_whitespace_opportunity TO healthcare_bi_app;

-- ============================================================
-- END OF ANALYTICAL VIEWS FOR POWER BI (TASK 11)
-- ============================================================
