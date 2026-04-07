-- ============================================================================
-- ST-04: Product & Package Performance Analytics
-- File: 04_materialized_views.sql
-- Description: Materialized views with proper indexes for Power BI
-- Schema: dk
-- Dependencies: All ST-04 views (vw_skincare_monthly, vw_package_composition, etc.)
-- Constraints from ST-01:
--   - All objects in schema: dk
--   - Use UNIQUE indexes for CONCURRENT refresh
--   - Follow naming convention: mvw_*
-- ============================================================================

-- ============================================================================
-- SECTION 1: Create Materialized Views
-- ============================================================================

-- MVW: Skincare Monthly Performance
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_skincare_monthly CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_skincare_monthly AS
SELECT * FROM dk.vw_skincare_monthly;

CREATE UNIQUE INDEX idx_mvw_skincare_branch_month ON dk.mvw_skincare_monthly (branch, month);
CREATE INDEX idx_mvw_skincare_month ON dk.mvw_skincare_monthly (month);
CREATE INDEX idx_mvw_skincare_branch ON dk.mvw_skincare_monthly (branch);

COMMENT ON MATERIALIZED VIEW dk.mvw_skincare_monthly IS 'Materialized view of skincare monthly performance. Refresh: Daily at 2:00 AM via dk.refresh_product_mvws().';

-- MVW: Package Composition
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_package_composition CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_package_composition AS
SELECT * FROM dk.vw_package_composition;

CREATE UNIQUE INDEX idx_mvw_pkg_comp_branch_month ON dk.mvw_package_composition (branch, month);
CREATE INDEX idx_mvw_pkg_comp_month ON dk.mvw_package_composition (month);

COMMENT ON MATERIALIZED VIEW dk.mvw_package_composition IS 'Materialized view of package composition by category. Refresh: Daily at 2:00 AM.';

-- MVW: Package Conversion Demographics
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_package_conversion_demo CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_package_conversion_demo AS
SELECT * FROM dk.vw_package_conversion_demographics;

CREATE UNIQUE INDEX idx_mvw_pkg_conv_race_age_gender ON dk.mvw_package_conversion_demo (race, age_band, gender);
CREATE INDEX idx_mvw_pkg_conv_race ON dk.mvw_package_conversion_demo (race);
CREATE INDEX idx_mvw_pkg_conv_age ON dk.mvw_package_conversion_demo (age_band);

COMMENT ON MATERIALIZED VIEW dk.mvw_package_conversion_demo IS 'Materialized view of package conversion by demographics. Refresh: Daily at 2:00 AM.';

-- MVW: Payment Mode Distribution
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_payment_mode_dist CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_payment_mode_dist AS
SELECT * FROM dk.vw_payment_mode_distribution;

CREATE UNIQUE INDEX idx_mvw_payment_race_age_gender_mode ON dk.mvw_payment_mode_dist (race, age_band, gender, payment_mode);
CREATE INDEX idx_mvw_payment_mode ON dk.mvw_payment_mode_dist (payment_mode);

COMMENT ON MATERIALIZED VIEW dk.mvw_payment_mode_dist IS 'Materialized view of payment mode distribution. Refresh: Daily at 2:00 AM.';

-- MVW: Affordability Stress
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_affordability_stress CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_affordability_stress AS
SELECT * FROM dk.vw_affordability_stress;

CREATE UNIQUE INDEX idx_mvw_afford_stress_mrn_branch ON dk.mvw_affordability_stress (mrn, branch);
CREATE INDEX idx_mvw_afford_stress_level ON dk.mvw_affordability_stress (stress_level);
CREATE INDEX idx_mvw_afford_branch ON dk.mvw_affordability_stress (branch);

COMMENT ON MATERIALIZED VIEW dk.mvw_affordability_stress IS 'Materialized view of affordability stress analysis. Refresh: Daily at 2:00 AM.';

-- MVW: Product Category Mix
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_product_category_mix CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_product_category_mix AS
SELECT * FROM dk.vw_category_mix;

CREATE UNIQUE INDEX idx_mvw_mix_branch_month ON dk.mvw_product_category_mix (branch, month);
CREATE INDEX idx_mvw_mix_month ON dk.mvw_product_category_mix (month);

COMMENT ON MATERIALIZED VIEW dk.mvw_product_category_mix IS 'Materialized view of product category mix. Refresh: Daily at 2:00 AM.';

-- MVW: Stressed Buyers
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_stressed_buyers CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_stressed_buyers AS
SELECT * FROM dk.vw_stressed_buyers;

CREATE UNIQUE INDEX idx_mvw_stressed_mrn ON dk.mvw_stressed_buyers (mrn);
CREATE INDEX idx_mvw_stressed_flag ON dk.mvw_stressed_buyers (risk_flag);
CREATE INDEX idx_mvw_stressed_branch ON dk.mvw_stressed_buyers (branch);

COMMENT ON MATERIALIZED VIEW dk.mvw_stressed_buyers IS 'Materialized view of high outstanding buyers. Refresh: Daily at 2:00 AM.';

-- ============================================================================
-- SECTION 2: Refresh Function for ST-04 MVWs
-- ============================================================================

CREATE OR REPLACE FUNCTION dk.refresh_product_mvws()
RETURNS TABLE(mvw_name TEXT, status TEXT, duration_ms NUMERIC) AS $$
DECLARE
    start_time TIMESTAMP;
    mvw_record RECORD;
    st04_mvws TEXT[] := ARRAY[
        'mvw_skincare_monthly',
        'mvw_package_composition',
        'mvw_package_conversion_demo',
        'mvw_payment_mode_dist',
        'mvw_affordability_stress',
        'mvw_product_category_mix',
        'mvw_stressed_buyers'
    ];
BEGIN
    FOREACH mvw_name IN ARRAY st04_mvws
    LOOP
        start_time := clock_timestamp();
        
        BEGIN
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY dk.%I', mvw_name);
            
            RETURN QUERY SELECT 
                mvw_name::TEXT,
                'SUCCESS'::TEXT,
                EXTRACT(MILLISECONDS FROM clock_timestamp() - start_time)::NUMERIC;
        EXCEPTION WHEN OTHERS THEN
            BEGIN
                EXECUTE format('REFRESH MATERIALIZED VIEW dk.%I', mvw_name);
                
                RETURN QUERY SELECT 
                    mvw_name::TEXT,
                    'SUCCESS (non-concurrent)'::TEXT,
                    EXTRACT(MILLISECONDS FROM clock_timestamp() - start_time)::NUMERIC;
            EXCEPTION WHEN OTHERS THEN
                RETURN QUERY SELECT 
                    mvw_name::TEXT,
                    ('FAILED: ' || SQLERRM)::TEXT,
                    EXTRACT(MILLISECONDS FROM clock_timestamp() - start_time)::NUMERIC;
            END;
        END;
    END LOOP;
    
    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.refresh_product_mvws() IS 'Refreshes all ST-04 product analytics materialized views. Returns status for each view.';

-- ============================================================================
-- SECTION 3: Grant Permissions
-- ============================================================================

-- Grant select on materialized views to reader role
GRANT SELECT ON dk.mvw_skincare_monthly TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_package_composition TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_package_conversion_demo TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_payment_mode_dist TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_affordability_stress TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_product_category_mix TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_stressed_buyers TO healthcare_bi_reader;

-- Grant select on materialized views to app role
GRANT SELECT ON dk.mvw_skincare_monthly TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_package_composition TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_package_conversion_demo TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_payment_mode_dist TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_affordability_stress TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_product_category_mix TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_stressed_buyers TO healthcare_bi_app;

-- ============================================================================
-- END OF FILE
-- ============================================================================