-- ============================================================================
-- ST-04: Product & Package Performance Analytics
-- File: 01_product_performance_views.sql
-- Description: Product performance views for skincare, supplements, medications, services
-- Schema: dk
-- Source: dk.collection (pre-split columns)
-- Dependencies: dk.collection
-- Actual Schema Fields:
--   dk.collection: row_number (PK), date, branch, mrn, sales_channel
--   Pre-split columns: standalone_sales_*, package_sales_* (amount/unit/discount)
-- ============================================================================

-- ============================================================================
-- SECTION 1: Skincare Monthly Performance View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_skincare_monthly CASCADE;
CREATE VIEW dk.vw_skincare_monthly AS
SELECT 
    c.branch,
    c.sales_channel,
    DATE_TRUNC('month', c.date)::DATE AS month,
    
    -- Revenue metrics
    COALESCE(SUM(c.standalone_sales_skincare_product_amount), 0) AS standalone_skincare,
    COALESCE(SUM(c.package_sales_skincare_product_amount), 0) AS package_skincare,
    COALESCE(SUM(c.standalone_sales_skincare_product_amount), 0) + 
    COALESCE(SUM(c.package_sales_skincare_product_amount), 0) AS total_skincare,
    
    -- Unit metrics
    COALESCE(SUM(c.standalone_sales_skincare_product_unit), 0) +
    COALESCE(SUM(c.package_sales_skincare_product_unit), 0) AS skincare_units,
    
    -- Price and discount calculations
    CASE 
        WHEN (COALESCE(SUM(c.standalone_sales_skincare_product_unit), 0) +
              COALESCE(SUM(c.package_sales_skincare_product_unit), 0)) > 0 THEN
            ROUND((((COALESCE(SUM(c.standalone_sales_skincare_product_amount), 0) + 
                    COALESCE(SUM(c.package_sales_skincare_product_amount), 0)) / 
                   (COALESCE(SUM(c.standalone_sales_skincare_product_unit), 0) +
                    COALESCE(SUM(c.package_sales_skincare_product_unit), 0))))::NUMERIC, 2)
        ELSE 0 
    END AS avg_unit_price,
    
    -- Discount rate
    CASE 
        WHEN (COALESCE(SUM(c.standalone_sales_skincare_product_amount), 0) + 
              COALESCE(SUM(c.package_sales_skincare_product_amount), 0)) > 0 THEN
            ROUND((((COALESCE(SUM(c.standalone_sales_skincare_product_discount), 0) + 
                    COALESCE(SUM(c.package_sales_skincare_product_discount), 0)) / 
                   (COALESCE(SUM(c.standalone_sales_skincare_product_amount), 0) + 
                    COALESCE(SUM(c.package_sales_skincare_product_amount), 0))) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS discount_rate,
    
    -- Transaction count
    COUNT(DISTINCT c.row_number) AS transaction_count
    
FROM dk.collection c
WHERE c.date IS NOT NULL
  AND (c.standalone_sales_skincare_product_amount > 0 
       OR c.package_sales_skincare_product_amount > 0
       OR c.standalone_sales_skincare_product_unit > 0
       OR c.package_sales_skincare_product_unit > 0)
GROUP BY c.branch, c.sales_channel, DATE_TRUNC('month', c.date)
ORDER BY c.branch, month DESC;

COMMENT ON VIEW dk.vw_skincare_monthly IS 'Monthly skincare performance by branch and sales channel. Source: dk.collection pre-split columns.';

-- ============================================================================
-- SECTION 2: Supplements Monthly Performance View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_supplements_monthly CASCADE;
CREATE VIEW dk.vw_supplements_monthly AS
SELECT 
    c.branch,
    DATE_TRUNC('month', c.date)::DATE AS month,
    
    -- RM5 supplements
    COALESCE(SUM(c.standalone_sales_supplements_supplement_rm5_amount), 0) AS supplements_rm5_standalone,
    COALESCE(SUM(c.package_sales_supplements_supplement_rm5_amount), 0) AS supplements_rm5_package,
    
    -- NA supplements
    COALESCE(SUM(c.standalone_sales_supplements_supplement_na_amount), 0) AS supplements_na_standalone,
    COALESCE(SUM(c.package_sales_supplements_supplement_na_amount), 0) AS supplements_na_package,
    
    -- Total
    COALESCE(SUM(c.standalone_sales_supplements_supplement_rm5_amount), 0) + 
    COALESCE(SUM(c.package_sales_supplements_supplement_rm5_amount), 0) +
    COALESCE(SUM(c.standalone_sales_supplements_supplement_na_amount), 0) + 
    COALESCE(SUM(c.package_sales_supplements_supplement_na_amount), 0) AS total_supplements,
    
    -- Units (RM5 only - NA supplements have no unit columns)
    COALESCE(SUM(c.standalone_sales_supplements_supplement_rm5_unit), 0) +
    COALESCE(SUM(c.package_sales_supplements_supplement_rm5_unit), 0) AS supplements_units
    
FROM dk.collection c
WHERE c.date IS NOT NULL
GROUP BY c.branch, DATE_TRUNC('month', c.date)
ORDER BY c.branch, month DESC;

COMMENT ON VIEW dk.vw_supplements_monthly IS 'Monthly supplements performance with RM5 vs NA breakdown. Source: dk.collection.';

-- ============================================================================
-- SECTION 3: Medications Monthly Performance View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_medications_monthly CASCADE;
CREATE VIEW dk.vw_medications_monthly AS
SELECT 
    c.branch,
    DATE_TRUNC('month', c.date)::DATE AS month,
    
    COALESCE(SUM(c.standalone_sales_medications), 0) AS standalone_medications,
    COALESCE(SUM(c.package_sales_medications), 0) AS package_medications,
    
    COALESCE(SUM(c.standalone_sales_medications), 0) + 
    COALESCE(SUM(c.package_sales_medications), 0) AS total_medications,
    
    -- Percentages
    CASE 
        WHEN (COALESCE(SUM(c.standalone_sales_medications), 0) + 
              COALESCE(SUM(c.package_sales_medications), 0)) > 0 THEN
            ROUND((COALESCE(SUM(c.standalone_sales_medications), 0) / 
                   (COALESCE(SUM(c.standalone_sales_medications), 0) + 
                    COALESCE(SUM(c.package_sales_medications), 0)) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS standalone_pct,
    
    CASE 
        WHEN (COALESCE(SUM(c.standalone_sales_medications), 0) + 
              COALESCE(SUM(c.package_sales_medications), 0)) > 0 THEN
            ROUND((COALESCE(SUM(c.package_sales_medications), 0) / 
                   (COALESCE(SUM(c.standalone_sales_medications), 0) + 
                    COALESCE(SUM(c.package_sales_medications), 0)) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS package_pct
    
FROM dk.collection c
WHERE c.date IS NOT NULL
GROUP BY c.branch, DATE_TRUNC('month', c.date)
ORDER BY c.branch, month DESC;

COMMENT ON VIEW dk.vw_medications_monthly IS 'Monthly medications standalone vs package split. Source: dk.collection.';

-- ============================================================================
-- SECTION 4: Services Monthly Performance View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_services_monthly CASCADE;
CREATE VIEW dk.vw_services_monthly AS
WITH monthly_services AS (
    SELECT 
        c.branch,
        DATE_TRUNC('month', c.date)::DATE AS month,
        COALESCE(SUM(c.standalone_sales_consultations), 0) AS consultations_amount,
        COALESCE(SUM(c.standalone_sales_services), 0) AS services_standalone_amount,
        COALESCE(SUM(c.package_sales_services), 0) AS services_package_amount
    FROM dk.collection c
    WHERE c.date IS NOT NULL
      AND (c.standalone_sales_consultations IS NOT NULL 
           OR c.standalone_sales_services IS NOT NULL
           OR c.package_sales_services IS NOT NULL)
    GROUP BY c.branch, DATE_TRUNC('month', c.date)
)
SELECT 
    branch,
    month,
    
    SUM(consultations_amount) AS consultations,
    SUM(services_standalone_amount) + SUM(services_package_amount) AS services,
    SUM(consultations_amount) + SUM(services_standalone_amount) + SUM(services_package_amount) AS total_services
    
FROM monthly_services
GROUP BY branch, month
ORDER BY branch, month DESC;

COMMENT ON VIEW dk.vw_services_monthly IS 'Monthly services and consultations by branch. Source: dk.collection.';

-- ============================================================================
-- SECTION 5: Category Revenue Mix View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_category_mix CASCADE;
CREATE VIEW dk.vw_category_mix AS
WITH monthly_branch_revenue AS (
    SELECT 
        c.branch,
        DATE_TRUNC('month', c.date)::DATE AS month,
        
        -- Category revenues
        COALESCE(SUM(c.standalone_sales_skincare_product_amount), 0) + 
        COALESCE(SUM(c.package_sales_skincare_product_amount), 0) AS skincare_amount,
        
        COALESCE(SUM(c.standalone_sales_supplements_supplement_rm5_amount), 0) + 
        COALESCE(SUM(c.package_sales_supplements_supplement_rm5_amount), 0) +
        COALESCE(SUM(c.standalone_sales_supplements_supplement_na_amount), 0) + 
        COALESCE(SUM(c.package_sales_supplements_supplement_na_amount), 0) AS supplements_amount,
        
        COALESCE(SUM(c.standalone_sales_medications), 0) + 
        COALESCE(SUM(c.package_sales_medications), 0) AS medications_amount,
        
        COALESCE(SUM(c.standalone_sales_services), 0) + 
        COALESCE(SUM(c.package_sales_services), 0) AS services_amount,
        
        COALESCE(SUM(c.standalone_sales_consultations), 0) AS consultations_amount,
        
        COALESCE(SUM(c.standalone_sales_other_product_amount), 0) +
        COALESCE(SUM(c.standalone_sales_others_commissionable), 0) +
        COALESCE(SUM(c.standalone_sales_others_non_commissionable), 0) +
        COALESCE(SUM(c.package_sales_other_product_amount), 0) AS other_amount,
        
        -- Total revenue
        COALESCE(SUM(c.standalone_sales_subtotal), 0) + 
        COALESCE(SUM(c.package_sales_subtotal), 0) AS total_revenue
        
    FROM dk.collection c
    WHERE c.date IS NOT NULL
    GROUP BY c.branch, DATE_TRUNC('month', c.date)
)
SELECT 
    branch,
    month,
    total_revenue,
    
    -- Individual category amounts
    skincare_amount,
    supplements_amount,
    medications_amount,
    services_amount,
    consultations_amount,
    other_amount,
    
    -- Category percentages
    CASE 
        WHEN total_revenue > 0 THEN
            ROUND((skincare_amount / total_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS skincare_pct,
    
    CASE 
        WHEN total_revenue > 0 THEN
            ROUND((supplements_amount / total_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS supplements_pct,
    
    CASE 
        WHEN total_revenue > 0 THEN
            ROUND((medications_amount / total_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS medications_pct,
    
    CASE 
        WHEN total_revenue > 0 THEN
            ROUND((services_amount / total_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS services_pct,
    
    CASE 
        WHEN total_revenue > 0 THEN
            ROUND((consultations_amount / total_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS consultations_pct,
    
    CASE 
        WHEN total_revenue > 0 THEN
            ROUND((other_amount / total_revenue * 100)::NUMERIC, 2)
        ELSE 0 
    END AS other_pct
    
FROM monthly_branch_revenue
ORDER BY branch, month DESC;

COMMENT ON VIEW dk.vw_category_mix IS 'Category revenue share per branch and month. Source: dk.collection pre-split columns.';

-- ============================================================================
-- SECTION 6: Grant Permissions
-- ============================================================================

GRANT SELECT ON dk.vw_skincare_monthly TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_supplements_monthly TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_medications_monthly TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_services_monthly TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_category_mix TO healthcare_bi_reader;

GRANT SELECT ON dk.vw_skincare_monthly TO healthcare_bi_app;
GRANT SELECT ON dk.vw_supplements_monthly TO healthcare_bi_app;
GRANT SELECT ON dk.vw_medications_monthly TO healthcare_bi_app;
GRANT SELECT ON dk.vw_services_monthly TO healthcare_bi_app;
GRANT SELECT ON dk.vw_category_mix TO healthcare_bi_app;

-- ============================================================================
-- END OF FILE
-- ============================================================================