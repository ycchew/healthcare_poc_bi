-- ============================================================
-- ST-01: Data Foundation & Infrastructure
-- 02_materialized_views.sql
-- Materialized Views for Power BI Performance
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- MATERIALIZED VIEW REFRESH FUNCTION
-- ============================================================

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
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_enriched CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_patient_enriched AS
SELECT 
    p.id,
    p.mrn,
    p.name,
    p.email,
    p.phone,
    p.date_of_birth,
    p.gender,
    p.address,
    p.postcode,
    p.city,
    p.state,
    p.country,
    p.registration_date,
    p.first_visit_date,
    p.last_visit_date,
    p.total_visits,
    p.total_revenue,
    EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.date_of_birth))::INTEGER AS age,
    CASE 
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.date_of_birth)) < 18 THEN 'Under 18'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.date_of_birth)) < 25 THEN '18-24'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.date_of_birth)) < 35 THEN '25-34'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.date_of_birth)) < 45 THEN '35-44'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.date_of_birth)) < 55 THEN '45-54'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.date_of_birth)) < 65 THEN '55-64'
        ELSE '65+'
    END AS age_group,
    CASE 
        WHEN p.last_visit_date IS NOT NULL 
        THEN (CURRENT_DATE - p.last_visit_date)::INTEGER 
        ELSE NULL 
    END AS days_since_last_visit,
    CASE 
        WHEN p.last_visit_date IS NULL THEN 'New'
        WHEN (CURRENT_DATE - p.last_visit_date) <= 30 THEN 'Active'
        WHEN (CURRENT_DATE - p.last_visit_date) <= 90 THEN 'At Risk'
        ELSE 'Churned'
    END AS patient_status,
    CASE 
        WHEN p.last_visit_date IS NULL THEN 1
        WHEN (CURRENT_DATE - p.last_visit_date) <= 30 THEN 5
        WHEN (CURRENT_DATE - p.last_visit_date) <= 60 THEN 4
        WHEN (CURRENT_DATE - p.last_visit_date) <= 90 THEN 3
        WHEN (CURRENT_DATE - p.last_visit_date) <= 180 THEN 2
        ELSE 1
    END AS recency_score,
    p.created_at,
    p.updated_at
FROM dk.patient p;

-- Unique index for concurrent refresh
CREATE UNIQUE INDEX idx_mvw_patient_enriched_mrn ON dk.mvw_patient_enriched(mrn);
CREATE INDEX idx_mvw_patient_enriched_status ON dk.mvw_patient_enriched(patient_status);
CREATE INDEX idx_mvw_patient_enriched_age_group ON dk.mvw_patient_enriched(age_group);

-- ============================================================
-- MATERIALIZED VIEW 2: Transaction Flat
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_transaction_flat CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_transaction_flat AS
SELECT 
    c.id AS transaction_id,
    c.sale_order_no,
    c.mrn,
    p.name AS patient_name,
    p.email AS patient_email,
    p.phone AS patient_phone,
    p.gender AS patient_gender,
    EXTRACT(YEAR FROM AGE(c.transaction_date, p.date_of_birth))::INTEGER AS patient_age_at_transaction,
    c.transaction_date,
    c.transaction_datetime,
    EXTRACT(YEAR FROM c.transaction_date)::INTEGER AS transaction_year,
    EXTRACT(MONTH FROM c.transaction_date)::INTEGER AS transaction_month,
    EXTRACT(QUARTER FROM c.transaction_date)::INTEGER AS transaction_quarter,
    TO_CHAR(c.transaction_date, 'YYYY-MM') AS transaction_year_month,
    TO_CHAR(c.transaction_date, 'Day') AS transaction_day_name,
    CASE 
        WHEN EXTRACT(DOW FROM c.transaction_date) IN (0, 6) THEN 'Weekend'
        ELSE 'Weekday'
    END AS is_weekend,
    c.branch_code,
    c.branch_name,
    c.doctor_code,
    c.doctor_name,
    c.product_code,
    c.product_name,
    c.category,
    c.subcategory,
    c.quantity,
    c.unit_price,
    c.gross_amount,
    c.discount_amount,
    CASE 
        WHEN c.gross_amount > 0 
        THEN ROUND((c.discount_amount / c.gross_amount) * 100, 2)
        ELSE 0 
    END AS discount_percentage,
    c.net_amount,
    c.tax_amount,
    c.total_amount,
    c.payment_method,
    c.is_package,
    c.package_code,
    c.package_name,
    c.session_number,
    c.total_sessions,
    CASE 
        WHEN c.total_sessions > 0 
        THEN ROUND((c.session_number::NUMERIC / c.total_sessions) * 100, 2)
        ELSE NULL 
    END AS session_completion_pct
FROM dk.collection c
LEFT JOIN dk.patient p ON c.mrn = p.mrn;

CREATE UNIQUE INDEX idx_mvw_transaction_flat_id ON dk.mvw_transaction_flat(transaction_id);
CREATE INDEX idx_mvw_transaction_flat_date ON dk.mvw_transaction_flat(transaction_date);
CREATE INDEX idx_mvw_transaction_flat_mrn ON dk.mvw_transaction_flat(mrn);
CREATE INDEX idx_mvw_transaction_flat_branch ON dk.mvw_transaction_flat(branch_code);
CREATE INDEX idx_mvw_transaction_flat_ym ON dk.mvw_transaction_flat(transaction_year_month);

-- ============================================================
-- MATERIALIZED VIEW 3: Patient Transactions (RFM Base)
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_transactions CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_patient_transactions AS
SELECT 
    p.mrn,
    p.name AS patient_name,
    p.email,
    p.phone,
    p.gender,
    p.date_of_birth,
    EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.date_of_birth))::INTEGER AS age,
    p.postcode,
    p.city,
    p.state,
    p.registration_date,
    p.first_visit_date,
    p.last_visit_date,
    COUNT(DISTINCT c.sale_order_no) AS total_orders,
    COUNT(c.id) AS total_line_items,
    COUNT(DISTINCT c.transaction_date) AS unique_visit_days,
    MIN(c.transaction_date) AS first_transaction_date,
    MAX(c.transaction_date) AS last_transaction_date,
    COALESCE(SUM(c.gross_amount), 0) AS total_gross_revenue,
    COALESCE(SUM(c.discount_amount), 0) AS total_discount_amount,
    COALESCE(SUM(c.net_amount), 0) AS total_net_revenue,
    COALESCE(SUM(c.total_amount), 0) AS total_amount,
    COALESCE(AVG(c.net_amount), 0) AS avg_transaction_value,
    COALESCE(MAX(c.net_amount), 0) AS max_transaction_value,
    COUNT(DISTINCT c.product_code) AS unique_products_purchased,
    COUNT(DISTINCT c.category) AS unique_categories,
    SUM(CASE WHEN c.is_package THEN 1 ELSE 0 END) AS package_transactions,
    COUNT(DISTINCT CASE WHEN c.is_package THEN c.package_code END) AS unique_packages,
    CURRENT_DATE - MAX(c.transaction_date) AS days_since_last_transaction,
    CURRENT_DATE - MIN(c.transaction_date) AS customer_tenure_days,
    CURRENT_DATE - MAX(c.transaction_date) AS recency_days,
    COUNT(DISTINCT c.sale_order_no) AS frequency,
    COALESCE(SUM(c.net_amount), 0) AS monetary
FROM dk.patient p
LEFT JOIN dk.collection c ON p.mrn = c.mrn
GROUP BY p.id, p.mrn, p.name, p.email, p.phone, p.gender, p.date_of_birth,
         p.postcode, p.city, p.state, p.registration_date, 
         p.first_visit_date, p.last_visit_date;

CREATE UNIQUE INDEX idx_mvw_patient_transactions_mrn ON dk.mvw_patient_transactions(mrn);
CREATE INDEX idx_mvw_patient_transactions_recency ON dk.mvw_patient_transactions(days_since_last_transaction);
CREATE INDEX idx_mvw_patient_transactions_monetary ON dk.mvw_patient_transactions(total_net_revenue DESC);

-- ============================================================
-- MATERIALIZED VIEW 4: Patient RFM
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_rfm CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_patient_rfm AS
WITH rfm_base AS (
    SELECT 
        mrn,
        patient_name,
        email,
        phone,
        days_since_last_transaction AS recency,
        total_orders AS frequency,
        total_net_revenue AS monetary,
        NTILE(5) OVER (ORDER BY days_since_last_transaction DESC) AS r_score,
        NTILE(5) OVER (ORDER BY total_orders) AS f_score,
        NTILE(5) OVER (ORDER BY total_net_revenue) AS m_score
    FROM dk.mvw_patient_transactions
    WHERE total_orders > 0
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
        WHEN rfm_segment_code IN ('155', '254', '245', '253', '252', '243', '242', '235', '234', '225', '224', '153', '152', '145', '143', '142', '135', '134', '125', '124') THEN 'Cannot Lose Them'
        WHEN rfm_segment_code IN ('155', '144', '214', '215', '115', '114', '113') THEN 'Hibernating'
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
        DATE_TRUNC('month', transaction_date) AS transaction_month,
        SUM(net_amount) AS monthly_revenue,
        COUNT(DISTINCT sale_order_no) AS monthly_orders
    FROM dk.collection
    GROUP BY mrn, DATE_TRUNC('month', transaction_date)
),
patient_stats AS (
    SELECT 
        mrn,
        COUNT(DISTINCT transaction_month) AS active_months,
        SUM(monthly_revenue) AS total_revenue,
        AVG(monthly_revenue) AS avg_monthly_revenue,
        STDDEV(monthly_revenue) AS stddev_monthly_revenue,
        MIN(transaction_month) AS first_month,
        MAX(transaction_month) AS last_month
    FROM monthly_stats
    GROUP BY mrn
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
SELECT 
    pt.mrn,
    pt.patient_name,
    pt.email,
    pt.phone,
    pt.total_orders,
    pt.total_net_revenue AS observed_ltv,
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
JOIN dk.mvw_patient_transactions pt ON ps.mrn = pt.mrn;

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
    branch_code,
    branch_name,
    COUNT(*) AS transaction_count,
    SUM(gross_amount) AS gross_revenue,
    SUM(discount_amount) AS total_discounts,
    SUM(net_amount) AS net_revenue,
    AVG(net_amount) AS avg_transaction_value,
    COUNT(DISTINCT mrn) AS unique_patients,
    COUNT(DISTINCT sale_order_no) AS unique_orders
FROM dk.mvw_transaction_flat
GROUP BY transaction_date, transaction_year, transaction_month, transaction_quarter,
         transaction_year_month, transaction_day_name, is_weekend, branch_code, branch_name;

CREATE UNIQUE INDEX idx_mvw_calendar_effects_pk ON dk.mvw_calendar_effects(transaction_date, branch_code);
CREATE INDEX idx_mvw_calendar_effects_ym ON dk.mvw_calendar_effects(transaction_year_month);
CREATE INDEX idx_mvw_calendar_effects_branch ON dk.mvw_calendar_effects(branch_code);

-- ============================================================
-- MATERIALIZED VIEW 7: Branch Performance
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_branch_performance CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_branch_performance AS
SELECT 
    branch_code,
    branch_name,
    transaction_year,
    transaction_month,
    transaction_year_month,
    COUNT(*) AS total_transactions,
    COUNT(DISTINCT sale_order_no) AS unique_orders,
    COUNT(DISTINCT mrn) AS unique_patients,
    SUM(gross_amount) AS gross_revenue,
    SUM(discount_amount) AS total_discounts,
    SUM(net_amount) AS net_revenue,
    AVG(net_amount) AS avg_transaction_value,
    SUM(CASE WHEN is_package THEN net_amount ELSE 0 END) AS package_revenue,
    SUM(CASE WHEN is_package THEN 1 ELSE 0 END) AS package_transactions,
    COUNT(DISTINCT product_code) AS unique_products_sold,
    COUNT(DISTINCT doctor_code) AS unique_doctors
FROM dk.mvw_transaction_flat
GROUP BY branch_code, branch_name, transaction_year, transaction_month, transaction_year_month;

CREATE UNIQUE INDEX idx_mvw_branch_perf_pk ON dk.mvw_branch_performance(branch_code, transaction_year_month);

-- ============================================================
-- MATERIALIZED VIEW 8: Product Performance
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_product_performance CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_product_performance AS
SELECT 
    product_code,
    product_name,
    category,
    subcategory,
    is_package,
    transaction_year_month,
    branch_code,
    COUNT(*) AS units_sold,
    SUM(quantity) AS total_quantity,
    SUM(gross_amount) AS gross_revenue,
    SUM(discount_amount) AS total_discounts,
    SUM(net_amount) AS net_revenue,
    AVG(net_amount) AS avg_selling_price,
    COUNT(DISTINCT mrn) AS unique_buyers,
    COUNT(DISTINCT sale_order_no) AS unique_orders
FROM dk.mvw_transaction_flat
GROUP BY product_code, product_name, category, subcategory, is_package, 
         transaction_year_month, branch_code;

CREATE UNIQUE INDEX idx_mvw_product_perf_pk ON dk.mvw_product_performance(product_code, transaction_year_month, branch_code);
CREATE INDEX idx_mvw_product_perf_category ON dk.mvw_product_performance(category);

-- ============================================================
-- MATERIALIZED VIEW 9: D+3 Follow-up List
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_d3_followup_list CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_d3_followup_list AS
WITH recent_visits AS (
    SELECT 
        mrn,
        transaction_date AS last_visit_date,
        branch_name AS last_branch,
        doctor_name AS last_doctor,
        net_amount AS last_visit_amount,
        LAG(transaction_date) OVER (PARTITION BY mrn ORDER BY transaction_date) AS prev_visit_date,
        LEAD(transaction_date) OVER (PARTITION BY mrn ORDER BY transaction_date) AS next_visit_date,
        ROW_NUMBER() OVER (PARTITION BY mrn ORDER BY transaction_date DESC) AS visit_rank
    FROM (
        SELECT DISTINCT mrn, transaction_date, branch_name, doctor_name, net_amount
        FROM dk.mvw_transaction_flat
    ) distinct_visits
)
SELECT 
    rv.mrn,
    pe.name AS patient_name,
    pe.phone,
    pe.email,
    rv.last_visit_date,
    rv.last_branch,
    rv.last_doctor,
    rv.last_visit_amount,
    CURRENT_DATE - rv.last_visit_date AS days_since_visit,
    rv.prev_visit_date,
    CASE 
        WHEN rv.prev_visit_date IS NOT NULL 
        THEN rv.last_visit_date - rv.prev_visit_date 
        ELSE NULL 
    END AS days_between_visits,
    rv.next_visit_date AS scheduled_return_date,
    CASE 
        WHEN rv.last_visit_amount >= 1000 AND CURRENT_DATE - rv.last_visit_date = 3 THEN 'High Priority'
        WHEN rv.last_visit_amount >= 500 AND CURRENT_DATE - rv.last_visit_date = 3 THEN 'Medium Priority'
        WHEN CURRENT_DATE - rv.last_visit_date = 3 THEN 'Standard Priority'
        ELSE 'Not Due'
    END AS followup_priority,
    CASE 
        WHEN rv.next_visit_date IS NOT NULL THEN 'Already Scheduled'
        WHEN CURRENT_DATE - rv.last_visit_date = 3 THEN 'Send Follow-up Message'
        ELSE 'Monitor'
    END AS recommended_action,
    pe.patient_status,
    pe.rfm_segment,
    pe.ltv_segment
FROM recent_visits rv
LEFT JOIN (
    SELECT mrn, name, phone, email, patient_status, rfm_segment, ltv_segment
    FROM dk.mvw_patient_enriched pe
    LEFT JOIN dk.mvw_patient_rfm pr ON pe.mrn = pr.mrn
    LEFT JOIN dk.mvw_patient_ltv pl ON pe.mrn = pl.mrn
) pe ON rv.mrn = pe.mrn
WHERE rv.visit_rank = 1
  AND rv.last_visit_date >= CURRENT_DATE - INTERVAL '30 days'
  AND pe.phone IS NOT NULL;

CREATE UNIQUE INDEX idx_mvw_d3_followup_mrn ON dk.mvw_d3_followup_list(mrn);
CREATE INDEX idx_mvw_d3_followup_priority ON dk.mvw_d3_followup_list(followup_priority);

-- ============================================================
-- SCHEDULE REFRESH
-- ============================================================

-- Schedule daily refresh at 1:00 AM
SELECT cron.schedule('mvw-refresh-daily', '0 1 * * *', 'SELECT dk.refresh_all_mvws()');

-- Log the scheduled job
COMMENT ON FUNCTION dk.refresh_all_mvws() IS 'Refreshes all materialized views concurrently. Scheduled to run daily at 1:00 AM via pg_cron.';
