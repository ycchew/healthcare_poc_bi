-- ============================================================================
-- ST-02: Sales & Revenue Analytics
-- File: 03_materialized_views.sql
-- Description: Materialized views for sales analytics with proper indexes
-- Schema: dk
-- Dependencies: dk.vw_daily_sales_summary, dk.vw_branch_performance, etc.
-- Constraints from ST-01:
--   - All objects in schema: dk
--   - Use UNIQUE indexes for CONCURRENT refresh
--   - Follow naming convention: mvw_*
-- ============================================================================

-- ============================================================================
-- SECTION 1: Create Materialized Views
-- ============================================================================

-- Materialized View: Daily Sales Summary
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_daily_sales_summary CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_daily_sales_summary AS
SELECT * FROM dk.vw_daily_sales_summary;

CREATE UNIQUE INDEX idx_mvw_daily_sales_date_branch ON dk.mvw_daily_sales_summary (transaction_date, branch);
CREATE INDEX idx_mvw_daily_sales_date ON dk.mvw_daily_sales_summary (transaction_date);
CREATE INDEX idx_mvw_daily_sales_branch ON dk.mvw_daily_sales_summary (branch);
CREATE INDEX idx_mvw_daily_sales_yearmonth ON dk.mvw_daily_sales_summary (year_month);

COMMENT ON MATERIALIZED VIEW dk.mvw_daily_sales_summary IS 'Materialized view of daily sales summary. Refresh: Daily at 1:00 AM via dk.refresh_all_mvws()';

-- Materialized View: Branch Performance
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_branch_performance CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_branch_performance AS
SELECT * FROM dk.vw_branch_performance;

CREATE UNIQUE INDEX idx_mvw_branch_perf_month_branch ON dk.mvw_branch_performance (month_start, branch);
CREATE INDEX idx_mvw_branch_perf_branch ON dk.mvw_branch_performance (branch);
CREATE INDEX idx_mvw_branch_perf_yearmonth ON dk.mvw_branch_performance (year_month);
CREATE INDEX idx_mvw_branch_perf_revenue ON dk.mvw_branch_performance (monthly_revenue DESC);
CREATE INDEX idx_mvw_branch_perf_rank ON dk.mvw_branch_performance (year_month, revenue_rank);

COMMENT ON MATERIALIZED VIEW dk.mvw_branch_performance IS 'Materialized view of branch performance with MoM/YoY growth. Refresh: Daily at 1:00 AM';

-- Materialized View: Product Performance
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_product_performance CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_product_performance AS
SELECT * FROM dk.vw_product_performance;

CREATE UNIQUE INDEX idx_mvw_prod_perf_month_branch ON dk.mvw_product_performance (month_start, branch);
CREATE INDEX idx_mvw_prod_perf_branch ON dk.mvw_product_performance (branch);
CREATE INDEX idx_mvw_prod_perf_yearmonth ON dk.mvw_product_performance (year_month);
CREATE INDEX idx_mvw_prod_perf_skincare ON dk.mvw_product_performance (month_start, skincare_revenue DESC);

COMMENT ON MATERIALIZED VIEW dk.mvw_product_performance IS 'Materialized view of product/category performance. Refresh: Daily at 1:00 AM';

-- Materialized View: Monthly Sales Trend
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_monthly_sales_trend CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_monthly_sales_trend AS
SELECT * FROM dk.vw_monthly_sales_trend;

CREATE UNIQUE INDEX idx_mvw_monthly_trend_month ON dk.mvw_monthly_sales_trend (month_start);
CREATE INDEX idx_mvw_monthly_trend_yearmonth ON dk.mvw_monthly_sales_trend (year_month);
CREATE INDEX idx_mvw_monthly_trend_revenue ON dk.mvw_monthly_sales_trend (total_revenue DESC);

COMMENT ON MATERIALIZED VIEW dk.mvw_monthly_sales_trend IS 'Materialized view of monthly sales trend. Refresh: Daily at 1:00 AM';

-- Materialized View: Calendar Effects (Festival-based)
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_calendar_effects CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_calendar_effects AS
SELECT * FROM dk.vw_festival_calendar_effects;

CREATE UNIQUE INDEX idx_mvw_calendar_date_branch ON dk.mvw_calendar_effects (transaction_date, branch);
CREATE INDEX idx_mvw_calendar_festival ON dk.mvw_calendar_effects (festival_group);
CREATE INDEX idx_mvw_calendar_period ON dk.mvw_calendar_effects (period_type);
CREATE INDEX idx_mvw_calendar_yearmonth ON dk.mvw_calendar_effects (year_month);

COMMENT ON MATERIALIZED VIEW dk.mvw_calendar_effects IS 'Materialized view of calendar effects with festival classification. Refresh: Daily at 1:00 AM';

-- Materialized View: Promotion Impact
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_promotion_impact CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_promotion_impact AS
SELECT * FROM dk.vw_promotion_impact;

CREATE UNIQUE INDEX idx_mvw_promo_date_branch ON dk.mvw_promotion_impact (transaction_date, branch);
CREATE INDEX idx_mvw_promo_branch ON dk.mvw_promotion_impact (branch);
CREATE INDEX idx_mvw_promo_promotional ON dk.mvw_promotion_impact (is_promotional) WHERE is_promotional = TRUE;
CREATE INDEX idx_mvw_promo_effectiveness ON dk.mvw_promotion_impact (promotion_effectiveness);

COMMENT ON MATERIALIZED VIEW dk.mvw_promotion_impact IS 'Materialized view of promotion impact analysis. Refresh: Daily at 1:00 AM';

-- Materialized View: DOW Heatmap
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_dow_heatmap CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_dow_heatmap AS
SELECT * FROM dk.vw_dow_heatmap;

CREATE UNIQUE INDEX idx_mvw_dow_branch_day ON dk.mvw_dow_heatmap (branch, day_of_week);
CREATE INDEX idx_mvw_dow_branch ON dk.mvw_dow_heatmap (branch);
CREATE INDEX idx_mvw_dow_day ON dk.mvw_dow_heatmap (day_of_week);

COMMENT ON MATERIALIZED VIEW dk.mvw_dow_heatmap IS 'Materialized view of day-of-week heatmap. Refresh: Daily at 1:00 AM';

-- ============================================================================
-- SECTION 2: Create Sales Forecast Table (for Prophet predictions)
-- Description: Table to store Prophet 90-day forecasts per branch
-- ============================================================================

DROP TABLE IF EXISTS dk.sales_forecast CASCADE;
CREATE TABLE dk.sales_forecast (
    forecast_id SERIAL PRIMARY KEY,
    branch VARCHAR(100) NOT NULL,
    forecast_date DATE NOT NULL,
    
    -- Prophet predictions
    yhat NUMERIC(12, 2) NOT NULL,        -- Point forecast
    yhat_lower NUMERIC(12, 2) NOT NULL,  -- Lower bound
    yhat_upper NUMERIC(12, 2) NOT NULL,  -- Upper bound
    
    -- Forecast metadata
    forecast_horizon INTEGER NOT NULL,   -- Days ahead (1-90)
    model_version VARCHAR(50),           -- Model version identifier
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT uq_forecast_branch UNIQUE (branch, forecast_date)
);

-- Indexes
CREATE INDEX idx_sales_forecast_branch ON dk.sales_forecast (branch);
CREATE INDEX idx_sales_forecast_date ON dk.sales_forecast (forecast_date);
CREATE INDEX idx_sales_forecast_horizon ON dk.sales_forecast (forecast_horizon);

COMMENT ON TABLE dk.sales_forecast IS 'Prophet 90-day sales forecasts per branch. Updated daily by Python forecast script.';

-- ============================================================================
-- SECTION 3: Create Forecast Accuracy Tracking Table
-- Description: Track forecast accuracy over time
-- ============================================================================

DROP TABLE IF EXISTS dk.forecast_accuracy CASCADE;
CREATE TABLE dk.forecast_accuracy (
    accuracy_id SERIAL PRIMARY KEY,
    branch VARCHAR(100) NOT NULL,
    forecast_date DATE NOT NULL,
    actual_date DATE NOT NULL,
    
    -- Values
    predicted_value NUMERIC(12, 2) NOT NULL,
    actual_value NUMERIC(12, 2),
    
    -- Error metrics
    absolute_error NUMERIC(12, 2),
    pct_error NUMERIC(8, 4),
    
    -- Metadata
    forecast_horizon INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_forecast_accuracy_branch ON dk.forecast_accuracy (branch);
CREATE INDEX idx_forecast_accuracy_date ON dk.forecast_accuracy (forecast_date);

COMMENT ON TABLE dk.forecast_accuracy IS 'Forecast accuracy tracking for model evaluation.';

-- ============================================================================
-- SECTION 4: Create Refresh Function for ST-02 MVWs
-- Description: Refresh only ST-02 materialized views
-- ============================================================================

CREATE OR REPLACE FUNCTION dk.refresh_sales_mvws()
RETURNS TABLE(mvw_name TEXT, status TEXT, duration_ms NUMERIC) AS $$
DECLARE
    start_time TIMESTAMP;
    mvw_record RECORD;
    st02_mvws TEXT[] := ARRAY[
        'mvw_daily_sales_summary',
        'mvw_branch_performance',
        'mvw_product_performance',
        'mvw_monthly_sales_trend',
        'mvw_calendar_effects',
        'mvw_promotion_impact',
        'mvw_dow_heatmap'
    ];
BEGIN
    FOREACH mvw_name IN ARRAY st02_mvws
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

COMMENT ON FUNCTION dk.refresh_sales_mvws() IS 'Refreshes all ST-02 sales analytics materialized views. Returns status for each view.';

-- ============================================================================
-- SECTION 5: Grant Permissions
-- ============================================================================

-- Grant select on materialized views
GRANT SELECT ON dk.mvw_daily_sales_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_branch_performance TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_product_performance TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_monthly_sales_trend TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_calendar_effects TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_promotion_impact TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_dow_heatmap TO healthcare_bi_reader;

GRANT SELECT ON dk.mvw_daily_sales_summary TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_branch_performance TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_product_performance TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_monthly_sales_trend TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_calendar_effects TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_promotion_impact TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_dow_heatmap TO healthcare_bi_app;

-- Grant on forecast tables
GRANT SELECT ON dk.sales_forecast TO healthcare_bi_reader;
GRANT SELECT ON dk.forecast_accuracy TO healthcare_bi_reader;

GRANT SELECT, INSERT, UPDATE ON dk.sales_forecast TO healthcare_bi_app;
GRANT SELECT, INSERT, UPDATE ON dk.forecast_accuracy TO healthcare_bi_app;

-- ============================================================================
-- END OF FILE
-- ============================================================================