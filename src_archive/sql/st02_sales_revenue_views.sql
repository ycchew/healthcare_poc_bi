-- ============================================================
-- ST-02: Sales & Revenue Analytics
-- sales_revenue_views.sql
-- Views for Sales Performance and Revenue Analysis
-- ============================================================

-- ============================================================
-- VIEW 1: Revenue Trend Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_revenue_trends AS
WITH monthly_revenue AS (
    SELECT 
        transaction_year,
        transaction_month,
        transaction_year_month,
        transaction_quarter,
        SUM(gross_revenue) AS gross_revenue,
        SUM(total_discounts) AS total_discounts,
        SUM(net_revenue) AS net_revenue,
        AVG(avg_transaction_value) AS avg_transaction_value,
        SUM(unique_patients) AS unique_patients,
        SUM(unique_orders) AS unique_orders
    FROM dk.mvw_calendar_effects
    GROUP BY transaction_year, transaction_month, transaction_year_month, transaction_quarter
),
with_growth AS (
    SELECT 
        *,
        LAG(net_revenue) OVER (ORDER BY transaction_year_month) AS prev_month_revenue,
        LAG(net_revenue, 12) OVER (ORDER BY transaction_year_month) AS prev_year_revenue,
        AVG(net_revenue) OVER (
            ORDER BY transaction_year_month 
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS moving_avg_3m
    FROM monthly_revenue
)
SELECT 
    *,
    CASE 
        WHEN prev_month_revenue IS NOT NULL AND prev_month_revenue > 0 
        THEN ROUND(((net_revenue - prev_month_revenue) / prev_month_revenue) * 100, 2)
        ELSE NULL 
    END AS mom_growth_pct,
    CASE 
        WHEN prev_year_revenue IS NOT NULL AND prev_year_revenue > 0 
        THEN ROUND(((net_revenue - prev_year_revenue) / prev_year_revenue) * 100, 2)
        ELSE NULL 
    END AS yoy_growth_pct,
    CASE 
        WHEN net_revenue > moving_avg_3m THEN 'Above Trend'
        WHEN net_revenue < moving_avg_3m THEN 'Below Trend'
        ELSE 'On Trend'
    END AS trend_status
FROM with_growth
ORDER BY transaction_year_month;

-- ============================================================
-- VIEW 2: Branch Performance Ranking
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_branch_ranking AS
WITH branch_metrics AS (
    SELECT 
        branch_code,
        branch_name,
        transaction_year_month,
        total_transactions,
        unique_patients,
        net_revenue,
        avg_transaction_value,
        package_revenue,
        unique_doctors,
        -- Calculate ratios
        CASE WHEN unique_patients > 0 
             THEN total_transactions::NUMERIC / unique_patients 
             ELSE 0 
        END AS transactions_per_patient,
        CASE WHEN net_revenue > 0 
             THEN (package_revenue / net_revenue) * 100 
             ELSE 0 
        END AS package_revenue_pct
    FROM dk.mvw_branch_performance
),
ranked AS (
    SELECT 
        *,
        RANK() OVER (PARTITION BY transaction_year_month ORDER BY net_revenue DESC) AS revenue_rank,
        RANK() OVER (PARTITION BY transaction_year_month ORDER BY unique_patients DESC) AS patient_rank,
        RANK() OVER (PARTITION BY transaction_year_month ORDER BY avg_transaction_value DESC) AS atv_rank,
        AVG(net_revenue) OVER (
            PARTITION BY branch_code 
            ORDER BY transaction_year_month 
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS revenue_3m_avg
    FROM branch_metrics
)
SELECT 
    branch_code,
    branch_name,
    transaction_year_month,
    total_transactions,
    unique_patients,
    ROUND(net_revenue, 2) AS net_revenue,
    ROUND(avg_transaction_value, 2) AS avg_transaction_value,
    ROUND(package_revenue, 2) AS package_revenue,
    ROUND(package_revenue_pct, 2) AS package_revenue_pct,
    unique_doctors,
    ROUND(transactions_per_patient, 2) AS transactions_per_patient,
    revenue_rank,
    patient_rank,
    atv_rank,
    ROUND(revenue_3m_avg, 2) AS revenue_3m_avg,
    -- Performance tier
    CASE 
        WHEN revenue_rank <= 3 THEN 'Top Performer'
        WHEN revenue_rank <= 7 THEN 'Middle Performer'
        ELSE 'Needs Improvement'
    END AS performance_tier
FROM ranked;

-- ============================================================
-- VIEW 3: Calendar Effects Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_calendar_analysis AS
WITH day_stats AS (
    SELECT 
        transaction_day_name,
        is_weekend,
        AVG(net_revenue) AS avg_daily_revenue,
        AVG(unique_patients) AS avg_daily_patients,
        AVG(avg_transaction_value) AS avg_atv,
        COUNT(DISTINCT transaction_date) AS day_count
    FROM dk.mvw_calendar_effects
    GROUP BY transaction_day_name, is_weekend
),
month_stats AS (
    SELECT 
        transaction_month,
        transaction_quarter,
        AVG(net_revenue) AS avg_monthly_revenue,
        SUM(net_revenue) AS total_monthly_revenue,
        AVG(unique_patients) AS avg_monthly_patients
    FROM dk.mvw_calendar_effects
    GROUP BY transaction_month, transaction_quarter
),
peak_days AS (
    SELECT 
        transaction_date,
        net_revenue,
        unique_patients,
        AVG(net_revenue) OVER (
            ORDER BY transaction_date 
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS revenue_7d_avg,
        PERCENT_RANK() OVER (ORDER BY net_revenue) AS revenue_percentile
    FROM dk.mvw_calendar_effects
)
SELECT 
    'Day of Week' AS analysis_type,
    transaction_day_name AS dimension,
    is_weekend::TEXT AS attribute,
    ROUND(avg_daily_revenue, 2) AS metric_value,
    ROUND(avg_daily_patients, 0) AS patient_count,
    day_count AS occurrence_count
FROM day_stats
UNION ALL
SELECT 
    'Month' AS analysis_type,
    'Month ' || transaction_month::TEXT AS dimension,
    'Q' || transaction_quarter::TEXT AS attribute,
    ROUND(avg_monthly_revenue, 2) AS metric_value,
    ROUND(avg_monthly_patients, 0) AS patient_count,
    1 AS occurrence_count
FROM month_stats
ORDER BY analysis_type, dimension;

-- ============================================================
-- VIEW 4: Discount Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_discount_analysis AS
WITH transaction_discounts AS (
    SELECT 
        transaction_id,
        transaction_date,
        transaction_year_month,
        branch_code,
        branch_name,
        mrn,
        patient_name,
        gross_amount,
        discount_amount,
        net_amount,
        discount_percentage,
        category,
        product_name,
        CASE 
            WHEN discount_percentage = 0 THEN 'No Discount'
            WHEN discount_percentage <= 5 THEN 'Low (<=5%)'
            WHEN discount_percentage <= 10 THEN 'Medium (6-10%)'
            WHEN discount_percentage <= 20 THEN 'High (11-20%)'
            ELSE 'Very High (>20%)'
        END AS discount_tier
    FROM dk.mvw_transaction_flat
    WHERE discount_amount > 0 OR discount_percentage > 0
)
SELECT 
    discount_tier,
    transaction_year_month,
    branch_code,
    COUNT(*) AS transaction_count,
    ROUND(AVG(discount_percentage), 2) AS avg_discount_pct,
    ROUND(SUM(discount_amount), 2) AS total_discount_amount,
    ROUND(SUM(net_amount), 2) AS total_net_revenue,
    ROUND(AVG(net_amount), 2) AS avg_transaction_value,
    COUNT(DISTINCT mrn) AS unique_patients,
    -- Calculate discount impact
    ROUND(
        (SUM(discount_amount) / NULLIF(SUM(gross_amount), 0)) * 100, 
        2
    ) AS discount_to_gross_ratio
FROM transaction_discounts
GROUP BY discount_tier, transaction_year_month, branch_code
ORDER BY transaction_year_month, 
         CASE discount_tier 
             WHEN 'No Discount' THEN 1
             WHEN 'Low (<=5%)' THEN 2
             WHEN 'Medium (6-10%)' THEN 3
             WHEN 'High (11-20%)' THEN 4
             ELSE 5
         END;

-- ============================================================
-- VIEW 5: Executive Summary KPIs
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_executive_kpis AS
WITH current_period AS (
    SELECT 
        DATE_TRUNC('month', CURRENT_DATE) AS current_month,
        DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') AS last_month,
        DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 year') AS last_year_month
),
current_metrics AS (
    SELECT 
        SUM(net_revenue) AS current_month_revenue,
        SUM(unique_patients) AS current_month_patients,
        COUNT(DISTINCT branch_code) AS active_branches,
        AVG(avg_transaction_value) AS current_month_atv
    FROM dk.mvw_calendar_effects ce
    JOIN current_period cp ON ce.transaction_year_month = TO_CHAR(cp.current_month, 'YYYY-MM')
),
last_month_metrics AS (
    SELECT 
        SUM(net_revenue) AS last_month_revenue,
        SUM(unique_patients) AS last_month_patients,
        AVG(avg_transaction_value) AS last_month_atv
    FROM dk.mvw_calendar_effects ce
    JOIN current_period cp ON ce.transaction_year_month = TO_CHAR(cp.last_month, 'YYYY-MM')
),
last_year_metrics AS (
    SELECT 
        SUM(net_revenue) AS last_year_revenue,
        SUM(unique_patients) AS last_year_patients
    FROM dk.mvw_calendar_effects ce
    JOIN current_period cp ON ce.transaction_year_month = TO_CHAR(cp.last_year_month, 'YYYY-MM')
),
ytd_metrics AS (
    SELECT 
        SUM(net_revenue) AS ytd_revenue,
        SUM(unique_patients) AS ytd_patients
    FROM dk.mvw_calendar_effects
    WHERE transaction_year = EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER
)
SELECT 
    ROUND(cm.current_month_revenue, 2) AS current_month_revenue,
    ROUND(lm.last_month_revenue, 2) AS last_month_revenue,
    ROUND(ly.last_year_revenue, 2) AS last_year_revenue,
    ROUND(
        ((cm.current_month_revenue - lm.last_month_revenue) / NULLIF(lm.last_month_revenue, 0)) * 100, 
        2
    ) AS mom_revenue_growth_pct,
    ROUND(
        ((cm.current_month_revenue - ly.last_year_revenue) / NULLIF(ly.last_year_revenue, 0)) * 100, 
        2
    ) AS yoy_revenue_growth_pct,
    ROUND(ym.ytd_revenue, 2) AS ytd_revenue,
    ROUND(cm.current_month_patients, 0) AS current_month_patients,
    ROUND(lm.last_month_patients, 0) AS last_month_patients,
    ROUND(cm.current_month_atv, 2) AS current_month_atv,
    ROUND(lm.last_month_atv, 2) AS last_month_atv,
    cm.active_branches,
    CURRENT_DATE AS report_date
FROM current_metrics cm
CROSS JOIN last_month_metrics lm
CROSS JOIN last_year_metrics ly
CROSS JOIN ytd_metrics ym;

-- ============================================================
-- MATERIALIZED VIEW: Sales Performance Summary
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_sales_performance CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_sales_performance AS
SELECT 
    branch_code,
    branch_name,
    transaction_year,
    transaction_month,
    transaction_year_month,
    transaction_quarter,
    COUNT(*) AS total_transactions,
    COUNT(DISTINCT sale_order_no) AS unique_orders,
    COUNT(DISTINCT mrn) AS unique_patients,
    SUM(gross_amount) AS gross_revenue,
    SUM(discount_amount) AS total_discounts,
    SUM(net_amount) AS net_revenue,
    AVG(net_amount) AS avg_transaction_value,
    SUM(CASE WHEN is_package THEN net_amount ELSE 0 END) AS package_revenue,
    SUM(CASE WHEN is_package THEN 1 ELSE 0 END) AS package_transactions,
    COUNT(DISTINCT product_code) AS unique_products,
    COUNT(DISTINCT doctor_code) AS unique_doctors,
    MIN(transaction_date) AS period_start,
    MAX(transaction_date) AS period_end
FROM dk.mvw_transaction_flat
GROUP BY branch_code, branch_name, transaction_year, transaction_month, 
         transaction_year_month, transaction_quarter;

CREATE UNIQUE INDEX idx_mvw_sales_perf_pk 
ON dk.mvw_sales_performance(branch_code, transaction_year_month);

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON VIEW dk.vw_revenue_trends IS 'Monthly revenue trends with MoM and YoY growth calculations';
COMMENT ON VIEW dk.vw_branch_ranking IS 'Branch performance ranking by revenue, patients, and ATV';
COMMENT ON VIEW dk.vw_calendar_analysis IS 'Calendar effects analysis by day of week and month';
COMMENT ON VIEW dk.vw_discount_analysis IS 'Discount impact analysis by tier and branch';
COMMENT ON VIEW dk.vw_executive_kpis IS 'Executive dashboard KPIs for monthly reporting';
COMMENT ON MATERIALIZED VIEW dk.mvw_sales_performance IS 'Sales performance summary for Power BI';
