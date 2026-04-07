-- ============================================================================
-- ST-02: Sales & Revenue Analytics
-- File: 02_calendar_effects_views.sql
-- Description: Calendar effect analysis with Malaysian festivals and promotion detection
-- Schema: dk
-- Dependencies: dk.vw_daily_sales_summary, dk.collection
-- ============================================================================

-- ============================================================================
-- SECTION 1: Malaysian Holidays Reference Table
-- Description: Configurable Malaysian festival dates with pre/during/post windows
-- ============================================================================

-- Create table for Malaysian holidays (configurable, not hard-coded)
DROP TABLE IF EXISTS dk.malaysian_holidays CASCADE;
CREATE TABLE dk.malaysian_holidays (
    holiday_id SERIAL PRIMARY KEY,
    holiday_name VARCHAR(100) NOT NULL,
    holiday_date DATE NOT NULL,
    holiday_type VARCHAR(50) NOT NULL,  -- 'National', 'State', 'School'
    festival_group VARCHAR(50) NOT NULL, -- 'Hari Raya', 'CNY', 'Deepavali', 'Christmas', etc.
    pre_window_days INTEGER DEFAULT 7,
    post_window_days INTEGER DEFAULT 7,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_holiday_date ON dk.malaysian_holidays (holiday_date);
CREATE INDEX idx_holiday_festival ON dk.malaysian_holidays (festival_group);
CREATE INDEX idx_holiday_active ON dk.malaysian_holidays (is_active) WHERE is_active = TRUE;

COMMENT ON TABLE dk.malaysian_holidays IS 'Malaysian holiday reference table with configurable festival windows. Values should be updated annually.';

-- Insert sample holidays (2024-2026) - These should be updated annually
INSERT INTO dk.malaysian_holidays (holiday_name, holiday_date, holiday_type, festival_group, pre_window_days, post_window_days) VALUES
-- Chinese New Year
('Chinese New Year 2024', '2024-02-10', 'National', 'CNY', 14, 7),
('Chinese New Year 2025', '2025-01-29', 'National', 'CNY', 14, 7),
('Chinese New Year 2026', '2026-02-17', 'National', 'CNY', 14, 7),

-- Hari Raya Aidilfitri
('Hari Raya Aidilfitri 2024', '2024-04-10', 'National', 'Hari Raya', 14, 7),
('Hari Raya Aidilfitri 2025', '2025-03-30', 'National', 'Hari Raya', 14, 7),
('Hari Raya Aidilfitri 2026', '2026-03-20', 'National', 'Hari Raya', 14, 7),

-- Deepavali
('Deepavali 2024', '2024-10-31', 'National', 'Deepavali', 7, 7),
('Deepavali 2025', '2025-10-20', 'National', 'Deepavali', 7, 7),
('Deepavali 2026', '2026-11-08', 'National', 'Deepavali', 7, 7),

-- Christmas
('Christmas 2024', '2024-12-25', 'National', 'Christmas', 14, 7),
('Christmas 2025', '2025-12-25', 'National', 'Christmas', 14, 7),
('Christmas 2026', '2026-12-25', 'National', 'Christmas', 14, 7),

-- Hari Raya Haji
('Hari Raya Haji 2024', '2024-06-17', 'National', 'Hari Raya Haji', 7, 3),
('Hari Raya Haji 2025', '2025-06-06', 'National', 'Hari Raya Haji', 7, 3),

-- Merdeka Day
('Merdeka Day 2024', '2024-08-31', 'National', 'Merdeka', 3, 1),
('Merdeka Day 2025', '2025-08-31', 'National', 'Merdeka', 3, 1),
('Merdeka Day 2026', '2026-08-31', 'National', 'Merdeka', 3, 1),

-- Malaysia Day
('Malaysia Day 2024', '2024-09-16', 'National', 'Malaysia Day', 3, 1),
('Malaysia Day 2025', '2025-09-16', 'National', 'Malaysia Day', 3, 1),
('Malaysia Day 2026', '2026-09-16', 'National', 'Malaysia Day', 3, 1);

DROP VIEW IF EXISTS dk.vw_festival_calendar_effects CASCADE;
DROP VIEW IF EXISTS dk.vw_festival_performance CASCADE;
DROP VIEW IF EXISTS dk.vw_promotion_impact CASCADE;
DROP VIEW IF EXISTS dk.vw_dow_heatmap CASCADE;

-- ============================================================================
-- SECTION 2: Calendar Effects View
-- Description: Daily sales with holiday/festival period classification
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_festival_calendar_effects AS
WITH daily_base AS (
    SELECT 
        d.transaction_date,
        d.branch,
        d.total_revenue,
        d.total_transactions,
        d.unique_patients,
        d.avg_transaction_value,
        d.discount_rate_pct,
        d.is_weekend,
        d.is_weekday,
        d.day_of_week,
        d.transaction_year AS year,
        d.transaction_month AS month,
        d.year_month
        
    FROM dk.vw_daily_sales_summary d
),
holiday_classified AS (
    SELECT 
        db.*,
        h.holiday_name,
        h.festival_group,
        h.holiday_date,
        
        -- Calculate days from holiday
        db.transaction_date - h.holiday_date AS days_from_holiday,
        
        -- Classify period type
        CASE 
            WHEN db.transaction_date = h.holiday_date THEN 'During'
            WHEN db.transaction_date > h.holiday_date AND 
                 db.transaction_date <= h.holiday_date + h.post_window_days THEN 'Post'
            WHEN db.transaction_date < h.holiday_date AND 
                 db.transaction_date >= h.holiday_date - h.pre_window_days THEN 'Pre'
            ELSE NULL
        END AS period_type,
        
        -- Window boundaries
        h.pre_window_days,
        h.post_window_days
        
    FROM daily_base db
    LEFT JOIN dk.malaysian_holidays h ON 
        db.transaction_date BETWEEN (h.holiday_date - h.pre_window_days) 
        AND (h.holiday_date + h.post_window_days)
        AND h.is_active = TRUE
),
baseline AS (
    SELECT 
        branch,
        day_of_week,
        AVG(total_revenue) AS baseline_revenue,
        AVG(total_transactions) AS baseline_transactions,
        AVG(unique_patients) AS baseline_patients
    FROM daily_base
    GROUP BY branch, day_of_week
)
SELECT 
    hc.transaction_date,
    hc.branch,
    hc.year,
    hc.month,
    hc.year_month,
    hc.day_of_week,
    hc.is_weekend,
    hc.is_weekday,
    
    -- Sales metrics
    hc.total_revenue,
    hc.total_transactions,
    hc.unique_patients,
    hc.avg_transaction_value,
    hc.discount_rate_pct,
    
    -- Holiday info
    hc.holiday_name,
    hc.festival_group,
    hc.holiday_date,
    hc.days_from_holiday,
    hc.period_type,
    
    -- Period classification (multiple holidays possible)
    COALESCE(hc.period_type, 'Normal') AS sales_period,
    COALESCE(hc.festival_group, 'Regular') AS period_name,
    
    -- Baseline comparison
    bl.baseline_revenue,
    bl.baseline_transactions,
    bl.baseline_patients,
    
    -- Performance vs baseline
    CASE 
        WHEN bl.baseline_revenue > 0 THEN
            ROUND(((hc.total_revenue - bl.baseline_revenue) / bl.baseline_revenue * 100)::NUMERIC, 2)
        ELSE 0
    END AS revenue_vs_baseline_pct,
    
    CASE 
        WHEN bl.baseline_transactions > 0 THEN
            ROUND(((hc.total_transactions - bl.baseline_transactions) / bl.baseline_transactions * 100)::NUMERIC, 2)
        ELSE 0
    END AS transactions_vs_baseline_pct,
    
    -- Lift indicator
    CASE 
        WHEN bl.baseline_revenue > 0 AND hc.total_revenue > bl.baseline_revenue * 1.1 THEN 'Positive Lift'
        WHEN bl.baseline_revenue > 0 AND hc.total_revenue < bl.baseline_revenue * 0.9 THEN 'Negative Impact'
        ELSE 'Normal Range'
    END AS lift_status,
    
    -- Promotion indicator (high discount)
    CASE 
        WHEN hc.discount_rate_pct > 10 THEN 'High Discount'
        WHEN hc.discount_rate_pct > 5 THEN 'Medium Discount'
        ELSE 'Normal Discount'
    END AS discount_level

FROM holiday_classified hc
LEFT JOIN baseline bl ON hc.branch = bl.branch AND hc.day_of_week = bl.day_of_week
ORDER BY hc.transaction_date, hc.branch;

COMMENT ON VIEW dk.vw_festival_calendar_effects IS 'Calendar effects with Malaysian festival classification and baseline comparison. For Power BI Calendar & Promotion Effect page.';

-- ============================================================================
-- SECTION 3: Festival Performance Summary View
-- Description: Aggregated performance by festival and period type
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_festival_performance AS
SELECT 
    festival_group,
    holiday_name,
    holiday_date,
    EXTRACT(YEAR FROM holiday_date)::INTEGER AS holiday_year,
    period_type,
    
    -- Aggregated metrics
    COUNT(DISTINCT transaction_date) AS total_days,
    COUNT(DISTINCT branch) AS active_branches,
    SUM(total_revenue) AS total_revenue,
    SUM(total_transactions) AS total_transactions,
    SUM(unique_patients) AS total_patients,
    
    -- Averages
    ROUND(AVG(total_revenue)::NUMERIC, 2) AS avg_daily_revenue,
    ROUND(AVG(total_transactions)::NUMERIC, 2) AS avg_daily_transactions,
    ROUND(AVG(unique_patients)::NUMERIC, 2) AS avg_daily_patients,
    ROUND(AVG(avg_transaction_value)::NUMERIC, 2) AS avg_transaction_value,
    ROUND(AVG(discount_rate_pct)::NUMERIC, 2) AS avg_discount_rate,
    
    -- Baseline comparison
    ROUND(AVG(baseline_revenue)::NUMERIC, 2) AS avg_baseline_revenue,
    ROUND(AVG(revenue_vs_baseline_pct)::NUMERIC, 2) AS avg_lift_pct,
    
    -- Performance indicators
    SUM(CASE WHEN lift_status = 'Positive Lift' THEN 1 ELSE 0 END) AS positive_lift_days,
    SUM(CASE WHEN lift_status = 'Negative Impact' THEN 1 ELSE 0 END) AS negative_impact_days,
    
    ROUND((SUM(CASE WHEN lift_status = 'Positive Lift' THEN 1 ELSE 0 END)::NUMERIC / 
           NULLIF(COUNT(*), 0) * 100)::NUMERIC, 2) AS positive_lift_pct

FROM dk.vw_festival_calendar_effects
WHERE festival_group IS NOT NULL
GROUP BY festival_group, holiday_name, holiday_date, period_type
ORDER BY holiday_date, period_type;

COMMENT ON VIEW dk.vw_festival_performance IS 'Festival performance summary by period type. For Power BI festival impact analysis.';

-- ============================================================================
-- SECTION 4: Promotion Impact View
-- Description: Detects promotion periods and measures impact
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_promotion_impact AS
WITH daily_with_flags AS (
    SELECT 
        transaction_date,
        branch,
        total_revenue,
        total_transactions,
        unique_patients,
        discount_rate_pct,
        total_discount,
        standalone_sales_total,
        package_sales_total,
        
        -- Promotion flag (configurable threshold, default 10%)
        CASE WHEN discount_rate_pct > 10 THEN TRUE ELSE FALSE END AS is_promotional,
        
        -- Discount tier
        CASE 
            WHEN discount_rate_pct > 20 THEN 'High Discount (>20%)'
            WHEN discount_rate_pct > 10 THEN 'Medium Discount (10-20%)'
            WHEN discount_rate_pct > 5 THEN 'Low Discount (5-10%)'
            ELSE 'No Discount (<5%)'
        END AS discount_tier,
        
        -- Day-of-week baseline
        AVG(total_revenue) OVER (
            PARTITION BY branch, EXTRACT(DOW FROM transaction_date)::INTEGER
        ) AS dow_baseline,
        
        -- 30-day moving average
        AVG(total_revenue) OVER (
            PARTITION BY branch 
            ORDER BY transaction_date 
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS moving_avg_30d,
        
        -- Prior period same branch
        LAG(total_revenue, 7) OVER (PARTITION BY branch ORDER BY transaction_date) AS prior_week_revenue
        
    FROM dk.vw_daily_sales_summary
),
baseline_calc AS (
    SELECT 
        branch,
        AVG(total_revenue) AS branch_baseline,
        STDDEV(total_revenue) AS branch_stddev
    FROM dk.vw_daily_sales_summary
    GROUP BY branch
)
SELECT 
    d.transaction_date,
    d.branch,
    d.total_revenue,
    d.total_transactions,
    d.unique_patients,
    d.discount_rate_pct,
    d.total_discount,
    d.standalone_sales_total,
    d.package_sales_total,
    d.is_promotional,
    d.discount_tier,
    d.prior_week_revenue,
    
    -- Baseline metrics
    b.branch_baseline,
    b.branch_stddev,
    d.dow_baseline,
    d.moving_avg_30d,
    
    -- Lift calculations
    CASE 
        WHEN b.branch_baseline > 0 THEN
            ROUND(((d.total_revenue - b.branch_baseline) / b.branch_baseline * 100)::NUMERIC, 2)
        ELSE 0
    END AS lift_vs_baseline_pct,
    
    CASE 
        WHEN d.moving_avg_30d > 0 THEN
            ROUND(((d.total_revenue - d.moving_avg_30d) / d.moving_avg_30d * 100)::NUMERIC, 2)
        ELSE 0
    END AS lift_vs_moving_avg_pct,
    
    CASE 
        WHEN d.prior_week_revenue > 0 THEN
            ROUND(((d.total_revenue - d.prior_week_revenue) / d.prior_week_revenue * 100)::NUMERIC, 2)
        ELSE 0
    END AS wow_growth_pct,
    
    -- Z-score (how unusual is this day)
    CASE 
        WHEN b.branch_stddev > 0 THEN
            ROUND(((d.total_revenue - b.branch_baseline) / b.branch_stddev)::NUMERIC, 2)
        ELSE 0
    END AS revenue_zscore,
    
    -- Anomaly detection
    CASE 
        WHEN b.branch_stddev > 0 AND 
             ABS((d.total_revenue - b.branch_baseline) / b.branch_stddev) > 2 THEN 'Anomaly'
        ELSE 'Normal'
    END AS anomaly_status,
    
    -- Promotion effectiveness
    CASE 
        WHEN d.is_promotional AND d.total_revenue > b.branch_baseline * 1.1 THEN 'Effective'
        WHEN d.is_promotional AND d.total_revenue < b.branch_baseline * 0.9 THEN 'Ineffective'
        WHEN d.is_promotional THEN 'Neutral'
        ELSE 'N/A'
    END AS promotion_effectiveness,
    
    -- Revenue impact (if promotional)
    CASE 
        WHEN d.is_promotional THEN d.total_revenue - b.branch_baseline
        ELSE 0
    END AS revenue_impact,
    
    -- Sales mix
    CASE 
        WHEN (d.standalone_sales_total + d.package_sales_total) > 0 THEN
            ROUND((d.standalone_sales_total / (d.standalone_sales_total + d.package_sales_total) * 100)::NUMERIC, 2)
        ELSE 0
    END AS standalone_mix_pct

FROM daily_with_flags d
LEFT JOIN baseline_calc b ON d.branch = b.branch
ORDER BY d.transaction_date DESC, d.branch;

COMMENT ON VIEW dk.vw_promotion_impact IS 'Promotion impact analysis with baseline comparison and anomaly detection. For Power BI promotion effectiveness analysis.';

-- ============================================================================
-- SECTION 5: Day-of-Week Heatmap View
-- Description: Day-of-week patterns by branch
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_dow_heatmap AS
WITH dow_stats AS (
    SELECT 
        branch,
        EXTRACT(DOW FROM transaction_date)::INTEGER AS day_of_week,
        TO_CHAR(transaction_date, 'Day') AS day_name,
        
        AVG(total_revenue) AS avg_revenue,
        AVG(total_transactions) AS avg_transactions,
        AVG(unique_patients) AS avg_patients,
        SUM(total_revenue) AS total_revenue,
        SUM(total_transactions) AS total_transactions,
        COUNT(*) AS day_count,
        
        AVG(discount_rate_pct) AS avg_discount_rate
        
    FROM dk.vw_daily_sales_summary
    GROUP BY branch, EXTRACT(DOW FROM transaction_date)::INTEGER, TO_CHAR(transaction_date, 'Day')
)
SELECT 
    branch,
    day_of_week,
    day_name,
    ROUND(avg_revenue::NUMERIC, 2) AS avg_revenue,
    ROUND(avg_transactions::NUMERIC, 2) AS avg_transactions,
    ROUND(avg_patients::NUMERIC, 2) AS avg_patients,
    ROUND(total_revenue::NUMERIC, 2) AS total_revenue,
    total_transactions,
    day_count,
    ROUND(avg_discount_rate::NUMERIC, 2) AS avg_discount_rate,
    
    -- Rank within branch
    RANK() OVER (PARTITION BY branch ORDER BY avg_revenue DESC) AS revenue_rank,
    
    -- Percentage of branch total
    ROUND((avg_revenue / NULLIF(SUM(avg_revenue) OVER (PARTITION BY branch), 0) * 100)::NUMERIC, 2) AS pct_of_branch,
    
    -- Peak indicator
    CASE 
        WHEN day_of_week IN (5, 6, 0) THEN 'Weekend'  -- Friday, Saturday, Sunday
        ELSE 'Weekday'
    END AS day_type,
    
    -- Performance indicator
    CASE 
        WHEN RANK() OVER (PARTITION BY branch ORDER BY avg_revenue DESC) <= 2 THEN 'Peak Day'
        WHEN RANK() OVER (PARTITION BY branch ORDER BY avg_revenue DESC) >= 6 THEN 'Low Day'
        ELSE 'Average Day'
    END AS performance_label

FROM dow_stats
ORDER BY branch, day_of_week;

COMMENT ON VIEW dk.vw_dow_heatmap IS 'Day-of-week performance heatmap by branch. For Power BI heatmap visualization.';

-- ============================================================================
-- SECTION 6: Grant Permissions
-- ============================================================================

GRANT SELECT ON dk.malaysian_holidays TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_festival_calendar_effects TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_festival_performance TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_promotion_impact TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_dow_heatmap TO healthcare_bi_reader;

GRANT SELECT ON dk.malaysian_holidays TO healthcare_bi_app;
GRANT SELECT ON dk.vw_festival_calendar_effects TO healthcare_bi_app;
GRANT SELECT ON dk.vw_festival_performance TO healthcare_bi_app;
GRANT SELECT ON dk.vw_promotion_impact TO healthcare_bi_app;
GRANT SELECT ON dk.vw_dow_heatmap TO healthcare_bi_app;

-- ============================================================================
-- END OF FILE
-- ============================================================================