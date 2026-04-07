-- ============================================================
-- ST-01: Data Foundation & Infrastructure
-- 01_core_views.sql
-- Core SQL Views for Healthcare Analytics
-- ============================================================
-- 
-- ACTUAL TABLE SCHEMA (existing):
-- 
-- dk.patient:
--   location (PK), mrn, gender, dob, race_name, address, street, 
--   street2, city_name, state_name, zip, country_name
--
-- dk.collection:
--   row_number, date, entity, branch, sale_order_no, mrn, status,
--   sales_channel, standalone_sales_*, package_sales_*, 
--   amount_collected, patient_outstanding_amount, discount, tax_*
--
-- dk.collection_report:
--   id (PK), csv_date, entity, branch, sale_order_no, mrn, 
--   patient_name, standalone_sales_*_rm, package_sales_*_rm,
--   amount_collected_rm
-- ============================================================

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS dk;

-- ============================================================
-- CORE VIEWS
-- ============================================================

-- ============================================================
-- View: vw_patient_enriched
-- Purpose: Patient data with calculated fields (age, status, recency)
-- ============================================================
CREATE OR REPLACE VIEW dk.vw_patient_enriched AS
WITH patient_transactions AS (
    SELECT 
        c.mrn,
        COUNT(DISTINCT c.row_number) AS total_transactions,
        SUM(COALESCE(c.amount_collected, 0)) AS total_revenue,
        MAX(c.date) AS last_visit_date,
        MIN(c.date) AS first_visit_date
    FROM dk.collection c
    WHERE c.mrn IS NOT NULL
    GROUP BY c.mrn
)
SELECT DISTINCT ON (p.mrn)
    p.location AS patient_location,
    p.mrn AS patient_id,
    p.mrn,
    p.gender,
    p.dob,
    p.race_name,
    p.address,
    p.street,
    p.street2,
    p.city_name AS city,
    p.state_name AS state,
    p.zip AS postcode,
    p.country_name AS country,
    
    -- Calculated fields
    CASE 
        WHEN p.dob IS NOT NULL THEN 
            EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob))::INTEGER 
        ELSE NULL 
    END AS age,
    
    CASE 
        WHEN p.gender = 'M' THEN 'Male'
        WHEN p.gender = 'F' THEN 'Female'
        ELSE 'Unknown'
    END AS gender_display,
    
    -- Transaction data (from CTE)
    COALESCE(pt.total_transactions, 0) AS total_transactions,
    COALESCE(pt.total_revenue, 0) AS total_revenue,
    pt.last_visit_date,
    pt.first_visit_date,
    
    -- Recency calculation
    CASE 
        WHEN pt.last_visit_date IS NOT NULL THEN 
            CURRENT_DATE - pt.last_visit_date 
        ELSE NULL 
    END AS days_since_last_visit,
    
    -- Patient status
    CASE 
        WHEN pt.last_visit_date IS NULL THEN 'NEW'
        WHEN CURRENT_DATE - pt.last_visit_date <= 21 THEN 'ACTIVE'
        WHEN CURRENT_DATE - pt.last_visit_date <= 45 THEN 'AT RISK'
        WHEN CURRENT_DATE - pt.last_visit_date <= 90 THEN 'HIGH RISK'
        ELSE 'LOST'
    END AS patient_status,
    
    -- Value tier
    CASE 
        WHEN COALESCE(pt.total_revenue, 0) >= 5000 THEN 'Platinum'
        WHEN COALESCE(pt.total_revenue, 0) >= 2500 THEN 'Gold'
        WHEN COALESCE(pt.total_revenue, 0) >= 1000 THEN 'Silver'
        WHEN COALESCE(pt.total_revenue, 0) >= 500 THEN 'Bronze'
        ELSE 'Standard'
    END AS value_tier,
    
    -- Recency score (1-5, 5 = most recent)
    CASE 
        WHEN pt.last_visit_date IS NULL THEN 1
        WHEN CURRENT_DATE - pt.last_visit_date <= 7 THEN 5
        WHEN CURRENT_DATE - pt.last_visit_date <= 14 THEN 4
        WHEN CURRENT_DATE - pt.last_visit_date <= 30 THEN 3
        WHEN CURRENT_DATE - pt.last_visit_date <= 60 THEN 2
        ELSE 1
    END AS recency_score,
    
    CURRENT_TIMESTAMP AS updated_at

FROM dk.patient p
LEFT JOIN patient_transactions pt ON p.mrn = pt.mrn
ORDER BY p.mrn, pt.last_visit_date DESC NULLS LAST;

COMMENT ON VIEW dk.vw_patient_enriched IS 'Patient data with calculated age, status, and transaction summary. Uses existing dk.patient and dk.collection tables.';

-- ============================================================
-- View: vw_transaction_flat
-- Purpose: Flattened transaction view with all dimensions
-- ============================================================
CREATE OR REPLACE VIEW dk.vw_transaction_flat AS
SELECT DISTINCT ON (c.row_number)
    c.row_number AS transaction_id,
    c.source_file,
    c.date AS transaction_date,
    c.entity,
    c.branch,
    c.sale_order_no,
    c.receipt_dn_no,
    c.mrn AS patient_id,
    c.status,
    c.sales_channel,
    
    -- Revenue breakdown - standalone
    COALESCE(c.standalone_sales_consultations, 0) AS standalone_consultations,
    COALESCE(c.standalone_sales_services, 0) AS standalone_services,
    COALESCE(c.standalone_sales_medications, 0) AS standalone_medications,
    COALESCE(c.standalone_sales_supplements_supplement_rm5_amount, 0) + 
    COALESCE(c.standalone_sales_supplements_supplement_na_amount, 0) AS standalone_supplements,
    COALESCE(c.standalone_sales_skincare_product_amount, 0) AS standalone_skincare,
    COALESCE(c.standalone_sales_other_product_amount, 0) AS standalone_other,
    COALESCE(c.standalone_sales_subtotal, 0) AS standalone_total,
    
    -- Revenue breakdown - package
    COALESCE(c.package_sales_services, 0) AS package_services,
    COALESCE(c.package_sales_medications, 0) AS package_medications,
    COALESCE(c.package_sales_supplements_supplement_rm5_amount, 0) + 
    COALESCE(c.package_sales_supplements_supplement_na_amount, 0) AS package_supplements,
    COALESCE(c.package_sales_skincare_product_amount, 0) AS package_skincare,
    COALESCE(c.package_sales_other_product_amount, 0) AS package_other,
    COALESCE(c.package_sales_subtotal, 0) AS package_total,
    
    -- Combined revenue
    COALESCE(c.standalone_package_sales, 0) AS total_sales,
    
    -- Other collections
    COALESCE(c.other_collections_deposit_open, 0) AS deposit_open,
    COALESCE(c.other_collections_deposit_loyalty, 0) AS deposit_loyalty,
    COALESCE(c.other_collections_deposit_on_behalf, 0) AS deposit_on_behalf,
    
    -- Financial totals
    COALESCE(c.tax_amount, 0) AS tax_amount,
    COALESCE(c.amount_due, 0) AS amount_due,
    COALESCE(c.amount_collected, 0) AS amount_collected,
    COALESCE(c.patient_outstanding_amount, 0) AS patient_outstanding,
    COALESCE(c.discount, 0) AS discount_amount,
    COALESCE(c.staff_voucher, 0) AS staff_voucher,
    COALESCE(c.credit_note_refund, 0) AS credit_note_refund,
    
    -- Time dimensions
    EXTRACT(YEAR FROM c.date)::INTEGER AS transaction_year,
    EXTRACT(MONTH FROM c.date)::INTEGER AS transaction_month,
    EXTRACT(QUARTER FROM c.date)::INTEGER AS transaction_quarter,
    EXTRACT(WEEK FROM c.date)::INTEGER AS transaction_week,
    EXTRACT(DOW FROM c.date)::INTEGER AS day_of_week,
    TO_CHAR(c.date, 'YYYY-MM') AS year_month,
    TO_CHAR(c.date, 'Day') AS day_name,
    
    -- Patient info (from collection_report if available)
    cr.patient_name,
    
    -- Weekend indicator
    CASE WHEN EXTRACT(DOW FROM c.date) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend

FROM dk.collection c
LEFT JOIN dk.collection_report cr ON c.sale_order_no = cr.sale_order_no AND c.date = cr.csv_date
WHERE c.date IS NOT NULL
ORDER BY c.row_number;

COMMENT ON VIEW dk.vw_transaction_flat IS 'Flattened transaction view with revenue breakdown. Uses existing dk.collection table with row_number as identifier.';

-- ============================================================
-- View: vw_patient_transactions
-- Purpose: Patient-level transaction aggregations
-- ============================================================
CREATE OR REPLACE VIEW dk.vw_patient_transactions AS
SELECT
    c.mrn AS patient_id,
    COUNT(DISTINCT c.row_number) AS total_transactions,
    COUNT(DISTINCT c.date) AS visit_days,
    COUNT(DISTINCT c.branch) AS branches_visited,
    
    -- Revenue totals
    SUM(COALESCE(c.amount_collected, 0)) AS total_revenue,
    SUM(COALESCE(c.discount, 0)) AS total_discount,
    SUM(COALESCE(c.patient_outstanding_amount, 0)) AS total_outstanding,
    
    -- Revenue by category (standalone)
    SUM(COALESCE(c.standalone_sales_consultations, 0)) AS standalone_consultations,
    SUM(COALESCE(c.standalone_sales_services, 0)) AS standalone_services,
    SUM(COALESCE(c.standalone_sales_medications, 0)) AS standalone_medications,
    SUM(COALESCE(c.standalone_sales_subtotal, 0)) AS standalone_total,
    
    -- Revenue by category (package)
    SUM(COALESCE(c.package_sales_services, 0)) AS package_services,
    SUM(COALESCE(c.package_sales_medications, 0)) AS package_medications,
    SUM(COALESCE(c.package_sales_subtotal, 0)) AS package_total,
    
    -- Date range
    MIN(c.date) AS first_transaction_date,
    MAX(c.date) AS last_transaction_date,
    
    -- Calculated metrics
    CASE 
        WHEN COUNT(DISTINCT c.date) > 1 THEN 
            ROUND((MAX(c.date) - MIN(c.date))::NUMERIC / NULLIF(COUNT(DISTINCT c.date) - 1, 0), 1)
        ELSE 0 
    END AS avg_days_between_visits,
    
    CASE 
        WHEN SUM(COALESCE(c.amount_collected, 0)) > 0 AND COUNT(DISTINCT c.row_number) > 0 THEN
            ROUND(SUM(COALESCE(c.amount_collected, 0)) / COUNT(DISTINCT c.row_number), 2)
        ELSE 0 
    END AS avg_transaction_value,
    
    -- Preferred branch
    MODE() WITHIN GROUP (ORDER BY c.branch) AS preferred_branch,
    
    -- Preferred sales channel
    MODE() WITHIN GROUP (ORDER BY c.sales_channel) AS preferred_channel

FROM dk.collection c
WHERE c.mrn IS NOT NULL
GROUP BY c.mrn;

COMMENT ON VIEW dk.vw_patient_transactions IS 'Patient-level transaction aggregations. Grouped by MRN from dk.collection.';

-- ============================================================
-- View: vw_patient_rfm
-- Purpose: RFM segmentation with customer segments
-- ============================================================
CREATE OR REPLACE VIEW dk.vw_patient_rfm AS
WITH rfm_base AS (
    SELECT
        c.mrn AS patient_id,
        CURRENT_DATE - MAX(c.date) AS recency_days,
        COUNT(DISTINCT c.row_number) AS frequency,
        SUM(COALESCE(c.amount_collected, 0)) AS monetary
    FROM dk.collection c
    WHERE c.mrn IS NOT NULL
    GROUP BY c.mrn
    HAVING SUM(COALESCE(c.amount_collected, 0)) > 0
),
rfm_scored AS (
    SELECT
        *,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,  -- Lower recency_days = higher score
        NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,
        NTILE(5) OVER (ORDER BY monetary ASC) AS m_score
    FROM rfm_base
)
SELECT
    patient_id,
    recency_days,
    frequency,
    ROUND(monetary::NUMERIC, 2) AS monetary,
    r_score,
    f_score,
    m_score,
    (r_score * 100 + f_score * 10 + m_score) AS rfm_score,
    
    -- Segment classification
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
        WHEN r_score >= 4 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal Customers'
        WHEN r_score >= 4 AND f_score <= 2 THEN 'New Customers'
        WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Potential Loyalists'
        WHEN r_score = 3 AND f_score <= 3 THEN 'Need Attention'
        WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4 THEN 'At Risk'
        WHEN r_score <= 2 AND f_score <= 2 AND m_score >= 4 THEN 'Cannot Lose Them'
        WHEN r_score <= 2 AND f_score <= 2 AND m_score <= 2 THEN 'Lost'
        WHEN r_score <= 2 THEN 'At Risk'
        ELSE 'Hibernating'
    END AS segment,
    
    -- Priority (1 = highest)
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 1
        WHEN r_score >= 4 AND f_score >= 3 AND m_score >= 3 THEN 2
        WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4 THEN 3
        WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 4
        WHEN r_score = 3 AND f_score <= 3 THEN 5
        WHEN r_score <= 2 THEN 6
        ELSE 7
    END AS priority,
    
    -- High value flag
    (m_score >= 4) AS is_high_value,
    
    -- At risk flag
    (r_score <= 2 AND m_score >= 3) AS is_at_risk,
    
    CURRENT_TIMESTAMP AS calculated_at

FROM rfm_scored;

COMMENT ON VIEW dk.vw_patient_rfm IS 'RFM segmentation using NTILE(5) scoring. Segments: Champions, Loyal, New, Potential, At Risk, Lost.';

-- ============================================================
-- View: vw_patient_lifetime_value
-- Purpose: Patient LTV predictions and health scores
-- ============================================================
CREATE OR REPLACE VIEW dk.vw_patient_lifetime_value AS
SELECT
    pt.patient_id,
    pe.patient_status,
    pe.value_tier,
    pt.total_transactions,
    pt.total_revenue AS historical_revenue,
    pt.first_transaction_date,
    pt.last_transaction_date,
    
    -- Customer lifespan
    CASE 
        WHEN pt.first_transaction_date IS NOT NULL AND pt.last_transaction_date IS NOT NULL THEN
            (pt.last_transaction_date - pt.first_transaction_date)::INTEGER
        ELSE 0 
    END AS customer_lifespan_days,
    
    -- Average transaction value
    CASE 
        WHEN pt.total_transactions > 0 THEN ROUND(pt.total_revenue / pt.total_transactions, 2)
        ELSE 0 
    END AS avg_transaction_value,
    
    -- Purchase frequency (transactions per month)
    CASE 
        WHEN pt.first_transaction_date IS NOT NULL AND pt.last_transaction_date IS NOT NULL AND
             (pt.last_transaction_date - pt.first_transaction_date) > 0 THEN
            ROUND(pt.total_transactions::NUMERIC / NULLIF((pt.last_transaction_date - pt.first_transaction_date), 0) * 30, 2)
        ELSE 0 
    END AS transactions_per_month,
    
    -- Predicted LTV (simple: avg_transaction * 12 months * 2 years)
    CASE 
        WHEN pt.total_transactions > 0 THEN
            ROUND((pt.total_revenue / pt.total_transactions) * 12 * 2, 2)
        ELSE 0 
    END AS predicted_ltv_24m,
    
    -- Health score (0-100)
    CASE 
        WHEN pt.total_transactions = 0 THEN 0
        ELSE
            LEAST(100, GREATEST(0,
                -- Recency component (40 points max)
                CASE 
                    WHEN CURRENT_DATE - pt.last_transaction_date <= 7 THEN 40
                    WHEN CURRENT_DATE - pt.last_transaction_date <= 14 THEN 35
                    WHEN CURRENT_DATE - pt.last_transaction_date <= 30 THEN 30
                    WHEN CURRENT_DATE - pt.last_transaction_date <= 60 THEN 20
                    WHEN CURRENT_DATE - pt.last_transaction_date <= 90 THEN 10
                    ELSE 0
                END +
                -- Frequency component (30 points max)
                LEAST(30, pt.total_transactions * 3) +
                -- Monetary component (30 points max)
                CASE 
                    WHEN pt.total_revenue >= 5000 THEN 30
                    WHEN pt.total_revenue >= 2500 THEN 25
                    WHEN pt.total_revenue >= 1000 THEN 20
                    WHEN pt.total_revenue >= 500 THEN 15
                    WHEN pt.total_revenue >= 100 THEN 10
                    ELSE 5
                END
            ))
    END AS health_score,
    
    -- Risk level
    CASE 
        WHEN CURRENT_DATE - pt.last_transaction_date <= 30 THEN 'Low'
        WHEN CURRENT_DATE - pt.last_transaction_date <= 60 THEN 'Medium'
        WHEN CURRENT_DATE - pt.last_transaction_date <= 90 THEN 'High'
        ELSE 'Critical'
    END AS churn_risk,
    
    CURRENT_TIMESTAMP AS calculated_at

FROM dk.vw_patient_transactions pt
LEFT JOIN dk.vw_patient_enriched pe ON pt.patient_id = pe.mrn;

COMMENT ON VIEW dk.vw_patient_lifetime_value IS 'Patient LTV predictions with health scores and churn risk.';

-- ============================================================
-- View: vw_ml_patient_features
-- Purpose: Feature engineering for ML models
-- ============================================================
CREATE OR REPLACE VIEW dk.vw_ml_patient_features AS
SELECT
    pt.patient_id,
    
    -- Demographic features
    pe.gender,
    pe.age,
    pe.race_name,
    pe.city AS city_name,
    pe.state AS state_name,
    
    -- Behavioral features
    pt.total_transactions,
    pt.visit_days,
    pt.branches_visited,
    pt.total_revenue,
    pt.avg_transaction_value,
    pt.avg_days_between_visits,
    
    -- Recency features
    CURRENT_DATE - pt.last_transaction_date AS days_since_last_visit,
    CURRENT_DATE - pt.first_transaction_date AS days_since_first_visit,
    
    -- RFM features
    pr.r_score,
    pr.f_score,
    pr.m_score,
    pr.segment AS rfm_segment,
    
    -- Value features
    pe.value_tier,
    pe.patient_status,
    plv.health_score,
    plv.churn_risk,
    plv.predicted_ltv_24m,
    
    -- Category preferences
    CASE WHEN pt.standalone_total > 0 THEN pt.standalone_total / NULLIF(pt.total_revenue, 0) ELSE 0 END AS standalone_ratio,
    CASE WHEN pt.package_total > 0 THEN pt.package_total / NULLIF(pt.total_revenue, 0) ELSE 0 END AS package_ratio,
    CASE WHEN pt.standalone_services > 0 THEN pt.standalone_services / NULLIF(pt.total_revenue, 0) ELSE 0 END AS services_ratio,
    CASE WHEN pt.standalone_medications > 0 THEN pt.standalone_medications / NULLIF(pt.total_revenue, 0) ELSE 0 END AS medications_ratio,
    
    -- Preferred dimensions
    pt.preferred_branch,
    pt.preferred_channel,
    
    -- Time features
    EXTRACT(MONTH FROM pt.first_transaction_date)::INTEGER AS first_visit_month,
    EXTRACT(DOW FROM pt.last_transaction_date)::INTEGER AS last_visit_day_of_week,
    
    CURRENT_TIMESTAMP AS feature_timestamp

FROM dk.vw_patient_transactions pt
LEFT JOIN dk.vw_patient_enriched pe ON pt.patient_id = pe.mrn
LEFT JOIN dk.vw_patient_rfm pr ON pt.patient_id = pr.patient_id
LEFT JOIN dk.vw_patient_lifetime_value plv ON pt.patient_id = plv.patient_id;

COMMENT ON VIEW dk.vw_ml_patient_features IS 'Feature engineering view for ML models. Includes demographic, behavioral, RFM, and category preference features.';

-- ============================================================
-- View: vw_calendar_effects
-- Purpose: Calendar/seasonality analysis
-- ============================================================
CREATE OR REPLACE VIEW dk.vw_calendar_effects AS
SELECT
    c.date,
    EXTRACT(YEAR FROM c.date)::INTEGER AS year,
    EXTRACT(MONTH FROM c.date)::INTEGER AS month,
    EXTRACT(QUARTER FROM c.date)::INTEGER AS quarter,
    EXTRACT(WEEK FROM c.date)::INTEGER AS week,
    EXTRACT(DOW FROM c.date)::INTEGER AS day_of_week,
    TO_CHAR(c.date, 'Day') AS day_name,
    TO_CHAR(c.date, 'Month') AS month_name,
    
    -- Season classification (Malaysia)
    CASE 
        WHEN EXTRACT(MONTH FROM c.date) IN (3, 4, 5) THEN 'Dry Season'
        WHEN EXTRACT(MONTH FROM c.date) IN (6, 7, 8) THEN 'Southwest Monsoon'
        WHEN EXTRACT(MONTH FROM c.date) IN (9, 10, 11) THEN 'Inter-monsoon'
        ELSE 'Northeast Monsoon'
    END AS season,
    
    -- Is weekend
    CASE WHEN EXTRACT(DOW FROM c.date) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend,
    
    -- Is month start/end
    CASE WHEN EXTRACT(DAY FROM c.date) <= 5 THEN TRUE ELSE FALSE END AS is_month_start,
    CASE WHEN EXTRACT(DAY FROM c.date) >= 25 THEN TRUE ELSE FALSE END AS is_month_end,
    
    -- Aggregate metrics
    COUNT(DISTINCT c.row_number) AS total_transactions,
    COUNT(DISTINCT c.mrn) AS unique_patients,
    COUNT(DISTINCT c.branch) AS active_branches,
    SUM(COALESCE(c.amount_collected, 0)) AS total_revenue,
    SUM(COALESCE(c.discount, 0)) AS total_discount,
    AVG(COALESCE(c.amount_collected, 0)) AS avg_transaction_value

FROM dk.collection c
WHERE c.date IS NOT NULL
GROUP BY 
    c.date,
    EXTRACT(YEAR FROM c.date),
    EXTRACT(MONTH FROM c.date),
    EXTRACT(QUARTER FROM c.date),
    EXTRACT(WEEK FROM c.date),
    EXTRACT(DOW FROM c.date),
    EXTRACT(DAY FROM c.date)
ORDER BY c.date;

COMMENT ON VIEW dk.vw_calendar_effects IS 'Calendar and seasonality analysis with daily aggregations.';

-- ============================================================
-- View: vw_d3_followup_tracker
-- Purpose: D+3 follow-up list for campaigns
-- ============================================================
CREATE OR REPLACE VIEW dk.vw_d3_followup_tracker AS
WITH patient_last_visit AS (
    SELECT DISTINCT ON (c.mrn)
        c.mrn AS patient_id,
        c.row_number AS last_transaction_id,
        c.date AS last_visit_date,
        c.branch,
        c.amount_collected AS last_amount,
        c.sales_channel,
        CURRENT_DATE - c.date AS days_since_visit
    FROM dk.collection c
    WHERE c.mrn IS NOT NULL
    ORDER BY c.mrn, c.date DESC
)
SELECT
    plv.patient_id,
    plv.last_transaction_id,
    plv.last_visit_date,
    plv.days_since_visit,
    plv.branch,
    plv.last_amount,
    plv.sales_channel,
    
    -- Patient info
    pe.gender,
    pe.age,
    pe.city,
    pe.state,
    pe.value_tier,
    pe.patient_status,
    
    -- Transaction history
    pt.total_transactions,
    pt.total_revenue,
    
    -- Follow-up status
    CASE 
        WHEN plv.days_since_visit = 3 THEN 'READY'
        WHEN plv.days_since_visit > 3 AND plv.days_since_visit <= 7 THEN 'OVERDUE'
        WHEN plv.days_since_visit < 3 THEN 'PENDING'
        ELSE 'EXPIRED'
    END AS followup_status,
    
    -- Priority (1 = highest)
    CASE 
        WHEN pe.value_tier = 'Platinum' AND plv.days_since_visit = 3 THEN 1
        WHEN pe.value_tier = 'Gold' AND plv.days_since_visit = 3 THEN 2
        WHEN pe.value_tier IN ('Silver', 'Bronze') AND plv.days_since_visit = 3 THEN 3
        WHEN plv.days_since_visit BETWEEN 4 AND 7 THEN 4
        ELSE 5
    END AS priority_rank,
    
    -- Recommended action
    CASE 
        WHEN pe.value_tier = 'Platinum' THEN 'VIP Follow-up Call'
        WHEN pe.value_tier = 'Gold' THEN 'Loyal Customer Check-in'
        WHEN pt.total_transactions = 1 THEN 'New Patient Welcome'
        ELSE 'Standard Follow-up'
    END AS recommended_action,
    
    CURRENT_TIMESTAMP AS generated_at

FROM patient_last_visit plv
LEFT JOIN dk.vw_patient_enriched pe ON plv.patient_id = pe.mrn
LEFT JOIN dk.vw_patient_transactions pt ON plv.patient_id = pt.patient_id
WHERE plv.days_since_visit BETWEEN 3 AND 30
ORDER BY priority_rank, pt.total_revenue DESC;

COMMENT ON VIEW dk.vw_d3_followup_tracker IS 'D+3 follow-up tracker for patient callbacks. Filters patients 3-30 days since last visit.';

-- ============================================================
-- Grant Permissions
-- ============================================================

-- Create roles if they don't exist (ignore error if exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'healthcare_bi_reader') THEN
        CREATE ROLE healthcare_bi_reader;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'healthcare_bi_app') THEN
        CREATE ROLE healthcare_bi_app;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'healthcare_bi_admin') THEN
        CREATE ROLE healthcare_bi_admin;
    END IF;
END $$;

-- Grant SELECT on all views to reader role
GRANT SELECT ON dk.vw_patient_enriched TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_transaction_flat TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_transactions TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_rfm TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_lifetime_value TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_ml_patient_features TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_calendar_effects TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_d3_followup_tracker TO healthcare_bi_reader;

-- Grant SELECT on all views to app role
GRANT SELECT ON dk.vw_patient_enriched TO healthcare_bi_app;
GRANT SELECT ON dk.vw_transaction_flat TO healthcare_bi_app;
GRANT SELECT ON dk.vw_patient_transactions TO healthcare_bi_app;
GRANT SELECT ON dk.vw_patient_rfm TO healthcare_bi_app;
GRANT SELECT ON dk.vw_patient_lifetime_value TO healthcare_bi_app;
GRANT SELECT ON dk.vw_ml_patient_features TO healthcare_bi_app;
GRANT SELECT ON dk.vw_calendar_effects TO healthcare_bi_app;
GRANT SELECT ON dk.vw_d3_followup_tracker TO healthcare_bi_app;

-- Grant ALL to admin role
GRANT ALL ON ALL TABLES IN SCHEMA dk TO healthcare_bi_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA dk TO healthcare_bi_admin;

-- ============================================================
-- Summary
-- ============================================================
-- Views created:
-- 1. vw_patient_enriched - Patient data with calculated fields
-- 2. vw_transaction_flat - Flattened transaction view
-- 3. vw_patient_transactions - Patient-level aggregations
-- 4. vw_patient_rfm - RFM segmentation
-- 5. vw_patient_lifetime_value - LTV predictions
-- 6. vw_ml_patient_features - ML feature engineering
-- 7. vw_calendar_effects - Calendar/seasonality
-- 8. vw_d3_followup_tracker - D+3 follow-up list
-- ============================================================