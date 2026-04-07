-- ============================================================================
-- ST-04: Product & Package Performance Analytics
-- File: 03_payment_behavior_views.sql
-- Description: Payment mode distribution, affordability stress, preference views
-- Schema: dk
-- Dependencies: dk.collection, dk.patient
-- Actual Schema Fields:
--   dk.collection: row_number, date, branch, mrn, amount_collected, patient_outstanding_amount
--   dk.patient: location (PK), mrn, gender, dob, race_name, city_name, state_name
--   Offset columns: offset_package_balance, offset_deposit_loyalty, offset_deposit_on_behalf, offset_deposit_open
-- ============================================================================

-- ============================================================================
-- SECTION 1: Payment Mode Distribution View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_payment_mode_distribution CASCADE;
CREATE VIEW dk.vw_payment_mode_distribution AS
WITH payment_mode_enriched AS (
    SELECT 
        p.race_name AS race,
        CASE 
            WHEN p.dob IS NOT NULL AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 25 THEN '18-24'
            WHEN p.dob IS NOT NULL AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 35 THEN '25-34'
            WHEN p.dob IS NOT NULL AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 45 THEN '35-44'
            WHEN p.dob IS NOT NULL AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 55 THEN '45-54'
            ELSE '55+'
        END AS age_band,
        p.gender,
        
        CASE 
            WHEN c.offset_package_balance > 0 THEN 'PACKAGE_REDEMPTION'
            WHEN c.offset_deposit_loyalty > 0 THEN 'LOYALTY_DEPOSIT'
            WHEN c.offset_deposit_on_behalf > 0 THEN 'ON_BEHALF'
            WHEN c.offset_deposit_open > 0 THEN 'OPEN_DEPOSIT'
            ELSE 'DIRECT_PAYMENT'
        END AS payment_mode,
        
        c.amount_collected,
        c.date
        
    FROM dk.collection c
    JOIN dk.patient p ON p.mrn = c.mrn
    WHERE c.date IS NOT NULL
      AND (c.offset_package_balance > 0 OR c.offset_deposit_loyalty > 0 OR 
           c.offset_deposit_on_behalf > 0 OR c.offset_deposit_open > 0 OR c.amount_collected > 0)
)
SELECT 
    race,
    age_band,
    gender,
    payment_mode,
    
    COUNT(*) AS transaction_count,
    SUM(amount_collected) AS total_amount,
    
    -- Average amount
    CASE 
        WHEN COUNT(*) > 0 THEN
            ROUND((SUM(amount_collected) / COUNT(*))::NUMERIC, 2)
        ELSE 0 
    END AS avg_amount
    
FROM payment_mode_enriched
WHERE race IS NOT NULL
GROUP BY race, age_band, gender, payment_mode
ORDER BY race, age_band, payment_mode;

COMMENT ON VIEW dk.vw_payment_mode_distribution IS 'Payment mode distribution by demographics. Source: dk.collection offset columns, dk.patient.';

-- ============================================================================
-- SECTION 2: Affordability Stress Analysis View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_affordability_stress CASCADE;
CREATE VIEW dk.vw_affordability_stress AS
WITH patient_monthly_spend AS (
    SELECT 
        c.mrn,
        c.branch,
        DATE_TRUNC('month', c.date)::DATE AS month,
        SUM(c.amount_collected) AS monthly_spent
    FROM dk.collection c
    WHERE c.date IS NOT NULL
    GROUP BY c.mrn, c.branch, DATE_TRUNC('month', c.date)
),
patient_summary AS (
    SELECT 
        c.mrn,
        c.branch,
        p.city_name AS city,
        p.state_name AS state,
        
        -- Average monthly spend
        (SELECT AVG(monthly_spent) FROM patient_monthly_spend pms WHERE pms.mrn = c.mrn) AS avg_monthly_spend,
        
        -- Average outstanding balance
        COALESCE(AVG(c.patient_outstanding_amount), 0) AS avg_outstanding,
        
        -- Current outstanding
        COALESCE(MAX(c.patient_outstanding_amount), 0) AS current_outstanding,
        
        -- Total visits
        COUNT(DISTINCT c.row_number) AS total_visits,
        
        -- Last visit date
        MAX(c.date) AS last_visit_date
        
    FROM dk.collection c
    JOIN dk.patient p ON p.mrn = c.mrn
    WHERE c.date IS NOT NULL
    GROUP BY c.mrn, c.branch, p.city_name, p.state_name
)
SELECT DISTINCT ON (mrn, branch)
    mrn,
    branch,
    city,
    state,
    
    avg_monthly_spend,
    avg_outstanding,
    
    -- Stress ratio: outstanding / monthly_spend
    CASE 
        WHEN avg_monthly_spend > 0 THEN
            ROUND((avg_outstanding / avg_monthly_spend)::NUMERIC, 2)
        ELSE 0 
    END AS stress_ratio,
    
    -- Stress level classification
    CASE 
        WHEN avg_monthly_spend > 0 AND avg_outstanding / avg_monthly_spend >= 3 THEN 'CRITICAL'
        WHEN avg_monthly_spend > 0 AND avg_outstanding / avg_monthly_spend >= 2 THEN 'HIGH'
        WHEN avg_monthly_spend > 0 AND avg_outstanding / avg_monthly_spend >= 1 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS stress_level,
    
    total_visits,
    last_visit_date
    
FROM patient_summary
ORDER BY mrn, branch, stress_ratio DESC;

COMMENT ON VIEW dk.vw_affordability_stress IS 'Affordability stress analysis per patient. Source: dk.collection, dk.patient.';

-- ============================================================================
-- SECTION 3: Payment Preference by Stress View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_payment_preference_by_stress CASCADE;
CREATE VIEW dk.vw_payment_preference_by_stress AS
WITH patient_spend_split AS (
    SELECT 
        c.mrn,
        c.branch,
        
        COALESCE(SUM(c.standalone_sales_subtotal), 0) AS standalone_total,
        COALESCE(SUM(c.offset_package_balance), 0) AS package_total,
        
        COALESCE(SUM(c.standalone_sales_subtotal), 0) + COALESCE(SUM(c.offset_package_balance), 0) AS grand_total
        
    FROM dk.collection c
    WHERE c.date IS NOT NULL
    GROUP BY c.mrn, c.branch
),
stress_and_preference AS (
    SELECT 
        ps.mrn,
        ps.branch,
        as_view.stress_level,
        
        ps.standalone_total,
        ps.package_total,
        
        CASE 
            WHEN ps.package_total > ps.standalone_total THEN 'PREFERS_PACKAGE'
            WHEN ps.standalone_total > ps.package_total THEN 'PREFERS_STANDALONE'
            ELSE 'NO_PREFERENCE'
        END AS preference
    FROM patient_spend_split ps
    JOIN dk.vw_affordability_stress as_view ON as_view.mrn = ps.mrn
)
SELECT 
    sap.stress_level,
    
    COUNT(DISTINCT sap.mrn) AS total_patients,
    
    SUM(CASE WHEN preference = 'PREFERS_PACKAGE' THEN 1 ELSE 0 END) AS prefers_package_count,
    SUM(CASE WHEN preference = 'PREFERS_STANDALONE' THEN 1 ELSE 0 END) AS prefers_standalone_count,
    
    -- Percentages
    CASE 
        WHEN COUNT(DISTINCT sap.mrn) > 0 THEN
            ROUND((SUM(CASE WHEN preference = 'PREFERS_PACKAGE' THEN 1 ELSE 0 END) / 
                   COUNT(DISTINCT sap.mrn) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS prefers_package_pct,
    
    CASE 
        WHEN COUNT(DISTINCT sap.mrn) > 0 THEN
            ROUND((SUM(CASE WHEN preference = 'PREFERS_STANDALONE' THEN 1 ELSE 0 END) / 
                   COUNT(DISTINCT sap.mrn) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS prefers_standalone_pct,
    
    -- Average outstanding
    ROUND((AVG(vs.avg_outstanding))::NUMERIC, 2) AS avg_outstanding
    
FROM stress_and_preference sap
JOIN dk.vw_affordability_stress vs ON vs.mrn = sap.mrn
GROUP BY sap.stress_level
ORDER BY sap.stress_level;

COMMENT ON VIEW dk.vw_payment_preference_by_stress IS 'Package vs standalone preference by financial stress level. Source: dk.collection, dk.vw_affordability_stress.';

-- ============================================================================
-- SECTION 4: Stressed Buyers View
-- ============================================================================

DROP VIEW IF EXISTS dk.vw_stressed_buyers CASCADE;
CREATE VIEW dk.vw_stressed_buyers AS
WITH recent_spend AS (
    SELECT 
        c.mrn,
        
        -- Last 30 days spend
        COALESCE(SUM(CASE WHEN c.date >= CURRENT_DATE - INTERVAL '30 days' THEN c.amount_collected ELSE 0 END), 0) AS recent_spend_30d,
        
        -- Last 90 days spend
        COALESCE(SUM(CASE WHEN c.date >= CURRENT_DATE - INTERVAL '90 days' THEN c.amount_collected ELSE 0 END), 0) AS recent_spend_90d,
        
        -- Days since last visit (date subtraction returns integer days directly)
        (CURRENT_DATE - MAX(c.date))::INTEGER AS days_since_visit
        
    FROM dk.collection c
    WHERE c.date IS NOT NULL
    GROUP BY c.mrn
),
stressed_buyers_data AS (
    SELECT DISTINCT ON (as_view.mrn)
        as_view.mrn,
        cr.patient_name,
        p.city_name AS city,
        p.state_name AS state,
        as_view.branch,
        as_view.avg_outstanding AS outstanding_amount,
        as_view.stress_level,
        rs.recent_spend_30d,
        rs.recent_spend_90d,
        rs.days_since_visit,
        
        CASE 
            WHEN as_view.stress_level IN ('CRITICAL', 'HIGH') AND rs.recent_spend_30d > 0 THEN 'HIGH'
            WHEN as_view.stress_level IN ('CRITICAL', 'HIGH') AND rs.recent_spend_90d > 0 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS risk_flag
        
    FROM dk.vw_affordability_stress as_view
    JOIN dk.patient p ON p.mrn = as_view.mrn
    JOIN recent_spend rs ON rs.mrn = as_view.mrn
    LEFT JOIN LATERAL (
        SELECT patient_name 
        FROM dk.collection_report cr2 
        WHERE cr2.mrn = as_view.mrn 
        ORDER BY cr2.csv_date DESC 
        LIMIT 1
    ) cr ON true
    WHERE as_view.stress_level IN ('CRITICAL', 'HIGH')
    ORDER BY as_view.mrn, as_view.avg_outstanding DESC
)
SELECT 
    mrn,
    patient_name,
    city,
    state,
    branch,
    outstanding_amount,
    stress_level,
    recent_spend_30d,
    recent_spend_90d,
    days_since_visit,
    risk_flag
    
FROM stressed_buyers_data
ORDER BY outstanding_amount DESC
LIMIT 1000;

COMMENT ON VIEW dk.vw_stressed_buyers IS 'High outstanding patients who are still buying. Source: dk.vw_affordability_stress, dk.patient, dk.collection_report.';

-- ============================================================================
-- SECTION 5: Grant Permissions
-- ============================================================================

GRANT SELECT ON dk.vw_payment_mode_distribution TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_affordability_stress TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_payment_preference_by_stress TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_stressed_buyers TO healthcare_bi_reader;

GRANT SELECT ON dk.vw_payment_mode_distribution TO healthcare_bi_app;
GRANT SELECT ON dk.vw_affordability_stress TO healthcare_bi_app;
GRANT SELECT ON dk.vw_payment_preference_by_stress TO healthcare_bi_app;
GRANT SELECT ON dk.vw_stressed_buyers TO healthcare_bi_app;

-- ============================================================================
-- END OF FILE
-- ============================================================================