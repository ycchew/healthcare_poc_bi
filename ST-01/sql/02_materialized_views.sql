-- ============================================================
-- ST-01: Data Foundation & Infrastructure
-- 02_materialized_views.sql
-- Materialized Views for Power BI Performance
-- ============================================================

-- Enable required extensions (PostGIS for geospatial, skip pg_cron on Windows)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- MATERIALIZED VIEW REFRESH FUNCTION
-- ============================================================

-- Drop existing function if signature changed
DROP FUNCTION IF EXISTS dk.refresh_all_mvws();

CREATE OR REPLACE FUNCTION dk.refresh_all_mvws()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_patient_enriched;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_transaction_flat;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_patient_transactions;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_patient_rfm;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_patient_ltv;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_calendar_effects;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_branch_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_product_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_d3_followup_list;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error refreshing materialized views: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- MATERIALIZED VIEW 1: Patient Enriched
-- Uses actual dk.patient schema: location (PK), mrn, gender, dob, 
-- race_name, address, street, street2, city_name, state_name, zip, country_name
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_enriched CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_patient_enriched AS
SELECT DISTINCT ON (p.mrn)
    p.location,
    p.mrn,
    p.gender,
    p.dob,
    p.race_name,
    p.address,
    p.street,
    p.street2,
    p.city_name,
    p.state_name,
    p.zip,
    p.country_name,
    EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob))::INTEGER AS age,
    CASE 
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 18 THEN 'Under 18'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 25 THEN '18-24'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 35 THEN '25-34'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 45 THEN '35-44'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 55 THEN '45-54'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob)) < 65 THEN '55-64'
        ELSE '65+'
    END AS age_group,
    -- Calculate visit metrics from collection
    c_stats.first_visit_date,
    c_stats.last_visit_date,
    c_stats.total_visits,
    c_stats.total_revenue,
    CASE 
        WHEN c_stats.last_visit_date IS NOT NULL 
        THEN (CURRENT_DATE - c_stats.last_visit_date)::INTEGER 
        ELSE NULL 
    END AS days_since_last_visit,
    CASE 
        WHEN c_stats.last_visit_date IS NULL THEN 'New'
        WHEN (CURRENT_DATE - c_stats.last_visit_date) <= 30 THEN 'Active'
        WHEN (CURRENT_DATE - c_stats.last_visit_date) <= 90 THEN 'At Risk'
        ELSE 'Churned'
    END AS patient_status,
    CASE 
        WHEN c_stats.last_visit_date IS NULL THEN 1
        WHEN (CURRENT_DATE - c_stats.last_visit_date) <= 30 THEN 5
        WHEN (CURRENT_DATE - c_stats.last_visit_date) <= 60 THEN 4
        WHEN (CURRENT_DATE - c_stats.last_visit_date) <= 90 THEN 3
        WHEN (CURRENT_DATE - c_stats.last_visit_date) <= 180 THEN 2
        ELSE 1
    END AS recency_score
FROM dk.patient p
LEFT JOIN (
    SELECT 
        mrn,
        MIN(date) AS first_visit_date,
        MAX(date) AS last_visit_date,
        COUNT(DISTINCT date) AS total_visits,
        COALESCE(SUM(amount_collected), 0) AS total_revenue
    FROM dk.collection
    WHERE mrn IS NOT NULL
    GROUP BY mrn
) c_stats ON p.mrn = c_stats.mrn
WHERE p.mrn IS NOT NULL
ORDER BY p.mrn;

CREATE UNIQUE INDEX idx_mvw_patient_enriched_mrn ON dk.mvw_patient_enriched(mrn);
CREATE INDEX idx_mvw_patient_enriched_status ON dk.mvw_patient_enriched(patient_status);
CREATE INDEX idx_mvw_patient_enriched_age_group ON dk.mvw_patient_enriched(age_group);
CREATE INDEX idx_mvw_patient_enriched_city ON dk.mvw_patient_enriched(city_name);

-- ============================================================
-- MATERIALIZED VIEW 2: Transaction Flat
-- Uses actual dk.collection schema: row_number, date, branch, mrn,
-- amount_collected, standalone_sales_*, package_sales_*, etc.
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_transaction_flat CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_transaction_flat AS
SELECT DISTINCT ON (c.row_number)
    c.row_number AS transaction_id,
    c.source_file,
    c.date AS transaction_date,
    c.entity,
    c.branch,
    c.sale_order_no,
    c.receipt_dn_no,
    c.mrn,
    c.status,
    c.sales_channel,
    -- Patient info from join
    p.gender AS patient_gender,
    p.dob AS patient_dob,
    p.city_name AS patient_city,
    p.state_name AS patient_state,
    EXTRACT(YEAR FROM AGE(c.date, p.dob))::INTEGER AS patient_age_at_transaction,
    -- Time dimensions
    EXTRACT(YEAR FROM c.date)::INTEGER AS transaction_year,
    EXTRACT(MONTH FROM c.date)::INTEGER AS transaction_month,
    EXTRACT(QUARTER FROM c.date)::INTEGER AS transaction_quarter,
    TO_CHAR(c.date, 'YYYY-MM') AS transaction_year_month,
    TO_CHAR(c.date, 'Day') AS transaction_day_name,
    CASE 
        WHEN EXTRACT(DOW FROM c.date) IN (0, 6) THEN TRUE
        ELSE FALSE
    END AS is_weekend,
    -- Standalone sales
    COALESCE(c.standalone_sales_consultations, 0) AS standalone_consultations,
    COALESCE(c.standalone_sales_services, 0) AS standalone_services,
    COALESCE(c.standalone_sales_medications, 0) AS standalone_medications,
    COALESCE(c.standalone_sales_supplements_supplement_rm5_amount, 0) + 
    COALESCE(c.standalone_sales_supplements_supplement_na_amount, 0) AS standalone_supplements,
    COALESCE(c.standalone_sales_skincare_product_amount, 0) AS standalone_skincare,
    COALESCE(c.standalone_sales_other_product_amount, 0) AS standalone_other,
    COALESCE(c.standalone_sales_subtotal, 0) AS standalone_subtotal,
    -- Package sales
    COALESCE(c.package_sales_services, 0) AS package_services,
    COALESCE(c.package_sales_medications, 0) AS package_medications,
    COALESCE(c.package_sales_supplements_supplement_rm5_amount, 0) + 
    COALESCE(c.package_sales_supplements_supplement_na_amount, 0) AS package_supplements,
    COALESCE(c.package_sales_skincare_product_amount, 0) AS package_skincare,
    COALESCE(c.package_sales_other_product_amount, 0) AS package_other,
    COALESCE(c.package_sales_subtotal, 0) AS package_subtotal,
    -- Other collections
    COALESCE(c.other_collections_deposit_open, 0) AS deposit_open,
    COALESCE(c.other_collections_deposit_loyalty, 0) AS deposit_loyalty,
    COALESCE(c.other_collections_deposit_on_behalf, 0) AS deposit_on_behalf,
    -- Financial summary
    COALESCE(c.tax_amount, 0) AS tax_amount,
    COALESCE(c.rounding_total, 0) AS rounding_total,
    COALESCE(c.amount_due, 0) AS amount_due,
    COALESCE(c.amount_collected, 0) AS amount_collected,
    COALESCE(c.patient_outstanding_amount, 0) AS patient_outstanding,
    COALESCE(c.discount, 0) AS discount_amount,
    -- Calculate totals
    COALESCE(c.standalone_sales_subtotal, 0) + COALESCE(c.package_sales_subtotal, 0) AS total_sales,
    -- Offsets
    COALESCE(c.offset_deposit_open, 0) AS offset_deposit_open,
    COALESCE(c.offset_deposit_loyalty, 0) AS offset_deposit_loyalty,
    COALESCE(c.offset_package_balance, 0) AS offset_package_balance
FROM dk.collection c
LEFT JOIN dk.patient p ON c.mrn = p.mrn
WHERE c.row_number IS NOT NULL
ORDER BY c.row_number;

CREATE UNIQUE INDEX idx_mvw_transaction_flat_id ON dk.mvw_transaction_flat(transaction_id);
CREATE INDEX idx_mvw_transaction_flat_date ON dk.mvw_transaction_flat(transaction_date);
CREATE INDEX idx_mvw_transaction_flat_mrn ON dk.mvw_transaction_flat(mrn);
CREATE INDEX idx_mvw_transaction_flat_branch ON dk.mvw_transaction_flat(branch);
CREATE INDEX idx_mvw_transaction_flat_ym ON dk.mvw_transaction_flat(transaction_year_month);

-- ============================================================
-- MATERIALIZED VIEW 3: Patient Transactions (RFM Base)
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_transactions CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_patient_transactions AS
SELECT DISTINCT ON (p.mrn)
    p.mrn,
    p.gender,
    p.dob,
    EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.dob))::INTEGER AS age,
    p.race_name,
    p.city_name,
    p.state_name,
    p.zip,
    -- Transaction aggregations
    COALESCE(c_stats.total_orders, 0) AS total_orders,
    COALESCE(c_stats.total_line_items, 0) AS total_line_items,
    COALESCE(c_stats.unique_visit_days, 0) AS unique_visit_days,
    c_stats.first_transaction_date,
    c_stats.last_transaction_date,
    -- Revenue aggregations
    COALESCE(c_stats.total_revenue, 0) AS total_revenue,
    COALESCE(c_stats.total_discount, 0) AS total_discount,
    COALESCE(c_stats.total_tax, 0) AS total_tax,
    COALESCE(c_stats.avg_transaction_value, 0) AS avg_transaction_value,
    COALESCE(c_stats.max_transaction_value, 0) AS max_transaction_value,
    -- Sales breakdown
    COALESCE(c_stats.standalone_revenue, 0) AS standalone_revenue,
    COALESCE(c_stats.package_revenue, 0) AS package_revenue,
    -- RFM metrics
    c_stats.days_since_last_transaction,
    c_stats.customer_tenure_days,
    c_stats.recency_days,
    COALESCE(c_stats.total_orders, 0) AS frequency,
    COALESCE(c_stats.total_revenue, 0) AS monetary
FROM dk.patient p
LEFT JOIN (
    SELECT 
        mrn,
        COUNT(DISTINCT sale_order_no) AS total_orders,
        COUNT(row_number) AS total_line_items,
        COUNT(DISTINCT date) AS unique_visit_days,
        MIN(date) AS first_transaction_date,
        MAX(date) AS last_transaction_date,
        SUM(amount_collected) AS total_revenue,
        SUM(discount) AS total_discount,
        SUM(tax_amount) AS total_tax,
        AVG(amount_collected) AS avg_transaction_value,
        MAX(amount_collected) AS max_transaction_value,
        SUM(standalone_sales_subtotal) AS standalone_revenue,
        SUM(package_sales_subtotal) AS package_revenue,
        CURRENT_DATE - MAX(date) AS days_since_last_transaction,
        CURRENT_DATE - MIN(date) AS customer_tenure_days,
        CURRENT_DATE - MAX(date) AS recency_days
    FROM dk.collection
    WHERE mrn IS NOT NULL
    GROUP BY mrn
) c_stats ON p.mrn = c_stats.mrn
WHERE p.mrn IS NOT NULL
ORDER BY p.mrn;

CREATE UNIQUE INDEX idx_mvw_patient_transactions_mrn ON dk.mvw_patient_transactions(mrn);
CREATE INDEX idx_mvw_patient_transactions_recency ON dk.mvw_patient_transactions(days_since_last_transaction);
CREATE INDEX idx_mvw_patient_transactions_monetary ON dk.mvw_patient_transactions(total_revenue DESC);

-- ============================================================
-- MATERIALIZED VIEW 4: Patient RFM
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_rfm CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_patient_rfm AS
WITH rfm_base AS (
    SELECT DISTINCT ON (mrn)
        mrn,
        gender,
        age,
        city_name,
        state_name,
        days_since_last_transaction AS recency,
        total_orders AS frequency,
        total_revenue AS monetary,
        NTILE(5) OVER (ORDER BY days_since_last_transaction DESC NULLS LAST) AS r_score,
        NTILE(5) OVER (ORDER BY total_orders) AS f_score,
        NTILE(5) OVER (ORDER BY total_revenue) AS m_score
    FROM dk.mvw_patient_transactions
    WHERE total_orders > 0
    ORDER BY mrn
),
rfm_scored AS (
    SELECT 
        *,
        r_score * 100 + f_score * 10 + m_score AS rfm_score,
        CONCAT(r_score::TEXT, f_score::TEXT, m_score::TEXT) AS rfm_segment_code
    FROM rfm_base
)
SELECT 
    *,
    CASE 
        WHEN rfm_segment_code IN ('555', '554', '544', '545', '454', '455', '445') THEN 'Champions'
        WHEN rfm_segment_code IN ('543', '444', '435', '355', '354', '345', '344', '335') THEN 'Loyal Customers'
        WHEN rfm_segment_code IN ('553', '551', '552', '541', '542', '533', '532', '531', '452', '451') THEN 'Potential Loyalists'
        WHEN rfm_segment_code IN ('512', '511', '422', '421', '412', '411', '311') THEN 'New Customers'
        WHEN rfm_segment_code IN ('155', '154', '144', '214', '215', '115', '114') THEN 'At Risk'
        WHEN rfm_segment_code IN ('254', '245', '253', '252', '243', '242', '235', '234', '225', '224', '153', '152', '145', '143', '142', '135', '134', '125', '124') THEN 'Cannot Lose Them'
        WHEN rfm_segment_code IN ('133', '132', '123', '122', '113', '112') THEN 'Hibernating'
        WHEN rfm_segment_code IN ('132', '123', '122', '212', '211') THEN 'Lost'
        ELSE 'Others'
    END AS rfm_segment
FROM rfm_scored;

CREATE UNIQUE INDEX idx_mvw_patient_rfm_mrn ON dk.mvw_patient_rfm(mrn);
CREATE INDEX idx_mvw_patient_rfm_segment ON dk.mvw_patient_rfm(rfm_segment);

-- ============================================================
-- MATERIALIZED VIEW 5: Patient LTV
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_ltv CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_patient_ltv AS
WITH monthly_stats AS (
    SELECT 
        mrn,
        DATE_TRUNC('month', date) AS transaction_month,
        SUM(amount_collected) AS monthly_revenue,
        COUNT(DISTINCT sale_order_no) AS monthly_orders
    FROM dk.collection
    WHERE mrn IS NOT NULL AND date IS NOT NULL
    GROUP BY mrn, DATE_TRUNC('month', date)
),
patient_stats AS (
    SELECT DISTINCT ON (mrn)
        mrn,
        COUNT(DISTINCT transaction_month) AS active_months,
        SUM(monthly_revenue) AS total_revenue,
        AVG(monthly_revenue) AS avg_monthly_revenue,
        STDDEV(monthly_revenue) AS stddev_monthly_revenue,
        MIN(transaction_month) AS first_month,
        MAX(transaction_month) AS last_month
    FROM monthly_stats
    GROUP BY mrn
    ORDER BY mrn
),
predicted_stats AS (
    SELECT 
        ps.*,
        EXTRACT(MONTH FROM AGE(CURRENT_DATE, ps.first_month))::INTEGER + 1 AS tenure_months,
        CASE 
            WHEN ps.active_months > 0 
            THEN ps.total_revenue / ps.active_months 
            ELSE 0 
        END AS observed_monthly_value,
        CASE 
            WHEN ps.active_months >= 3 THEN (ps.avg_monthly_revenue * 12)
            ELSE ps.total_revenue * 2
        END AS predicted_annual_ltv
    FROM patient_stats ps
)
SELECT DISTINCT ON (pt.mrn)
    pt.mrn,
    pt.gender,
    pt.age,
    pt.city_name,
    pt.state_name,
    pt.total_orders,
    pt.total_revenue AS observed_ltv,
    ps.active_months,
    ps.avg_monthly_revenue,
    ps.observed_monthly_value,
    ps.predicted_annual_ltv,
    ps.first_month AS cohort_month,
    ps.tenure_months,
    CASE 
        WHEN ps.predicted_annual_ltv >= 10000 THEN 'High Value'
        WHEN ps.predicted_annual_ltv >= 5000 THEN 'Medium Value'
        WHEN ps.predicted_annual_ltv >= 1000 THEN 'Low Value'
        ELSE 'Minimal Value'
    END AS ltv_segment
FROM predicted_stats ps
JOIN dk.mvw_patient_transactions pt ON ps.mrn = pt.mrn
ORDER BY pt.mrn;

CREATE UNIQUE INDEX idx_mvw_patient_ltv_mrn ON dk.mvw_patient_ltv(mrn);
CREATE INDEX idx_mvw_patient_ltv_segment ON dk.mvw_patient_ltv(ltv_segment);

-- ============================================================
-- MATERIALIZED VIEW 6: Calendar Effects
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_calendar_effects CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_calendar_effects AS
SELECT 
    transaction_date,
    transaction_year,
    transaction_month,
    transaction_quarter,
    transaction_year_month,
    transaction_day_name,
    is_weekend,
    branch,
    COUNT(*) AS transaction_count,
    SUM(amount_collected) AS total_revenue,
    SUM(discount_amount) AS total_discounts,
    SUM(tax_amount) AS total_tax,
    AVG(amount_collected) AS avg_transaction_value,
    COUNT(DISTINCT mrn) AS unique_patients,
    COUNT(DISTINCT sale_order_no) AS unique_orders
FROM dk.mvw_transaction_flat
GROUP BY transaction_date, transaction_year, transaction_month, transaction_quarter,
         transaction_year_month, transaction_day_name, is_weekend, branch;

CREATE UNIQUE INDEX idx_mvw_calendar_effects_pk ON dk.mvw_calendar_effects(transaction_date, branch);
CREATE INDEX idx_mvw_calendar_effects_ym ON dk.mvw_calendar_effects(transaction_year_month);
CREATE INDEX idx_mvw_calendar_effects_branch ON dk.mvw_calendar_effects(branch);

-- ============================================================
-- MATERIALIZED VIEW 7: Branch Performance
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_branch_performance CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_branch_performance AS
SELECT 
    branch,
    transaction_year,
    transaction_month,
    transaction_year_month,
    COUNT(*) AS total_transactions,
    COUNT(DISTINCT sale_order_no) AS unique_orders,
    COUNT(DISTINCT mrn) AS unique_patients,
    SUM(total_sales) AS gross_revenue,
    SUM(discount_amount) AS total_discounts,
    SUM(amount_collected) AS net_revenue,
    SUM(tax_amount) AS total_tax,
    AVG(amount_collected) AS avg_transaction_value,
    SUM(standalone_subtotal) AS standalone_revenue,
    SUM(package_subtotal) AS package_revenue,
    COUNT(DISTINCT CASE WHEN package_subtotal > 0 THEN transaction_id END) AS package_transactions
FROM dk.mvw_transaction_flat
GROUP BY branch, transaction_year, transaction_month, transaction_year_month;

CREATE UNIQUE INDEX idx_mvw_branch_perf_pk ON dk.mvw_branch_performance(branch, transaction_year_month);

-- ============================================================
-- MATERIALIZED VIEW 8: Product Performance
-- Note: Product-level analysis is limited since collection table
-- aggregates by category rather than individual products.
-- This view shows category-level performance.
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_product_performance CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_product_performance AS
SELECT 
    branch,
    transaction_year_month,
    -- Standalone categories
    SUM(standalone_consultations) AS consultations_revenue,
    SUM(standalone_services) AS services_revenue,
    SUM(standalone_medications) AS medications_revenue,
    SUM(standalone_supplements) AS supplements_revenue,
    SUM(standalone_skincare) AS skincare_revenue,
    SUM(standalone_other) AS other_revenue,
    SUM(standalone_subtotal) AS standalone_total,
    -- Package categories
    SUM(package_services) AS package_services_revenue,
    SUM(package_medications) AS package_medications_revenue,
    SUM(package_supplements) AS package_supplements_revenue,
    SUM(package_skincare) AS package_skincare_revenue,
    SUM(package_other) AS package_other_revenue,
    SUM(package_subtotal) AS package_total,
    -- Totals
    SUM(total_sales) AS total_revenue,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT mrn) AS unique_patients,
    COUNT(DISTINCT sale_order_no) AS unique_orders
FROM dk.mvw_transaction_flat
GROUP BY branch, transaction_year_month;

CREATE UNIQUE INDEX idx_mvw_product_perf_pk ON dk.mvw_product_performance(branch, transaction_year_month);

-- ============================================================
-- MATERIALIZED VIEW 9: D+3 Follow-up List
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_d3_followup_list CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_d3_followup_list AS
WITH recent_visits AS (
    SELECT 
        mrn,
        date AS last_visit_date,
        branch AS last_branch,
        amount_collected AS last_visit_amount,
        ROW_NUMBER() OVER (PARTITION BY mrn ORDER BY date DESC) AS visit_rank
    FROM (
        SELECT DISTINCT mrn, date, branch, amount_collected
        FROM dk.collection
        WHERE mrn IS NOT NULL AND date IS NOT NULL
    ) distinct_visits
)
SELECT 
    rv.mrn,
    pe.gender,
    pe.age,
    pe.city_name,
    pe.state_name,
    pe.patient_status,
    pe.age_group,
    rv.last_visit_date,
    rv.last_branch,
    rv.last_visit_amount,
    CURRENT_DATE - rv.last_visit_date AS days_since_visit,
    CASE 
        WHEN rv.last_visit_amount >= 1000 AND CURRENT_DATE - rv.last_visit_date = 3 THEN 'High Priority'
        WHEN rv.last_visit_amount >= 500 AND CURRENT_DATE - rv.last_visit_date = 3 THEN 'Medium Priority'
        WHEN CURRENT_DATE - rv.last_visit_date = 3 THEN 'Standard Priority'
        ELSE 'Not Due'
    END AS followup_priority,
    CASE 
        WHEN CURRENT_DATE - rv.last_visit_date = 3 THEN 'Send Follow-up Message'
        ELSE 'Monitor'
    END AS recommended_action,
    pe.recency_score,
    pr.rfm_segment,
    pl.ltv_segment
FROM recent_visits rv
LEFT JOIN dk.mvw_patient_enriched pe ON rv.mrn = pe.mrn
LEFT JOIN dk.mvw_patient_rfm pr ON rv.mrn = pr.mrn
LEFT JOIN dk.mvw_patient_ltv pl ON rv.mrn = pl.mrn
WHERE rv.visit_rank = 1
  AND rv.last_visit_date >= CURRENT_DATE - INTERVAL '30 days';

CREATE UNIQUE INDEX idx_mvw_d3_followup_mrn ON dk.mvw_d3_followup_list(mrn);
CREATE INDEX idx_mvw_d3_followup_priority ON dk.mvw_d3_followup_list(followup_priority);

-- ============================================================
-- SCHEDULING (Windows: Use pgAgent or Windows Task Scheduler)
-- pg_cron is NOT available on Windows.
-- ============================================================

-- For Windows, schedule via:
-- 1. pgAgent (if installed): Create job to run daily at 1:00 AM
--    Command: SELECT dk.refresh_all_mvws();
-- 2. Windows Task Scheduler + psql:
--    psql -U postgres -d postgres -c "SELECT dk.refresh_all_mvws();"

-- Log function
COMMENT ON FUNCTION dk.refresh_all_mvws() IS 'Refreshes all materialized views concurrently. On Windows, schedule via pgAgent or Windows Task Scheduler.';