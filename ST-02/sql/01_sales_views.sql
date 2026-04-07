-- ============================================================================
-- ST-02: Sales & Revenue Analytics
-- File: 01_sales_views.sql
-- Description: Core SQL views for sales analytics using ST-01 base tables
-- Schema: dk
-- Dependencies: dk.collection
-- Actual Schema Fields (from dk.collection):
--   - row_number (not id)
--   - date (not transaction_date)
--   - branch (not branch_code)
--   - amount_collected (not net_amount)
--   - Pre-split revenue columns: standalone_sales_*, package_sales_*
-- ============================================================================

-- ============================================================================
-- SECTION 1: Daily Sales Summary View
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_daily_sales_summary AS
WITH daily_agg AS (
    SELECT 
        c.date AS transaction_date,
        c.branch,
        
        -- Transaction counts
        COUNT(DISTINCT c.row_number) AS total_transactions,
        COUNT(DISTINCT c.mrn) AS unique_patients,
        COUNT(DISTINCT c.sale_order_no) AS unique_orders,
        
        -- Standalone sales (pre-split columns)
        COALESCE(SUM(c.standalone_sales_consultations), 0) AS standalone_consultations,
        COALESCE(SUM(c.standalone_sales_services), 0) AS standalone_services,
        COALESCE(SUM(c.standalone_sales_medications), 0) AS standalone_medications,
        COALESCE(SUM(c.standalone_sales_supplements_supplement_rm5_amount), 0) +
        COALESCE(SUM(c.standalone_sales_supplements_supplement_na_amount), 0) AS standalone_supplements,
        COALESCE(SUM(c.standalone_sales_skincare_product_amount), 0) AS standalone_skincare,
        COALESCE(SUM(c.standalone_sales_other_product_amount), 0) +
        COALESCE(SUM(c.standalone_sales_others_commissionable), 0) +
        COALESCE(SUM(c.standalone_sales_others_non_commissionable), 0) AS standalone_other_products,
        COALESCE(SUM(c.standalone_sales_subtotal), 0) AS standalone_sales_total,
        
        -- Package sales (pre-split columns)
        COALESCE(SUM(c.package_sales_services), 0) AS package_services,
        COALESCE(SUM(c.package_sales_medications), 0) AS package_medications,
        COALESCE(SUM(c.package_sales_supplements_supplement_rm5_amount), 0) +
        COALESCE(SUM(c.package_sales_supplements_supplement_na_amount), 0) AS package_supplements,
        COALESCE(SUM(c.package_sales_skincare_product_amount), 0) AS package_skincare,
        COALESCE(SUM(c.package_sales_other_product_amount), 0) AS package_other_products,
        COALESCE(SUM(c.package_sales_subtotal), 0) AS package_sales_total,
        
        -- Combined sales
        COALESCE(SUM(c.standalone_package_sales), 0) AS combined_sales,
        
        -- Financial metrics
        COALESCE(SUM(c.amount_collected), 0) AS total_collected,
        COALESCE(SUM(c.patient_outstanding_amount), 0) AS total_outstanding,
        COALESCE(SUM(c.discount), 0) AS total_discount,
        COALESCE(SUM(c.tax_amount), 0) AS total_tax
        
    FROM dk.collection c
    WHERE c.date IS NOT NULL
    GROUP BY c.date, c.branch
)
SELECT 
    transaction_date,
    branch,
    
    -- Time dimensions
    EXTRACT(YEAR FROM transaction_date)::INTEGER AS transaction_year,
    EXTRACT(MONTH FROM transaction_date)::INTEGER AS transaction_month,
    EXTRACT(QUARTER FROM transaction_date)::INTEGER AS transaction_quarter,
    EXTRACT(WEEK FROM transaction_date)::INTEGER AS transaction_week,
    EXTRACT(DOW FROM transaction_date)::INTEGER AS day_of_week,
    EXTRACT(DOY FROM transaction_date)::INTEGER AS day_of_year,
    TO_CHAR(transaction_date, 'YYYY-MM') AS year_month,
    TO_CHAR(transaction_date, 'YYYY-"W"WW') AS year_week,
    TO_CHAR(transaction_date, 'Day') AS day_name,
    
    -- Transaction metrics
    total_transactions,
    unique_patients,
    unique_orders,
    
    -- Standalone sales breakdown
    standalone_consultations,
    standalone_services,
    standalone_medications,
    standalone_supplements,
    standalone_skincare,
    standalone_other_products,
    standalone_sales_total,
    
    -- Package sales breakdown
    package_services,
    package_medications,
    package_supplements,
    package_skincare,
    package_other_products,
    package_sales_total,
    
    -- Total revenue
    standalone_sales_total + package_sales_total AS total_revenue,
    combined_sales,
    
    -- Sales mix percentages
    CASE 
        WHEN (standalone_sales_total + package_sales_total) > 0 THEN
            ROUND((standalone_sales_total / (standalone_sales_total + package_sales_total) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS standalone_pct,
    
    CASE 
        WHEN (standalone_sales_total + package_sales_total) > 0 THEN
            ROUND((package_sales_total / (standalone_sales_total + package_sales_total) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS package_pct,
    
    -- Financial metrics
    total_collected,
    total_outstanding,
    total_discount,
    total_tax,
    
    -- Collection efficiency
    CASE 
        WHEN (standalone_sales_total + package_sales_total) > 0 THEN
            ROUND((total_collected / (standalone_sales_total + package_sales_total) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS collection_rate_pct,
    
    -- Discount rate
    CASE 
        WHEN (standalone_sales_total + package_sales_total) > 0 THEN
            ROUND((total_discount / (standalone_sales_total + package_sales_total) * 100)::NUMERIC, 2)
        ELSE 0 
    END AS discount_rate_pct,
    
    -- Average transaction value
    CASE 
        WHEN total_transactions > 0 THEN
            ROUND(((standalone_sales_total + package_sales_total) / total_transactions)::NUMERIC, 2)
        ELSE 0 
    END AS avg_transaction_value,
    
    -- Average patient value
    CASE 
        WHEN unique_patients > 0 THEN
            ROUND(((standalone_sales_total + package_sales_total) / unique_patients)::NUMERIC, 2)
        ELSE 0 
    END AS avg_patient_value,
    
    -- Weekend indicator
    CASE WHEN EXTRACT(DOW FROM transaction_date) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend,
    
    -- Weekday indicator  
    CASE WHEN EXTRACT(DOW FROM transaction_date) BETWEEN 1 AND 5 THEN TRUE ELSE FALSE END AS is_weekday

FROM daily_agg
ORDER BY transaction_date, branch;

COMMENT ON VIEW dk.vw_daily_sales_summary IS 'Daily sales summary using pre-split revenue columns from dk.collection.';

-- ============================================================================
-- SECTION 2: Branch Performance View
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_branch_performance AS
WITH monthly_branch AS (
    SELECT 
        branch,
        DATE_TRUNC('month', transaction_date)::date AS month_start,
        TO_CHAR(transaction_date, 'YYYY-MM') AS year_month,
        EXTRACT(YEAR FROM transaction_date)::INTEGER AS year,
        EXTRACT(MONTH FROM transaction_date)::INTEGER AS month,
        
        SUM(total_revenue) AS monthly_revenue,
        SUM(total_transactions) AS monthly_transactions,
        SUM(unique_patients) AS monthly_patients,
        SUM(total_collected) AS monthly_collected,
        SUM(total_discount) AS monthly_discount,
        SUM(standalone_sales_total) AS monthly_standalone,
        SUM(package_sales_total) AS monthly_package,
        AVG(avg_transaction_value) AS avg_txn_value
        
    FROM dk.vw_daily_sales_summary
    GROUP BY branch, DATE_TRUNC('month', transaction_date)::date, 
             TO_CHAR(transaction_date, 'YYYY-MM'),
             EXTRACT(YEAR FROM transaction_date)::INTEGER,
             EXTRACT(MONTH FROM transaction_date)::INTEGER
),
with_prior AS (
    SELECT 
        *,
        LAG(monthly_revenue, 1) OVER (PARTITION BY branch ORDER BY month_start) AS prior_month_revenue,
        LAG(monthly_transactions, 1) OVER (PARTITION BY branch ORDER BY month_start) AS prior_month_transactions,
        LAG(monthly_patients, 1) OVER (PARTITION BY branch ORDER BY month_start) AS prior_month_patients,
        LAG(monthly_revenue, 12) OVER (PARTITION BY branch ORDER BY month_start) AS prior_year_revenue,
        SUM(monthly_revenue) OVER (PARTITION BY branch, year ORDER BY month_start ROWS UNBOUNDED PRECEDING) AS ytd_revenue,
        SUM(monthly_transactions) OVER (PARTITION BY branch, year ORDER BY month_start ROWS UNBOUNDED PRECEDING) AS ytd_transactions,
        SUM(monthly_patients) OVER (PARTITION BY branch, year ORDER BY month_start ROWS UNBOUNDED PRECEDING) AS ytd_patients
    FROM monthly_branch
)
SELECT 
    branch,
    month_start,
    year_month,
    year,
    month,
    monthly_revenue,
    monthly_transactions,
    monthly_patients,
    monthly_collected,
    monthly_discount,
    monthly_standalone,
    monthly_package,
    avg_txn_value,
    prior_month_revenue,
    prior_month_transactions,
    prior_month_patients,
    CASE WHEN prior_month_revenue > 0 THEN ROUND(((monthly_revenue - prior_month_revenue) / prior_month_revenue * 100)::NUMERIC, 2) ELSE NULL END AS mom_revenue_growth_pct,
    CASE WHEN prior_month_transactions > 0 THEN ROUND(((monthly_transactions - prior_month_transactions) / prior_month_transactions * 100)::NUMERIC, 2) ELSE NULL END AS mom_transaction_growth_pct,
    CASE WHEN prior_month_patients > 0 THEN ROUND(((monthly_patients - prior_month_patients) / prior_month_patients * 100)::NUMERIC, 2) ELSE NULL END AS mom_patient_growth_pct,
    prior_year_revenue,
    CASE WHEN prior_year_revenue > 0 THEN ROUND(((monthly_revenue - prior_year_revenue) / prior_year_revenue * 100)::NUMERIC, 2) ELSE NULL END AS yoy_revenue_growth_pct,
    ytd_revenue,
    ytd_transactions,
    ytd_patients,
    CASE WHEN (monthly_standalone + monthly_package) > 0 THEN ROUND((monthly_standalone / (monthly_standalone + monthly_package) * 100)::NUMERIC, 2) ELSE 0 END AS standalone_mix_pct,
    CASE WHEN (monthly_standalone + monthly_package) > 0 THEN ROUND((monthly_package / (monthly_standalone + monthly_package) * 100)::NUMERIC, 2) ELSE 0 END AS package_mix_pct,
    CASE WHEN monthly_revenue > 0 THEN ROUND((monthly_discount / monthly_revenue * 100)::NUMERIC, 2) ELSE 0 END AS discount_rate_pct,
    RANK() OVER (PARTITION BY year_month ORDER BY monthly_revenue DESC) AS revenue_rank,
    RANK() OVER (PARTITION BY year_month ORDER BY monthly_transactions DESC) AS transaction_rank,
    RANK() OVER (PARTITION BY year_month ORDER BY monthly_patients DESC) AS patient_rank,
    CASE 
        WHEN monthly_revenue >= 100000 THEN 'Tier 1 - High'
        WHEN monthly_revenue >= 50000 THEN 'Tier 2 - Medium'
        WHEN monthly_revenue >= 20000 THEN 'Tier 3 - Low'
        ELSE 'Tier 4 - Minimal'
    END AS performance_tier,
    CASE 
        WHEN prior_month_revenue IS NOT NULL AND (monthly_revenue - prior_month_revenue) / prior_month_revenue >= 0.1 THEN 'Growing'
        WHEN prior_month_revenue IS NOT NULL AND (monthly_revenue - prior_month_revenue) / prior_month_revenue <= -0.1 THEN 'Declining'
        WHEN prior_month_revenue IS NOT NULL THEN 'Stable'
        ELSE 'New'
    END AS growth_status
FROM with_prior
ORDER BY month_start DESC, monthly_revenue DESC;

COMMENT ON VIEW dk.vw_branch_performance IS 'Branch performance with MoM/YoY growth using actual dk.collection schema.';

-- ============================================================================
-- SECTION 3: Product Performance View
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_product_performance AS
WITH category_sales AS (
    SELECT 
        branch,
        DATE_TRUNC('month', transaction_date)::date AS month_start,
        TO_CHAR(transaction_date, 'YYYY-MM') AS year_month,
        EXTRACT(YEAR FROM transaction_date)::INTEGER AS year,
        EXTRACT(MONTH FROM transaction_date)::INTEGER AS month,
        SUM(standalone_consultations) AS consultations_revenue,
        SUM(standalone_services + package_services) AS services_revenue,
        SUM(standalone_services) AS standalone_services,
        SUM(package_services) AS package_services,
        SUM(standalone_medications + package_medications) AS medications_revenue,
        SUM(standalone_medications) AS standalone_medications,
        SUM(package_medications) AS package_medications,
        SUM(standalone_supplements + package_supplements) AS supplements_revenue,
        SUM(standalone_supplements) AS standalone_supplements,
        SUM(package_supplements) AS package_supplements,
        SUM(standalone_skincare + package_skincare) AS skincare_revenue,
        SUM(standalone_skincare) AS standalone_skincare,
        SUM(package_skincare) AS package_skincare,
        SUM(standalone_other_products + package_other_products) AS other_products_revenue,
        SUM(standalone_other_products) AS standalone_other_products,
        SUM(package_other_products) AS package_other_products,
        SUM(total_revenue) AS total_revenue,
        SUM(total_transactions) AS total_transactions,
        SUM(unique_patients) AS unique_patients
    FROM dk.vw_daily_sales_summary
    GROUP BY branch, DATE_TRUNC('month', transaction_date)::date,
             TO_CHAR(transaction_date, 'YYYY-MM'),
             EXTRACT(YEAR FROM transaction_date)::INTEGER,
             EXTRACT(MONTH FROM transaction_date)::INTEGER
)
SELECT 
    branch,
    month_start,
    year_month,
    year,
    month,
    consultations_revenue,
    services_revenue,
    medications_revenue,
    supplements_revenue,
    skincare_revenue,
    other_products_revenue,
    standalone_services,
    package_services,
    standalone_medications,
    package_medications,
    standalone_supplements,
    package_supplements,
    standalone_skincare,
    package_skincare,
    standalone_other_products,
    package_other_products,
    total_revenue,
    total_transactions,
    unique_patients,
    CASE WHEN total_revenue > 0 THEN ROUND((consultations_revenue / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS consultations_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((services_revenue / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS services_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((medications_revenue / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS medications_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((supplements_revenue / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS supplements_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((skincare_revenue / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS skincare_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((other_products_revenue / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS other_products_pct,
    CASE 
        WHEN consultations_revenue >= services_revenue AND consultations_revenue >= medications_revenue AND
             consultations_revenue >= supplements_revenue AND consultations_revenue >= skincare_revenue THEN 'Consultations'
        WHEN services_revenue >= medications_revenue AND services_revenue >= supplements_revenue AND services_revenue >= skincare_revenue THEN 'Services'
        WHEN medications_revenue >= supplements_revenue AND medications_revenue >= skincare_revenue THEN 'Medications'
        WHEN supplements_revenue >= skincare_revenue THEN 'Supplements'
        WHEN skincare_revenue >= other_products_revenue THEN 'Skincare'
        ELSE 'Other Products'
    END AS top_category,
    CASE WHEN unique_patients > 0 THEN ROUND((total_revenue / unique_patients)::NUMERIC, 2) ELSE 0 END AS revenue_per_patient,
    CASE WHEN unique_patients > 0 THEN ROUND((skincare_revenue / unique_patients)::NUMERIC, 2) ELSE 0 END AS skincare_per_patient,
    CASE WHEN unique_patients > 0 THEN ROUND((services_revenue / unique_patients)::NUMERIC, 2) ELSE 0 END AS services_per_patient,
    CASE WHEN total_transactions > 0 THEN ROUND((total_revenue / total_transactions)::NUMERIC, 2) ELSE 0 END AS revenue_per_transaction,
    RANK() OVER (PARTITION BY branch, year_month ORDER BY services_revenue DESC) AS services_rank,
    RANK() OVER (PARTITION BY branch, year_month ORDER BY skincare_revenue DESC) AS skincare_rank,
    RANK() OVER (PARTITION BY branch, year_month ORDER BY supplements_revenue DESC) AS supplements_rank
FROM category_sales
ORDER BY month_start DESC, branch, total_revenue DESC;

COMMENT ON VIEW dk.vw_product_performance IS 'Product/category performance using pre-split revenue columns from dk.collection.';

-- ============================================================================
-- SECTION 4: Monthly Sales Trend View
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_monthly_sales_trend AS
WITH monthly_totals AS (
    SELECT 
        DATE_TRUNC('month', transaction_date)::date AS month_start,
        TO_CHAR(transaction_date, 'YYYY-MM') AS year_month,
        EXTRACT(YEAR FROM transaction_date)::INTEGER AS year,
        EXTRACT(MONTH FROM transaction_date)::INTEGER AS month,
        SUM(total_revenue) AS total_revenue,
        SUM(total_transactions) AS total_transactions,
        SUM(unique_patients) AS total_patients,
        SUM(standalone_sales_total) AS standalone_total,
        SUM(package_sales_total) AS package_total,
        SUM(total_collected) AS total_collected,
        SUM(total_discount) AS total_discount,
        SUM(total_tax) AS total_tax,
        SUM(standalone_consultations) AS consultations,
        SUM(standalone_services + package_services) AS services,
        SUM(standalone_medications + package_medications) AS medications,
        SUM(standalone_supplements + package_supplements) AS supplements,
        SUM(standalone_skincare + package_skincare) AS skincare,
        SUM(standalone_other_products + package_other_products) AS other_products,
        COUNT(DISTINCT branch) AS active_branches
    FROM dk.vw_daily_sales_summary
    GROUP BY DATE_TRUNC('month', transaction_date)::date,
             TO_CHAR(transaction_date, 'YYYY-MM'),
             EXTRACT(YEAR FROM transaction_date)::INTEGER,
             EXTRACT(MONTH FROM transaction_date)::INTEGER
),
with_lags AS (
    SELECT 
        *,
        LAG(total_revenue, 1) OVER (ORDER BY month_start) AS prior_month_revenue,
        LAG(total_revenue, 12) OVER (ORDER BY month_start) AS prior_year_revenue,
        LAG(total_patients, 1) OVER (ORDER BY month_start) AS prior_month_patients,
        SUM(total_revenue) OVER (PARTITION BY year ORDER BY month_start ROWS UNBOUNDED PRECEDING) AS ytd_revenue,
        AVG(total_revenue) OVER (ORDER BY month_start ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS moving_avg_3m,
        AVG(total_revenue) OVER (ORDER BY month_start ROWS BETWEEN 5 PRECEDING AND CURRENT ROW) AS moving_avg_6m
    FROM monthly_totals
)
SELECT 
    month_start,
    year_month,
    year,
    month,
    total_revenue,
    total_transactions,
    total_patients,
    standalone_total,
    package_total,
    total_collected,
    total_discount,
    total_tax,
    active_branches,
    consultations,
    services,
    medications,
    supplements,
    skincare,
    other_products,
    CASE WHEN total_revenue > 0 THEN ROUND((standalone_total / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS standalone_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((package_total / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS package_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((services / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS services_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((skincare / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS skincare_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((supplements / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS supplements_pct,
    CASE WHEN total_revenue > 0 THEN ROUND((medications / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS medications_pct,
    prior_month_revenue,
    CASE WHEN prior_month_revenue > 0 THEN ROUND(((total_revenue - prior_month_revenue) / prior_month_revenue * 100)::NUMERIC, 2) ELSE NULL END AS mom_growth_pct,
    prior_year_revenue,
    CASE WHEN prior_year_revenue > 0 THEN ROUND(((total_revenue - prior_year_revenue) / prior_year_revenue * 100)::NUMERIC, 2) ELSE NULL END AS yoy_growth_pct,
    prior_month_patients,
    CASE WHEN prior_month_patients > 0 THEN ROUND(((total_patients - prior_month_patients) / prior_month_patients * 100)::NUMERIC, 2) ELSE NULL END AS patient_growth_pct,
    ytd_revenue,
    ROUND(moving_avg_3m::NUMERIC, 2) AS moving_avg_3m,
    ROUND(moving_avg_6m::NUMERIC, 2) AS moving_avg_6m,
    CASE 
        WHEN total_revenue > moving_avg_3m * 1.1 THEN 'Above Trend'
        WHEN total_revenue < moving_avg_3m * 0.9 THEN 'Below Trend'
        ELSE 'On Trend'
    END AS trend_status,
    CASE WHEN total_revenue > 0 THEN ROUND((total_discount / total_revenue * 100)::NUMERIC, 2) ELSE 0 END AS discount_rate_pct,
    CASE WHEN total_transactions > 0 THEN ROUND((total_revenue / total_transactions)::NUMERIC, 2) ELSE 0 END AS avg_transaction_value,
    CASE WHEN total_patients > 0 THEN ROUND((total_revenue / total_patients)::NUMERIC, 2) ELSE 0 END AS avg_patient_value,
    CASE WHEN active_branches > 0 THEN ROUND((total_revenue / active_branches)::NUMERIC, 2) ELSE 0 END AS revenue_per_branch
FROM with_lags
ORDER BY month_start;

COMMENT ON VIEW dk.vw_monthly_sales_trend IS 'Monthly sales trend with MoM/YoY growth using actual dk.collection schema.';

-- ============================================================================
-- SECTION 5: Grant Permissions
-- ============================================================================

GRANT SELECT ON dk.vw_daily_sales_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_branch_performance TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_product_performance TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_monthly_sales_trend TO healthcare_bi_reader;

GRANT SELECT ON dk.vw_daily_sales_summary TO healthcare_bi_app;
GRANT SELECT ON dk.vw_branch_performance TO healthcare_bi_app;
GRANT SELECT ON dk.vw_product_performance TO healthcare_bi_app;
GRANT SELECT ON dk.vw_monthly_sales_trend TO healthcare_bi_app;