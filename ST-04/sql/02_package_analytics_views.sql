-- ============================================================================
-- ST-04: Product & Package Performance Analytics
-- File: 02_package_analytics_views.sql
-- Description: Package composition, redemption, addon, and demographics views
-- Schema: dk
-- Dependencies: dk.collection, dk.patient
-- Actual Schema Fields:
--   dk.collection: row_number, date, branch, mrn, package_sales_subtotal, offset_package_balance
--   dk.patient: location (PK), mrn, gender, dob, race_name, city_name, state_name
-- ============================================================================

-- ============================================================================
-- SECTION 1: Package Composition by Category View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_package_composition CASCADE;
CREATE VIEW dk.vw_package_composition AS
WITH monthly_packages AS (
    SELECT 
        c.branch,
        DATE_TRUNC('month', c.date)::DATE AS month,
        
        -- Package totals
        COALESCE(SUM(c.package_sales_subtotal), 0) AS total_package_revenue,
        
        -- By category
        COALESCE(SUM(c.package_sales_services), 0) AS pkg_services_amount,
        COALESCE(SUM(c.package_sales_skincare_product_amount), 0) AS pkg_skincare_amount,
        COALESCE(SUM(c.package_sales_medications), 0) AS pkg_medications_amount,
        COALESCE(SUM(c.package_sales_supplements_supplement_rm5_amount), 0) +
        COALESCE(SUM(c.package_sales_supplements_supplement_na_amount), 0) AS pkg_supplements_amount,
        COALESCE(SUM(c.package_sales_other_product_amount), 0) AS pkg_other_amount
        
    FROM dk.collection c
    WHERE c.date IS NOT NULL
      AND c.package_sales_subtotal > 0
    GROUP BY c.branch, DATE_TRUNC('month', c.date)
)
SELECT 
    branch,
    month,
    total_package_revenue,
    
    pkg_services_amount,
    pkg_skincare_amount,
    pkg_medications_amount,
    pkg_supplements_amount,
    pkg_other_amount,
    
    -- Percentages
    CASE 
        WHEN total_package_revenue > 0 THEN
            ROUND((pkg_services_amount / total_package_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS pkg_services_pct,
    
    CASE 
        WHEN total_package_revenue > 0 THEN
            ROUND((pkg_skincare_amount / total_package_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS pkg_skincare_pct,
    
    CASE 
        WHEN total_package_revenue > 0 THEN
            ROUND((pkg_medications_amount / total_package_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS pkg_medications_pct,
    
    CASE 
        WHEN total_package_revenue > 0 THEN
            ROUND((pkg_supplements_amount / total_package_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS pkg_supplements_pct,
    
    CASE 
        WHEN total_package_revenue > 0 THEN
            ROUND((pkg_other_amount / total_package_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS pkg_other_pct
    
FROM monthly_packages
ORDER BY branch, month DESC;

COMMENT ON VIEW dk.vw_package_composition IS 'Package breakdown by category per branch and month. Source: dk.collection package_sales columns.';

-- ============================================================================
-- SECTION 2: Package Redemption Rates View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_package_redemption CASCADE;
CREATE VIEW dk.vw_package_redemption AS
WITH patient_package_purchase AS (
    SELECT 
        c.mrn,
        c.branch,
        MAX(DATE_TRUNC('month', c.date)::DATE) AS first_package_month,
        COALESCE(SUM(c.package_sales_subtotal), 0) AS total_package_purchased,
        COALESCE(SUM(c.offset_package_balance), 0) AS total_package_redeemed,
        COALESCE(MAX(c.offset_package_balance), 0) AS remaining_balance,
        MAX(c.date) AS last_redemption_date
    FROM dk.collection c
    WHERE c.package_sales_subtotal > 0 OR c.offset_package_balance > 0
    GROUP BY c.mrn, c.branch
)
SELECT 
    mrn,
    branch,
    total_package_purchased,
    total_package_redeemed,
    remaining_balance,
    
    -- Redemption rate
    CASE 
        WHEN total_package_purchased > 0 THEN
            ROUND(((total_package_purchased - remaining_balance) / total_package_purchased * 100)::NUMERIC, 2)
        ELSE 0 
    END AS redemption_rate,
    
    -- Status classification
    CASE 
        WHEN total_package_purchased > 0 AND (total_package_purchased - remaining_balance) / total_package_purchased >= 0.95 THEN 'FULL'
        WHEN total_package_purchased > 0 AND (total_package_purchased - remaining_balance) / total_package_purchased >= 0.60 THEN 'HIGH'
        WHEN total_package_purchased > 0 AND (total_package_purchased - remaining_balance) / total_package_purchased >= 0.30 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS redemption_status,
    
    last_redemption_date
    
FROM patient_package_purchase
ORDER BY remaining_balance DESC;

COMMENT ON VIEW dk.vw_package_redemption IS 'Package redemption rates per patient with status classification. Source: dk.collection.';

-- ============================================================================
-- SECTION 3: Package Addon Analysis View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_package_addon CASCADE;
CREATE VIEW dk.vw_package_addon AS
SELECT 
    c.mrn,
    c.date AS visit_date,
    c.branch,
    
    c.offset_package_balance > 0 AS has_package_offset,
    
    COALESCE(c.standalone_sales_subtotal, 0) AS standalone_spend,
    COALESCE(c.offset_package_balance, 0) AS package_spend,
    
    COALESCE(c.standalone_sales_subtotal, 0) + COALESCE(c.offset_package_balance, 0) AS total_spend
    
FROM dk.collection c
WHERE c.date IS NOT NULL
  AND (c.offset_package_balance > 0 OR c.standalone_sales_subtotal > 0)
ORDER BY c.date DESC;

COMMENT ON VIEW dk.vw_package_addon IS 'Standalone spend during package redemption visits. Source: dk.collection.';

-- ============================================================================
-- SECTION 4: Package Conversion Demographics View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_package_conversion_demographics CASCADE;
CREATE VIEW dk.vw_package_conversion_demographics AS
WITH patient_package_status AS (
    SELECT DISTINCT ON (p.location)
        p.location,
        p.race_name AS race,
        CASE 
            WHEN p.dob IS NOT NULL AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 25 THEN '18-24'
            WHEN p.dob IS NOT NULL AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 35 THEN '25-34'
            WHEN p.dob IS NOT NULL AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 45 THEN '35-44'
            WHEN p.dob IS NOT NULL AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 55 THEN '45-54'
            ELSE '55+'
        END AS age_band,
        p.gender,
        MAX(CASE WHEN c.package_sales_subtotal > 0 THEN 1 ELSE 0 END) AS bought_package
    FROM dk.patient p
    LEFT JOIN dk.collection c ON c.mrn = p.mrn
    WHERE p.dob IS NOT NULL
    GROUP BY p.location, p.race_name, p.gender, p.dob
    ORDER BY p.location
)
SELECT 
    race,
    age_band,
    gender,
    
    COUNT(*) AS total_patients,
    SUM(bought_package) AS package_buyers,
    
    -- Conversion rate
    CASE 
        WHEN COUNT(*) > 0 THEN
            ROUND((SUM(bought_package) / COUNT(*) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS conversion_rate
    
FROM patient_package_status
WHERE race IS NOT NULL
GROUP BY race, age_band, gender
ORDER BY conversion_rate DESC;

COMMENT ON VIEW dk.vw_package_conversion_demographics IS 'Package buyer demographics analysis by race, age band, and gender. Source: dk.patient, dk.collection.';

-- ============================================================================
-- SECTION 5: Grant Permissions
-- ============================================================================

GRANT SELECT ON dk.vw_package_composition TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_package_redemption TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_package_addon TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_package_conversion_demographics TO healthcare_bi_reader;

GRANT SELECT ON dk.vw_package_composition TO healthcare_bi_app;
GRANT SELECT ON dk.vw_package_redemption TO healthcare_bi_app;
GRANT SELECT ON dk.vw_package_addon TO healthcare_bi_app;
GRANT SELECT ON dk.vw_package_conversion_demographics TO healthcare_bi_app;

-- ============================================================================
-- END OF FILE
-- ============================================================================