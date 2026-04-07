-- ============================================================================
-- ST-03: Patient Intelligence & Retention
-- File: 02_materialized_views.sql
-- Description: Materialized views for patient intelligence with indexes
-- Schema: dk
-- Dependencies: ST-03 patient intelligence views
-- ============================================================================

-- ============================================================================
-- SECTION 1: Patient LTV Predictions Table
-- Description: Stores BG/NBD + Gamma-Gamma LTV predictions from Python
-- NOTE: This table MUST be created BEFORE the materialized view that references it
-- ============================================================================

DROP TABLE IF EXISTS dk.patient_ltv_predictions CASCADE;
CREATE TABLE dk.patient_ltv_predictions (
    patient_id VARCHAR(50) PRIMARY KEY,
    
    -- Input features from RFM
    frequency INTEGER,
    recency_days INTEGER,
    T_days INTEGER,  -- customer age
    monetary_avg NUMERIC(12,2),
    
    -- BG/NBD model outputs
    predicted_purchases_12m NUMERIC(10,4),
    probability_alive NUMERIC(5,4),
    
    -- Gamma-Gamma model outputs
    predicted_clv_12m NUMERIC(12,2),
    predicted_clv_24m NUMERIC(12,2),
    
    -- CLV tier
    clv_tier VARCHAR(20),
    
    -- Metadata
    model_version VARCHAR(20),
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ltv_predictions_tier ON dk.patient_ltv_predictions (clv_tier);
CREATE INDEX idx_ltv_predictions_clv ON dk.patient_ltv_predictions (predicted_clv_12m DESC);
CREATE INDEX idx_ltv_predictions_alive ON dk.patient_ltv_predictions (probability_alive DESC);

COMMENT ON TABLE dk.patient_ltv_predictions IS 'Stores patient lifetime value predictions from BG/NBD + Gamma-Gamma models. Updated weekly by Python LTV model.';

-- ============================================================================
-- SECTION 2: Materialized Views
-- ============================================================================

-- Materialized View: D+3 Follow-up Tracker
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_followup_d3 CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_followup_d3 AS
SELECT * FROM dk.vw_followup_d3;

CREATE UNIQUE INDEX idx_mvw_followup_d3_patient ON dk.mvw_followup_d3 (patient_id);
CREATE INDEX idx_mvw_followup_d3_priority ON dk.mvw_followup_d3 (priority_rank, total_spent DESC);
CREATE INDEX idx_mvw_followup_d3_status ON dk.mvw_followup_d3 (followup_status);
CREATE INDEX idx_mvw_followup_d3_branch ON dk.mvw_followup_d3 (branch);

COMMENT ON MATERIALIZED VIEW dk.mvw_followup_d3 IS 'Materialized view of D+3 follow-up tracker. Refresh: Daily at 3:00 AM';

-- Materialized View: Patient Risk Classification
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_risk CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_patient_risk AS
SELECT * FROM dk.vw_patient_risk;

CREATE UNIQUE INDEX idx_mvw_patient_risk_id ON dk.mvw_patient_risk (patient_id);
CREATE INDEX idx_mvw_patient_risk_status ON dk.mvw_patient_risk (patient_status);
CREATE INDEX idx_mvw_patient_risk_tier ON dk.mvw_patient_risk (value_tier);
CREATE INDEX idx_mvw_patient_risk_branch ON dk.mvw_patient_risk (preferred_branch);

COMMENT ON MATERIALIZED VIEW dk.mvw_patient_risk IS 'Materialized view of patient risk classification. Refresh: Daily at 3:00 AM';

-- Materialized View: RFM Segmentation with NTILE
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_rfm_ntile CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_patient_rfm_ntile AS
SELECT * FROM dk.vw_patient_rfm_ntile;

CREATE UNIQUE INDEX idx_mvw_rfm_ntile_id ON dk.mvw_patient_rfm_ntile (patient_id);
CREATE INDEX idx_mvw_rfm_ntile_segment ON dk.mvw_patient_rfm_ntile (rfm_segment);
CREATE INDEX idx_mvw_rfm_ntile_priority ON dk.mvw_patient_rfm_ntile (segment_priority);
CREATE INDEX idx_mvw_rfm_ntile_score ON dk.mvw_patient_rfm_ntile (rfm_weighted_score DESC);
CREATE INDEX idx_mvw_rfm_ntile_highvalue ON dk.mvw_patient_rfm_ntile (is_high_value) WHERE is_high_value = TRUE;
CREATE INDEX idx_mvw_rfm_ntile_atrisk ON dk.mvw_patient_rfm_ntile (is_at_risk) WHERE is_at_risk = TRUE;

COMMENT ON MATERIALIZED VIEW dk.mvw_patient_rfm_ntile IS 'Materialized view of RFM segmentation with NTILE scoring. Refresh: Daily at 3:00 AM';

-- Materialized View: Cohort Retention
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_cohort_retention CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_cohort_retention AS
SELECT * FROM dk.vw_cohort_retention;

CREATE UNIQUE INDEX idx_mvw_cohort_pk ON dk.mvw_cohort_retention (cohort_month, branch, months_since_first);
CREATE INDEX idx_mvw_cohort_month ON dk.mvw_cohort_retention (cohort_month);
CREATE INDEX idx_mvw_cohort_branch ON dk.mvw_cohort_retention (branch);
CREATE INDEX idx_mvw_cohort_period ON dk.mvw_cohort_retention (months_since_first);

COMMENT ON MATERIALIZED VIEW dk.mvw_cohort_retention IS 'Materialized view of cohort retention analysis. Refresh: Daily at 3:00 AM';

-- Materialized View: Visit Frequency
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_visit_frequency CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_visit_frequency AS
SELECT * FROM dk.vw_visit_frequency;

CREATE UNIQUE INDEX idx_mvw_visit_freq_pk ON dk.mvw_visit_frequency (patient_id, branch);
CREATE INDEX idx_mvw_visit_freq_branch ON dk.mvw_visit_frequency (branch);
CREATE INDEX idx_mvw_visit_freq_visits ON dk.mvw_visit_frequency (total_visits DESC);
CREATE INDEX idx_mvw_visit_freq_bucket ON dk.mvw_visit_frequency (visit_bucket);
CREATE INDEX idx_mvw_visit_freq_loyalty ON dk.mvw_visit_frequency (loyalty_tier);
CREATE INDEX idx_mvw_visit_freq_repeat ON dk.mvw_visit_frequency (is_repeat_patient) WHERE is_repeat_patient = TRUE;

COMMENT ON MATERIALIZED VIEW dk.mvw_visit_frequency IS 'Materialized view of visit frequency distribution. Refresh: Daily at 3:00 AM';

-- Materialized View: Visit Frequency Summary
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_visit_frequency_summary CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_visit_frequency_summary AS
SELECT * FROM dk.vw_visit_frequency_summary;

CREATE UNIQUE INDEX idx_mvw_visit_freq_sum_branch ON dk.mvw_visit_frequency_summary (branch);
CREATE INDEX idx_mvw_visit_freq_sum_loyalty ON dk.mvw_visit_frequency_summary (loyalty_tier);
CREATE INDEX idx_mvw_visit_freq_sum_repeat ON dk.mvw_visit_frequency_summary (repeat_rate_pct DESC);

COMMENT ON MATERIALIZED VIEW dk.mvw_visit_frequency_summary IS 'Materialized view of branch-level visit frequency summary. Refresh: Daily at 3:00 AM';

-- Materialized View: Patient Dashboard
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_dashboard CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_patient_dashboard AS
SELECT * FROM dk.vw_patient_dashboard;

CREATE UNIQUE INDEX idx_mvw_patient_dash_branch ON dk.mvw_patient_dashboard (branch);
CREATE INDEX idx_mvw_patient_dash_health ON dk.mvw_patient_dashboard (patient_base_health_score DESC);

COMMENT ON MATERIALIZED VIEW dk.mvw_patient_dashboard IS 'Materialized view of executive patient dashboard. Refresh: Daily at 3:00 AM';

-- Materialized View: Patient LTV Predictions
DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_ltv_predictions CASCADE;
CREATE MATERIALIZED VIEW dk.mvw_patient_ltv_predictions AS
SELECT 
    ltv.patient_id AS mrn,
    ltv.frequency,
    ltv.recency_days AS recency,
    ltv.T_days AS T,
    ltv.monetary_avg AS monetary_value,
    ltv.predicted_purchases_12m AS predicted_purchases_next_90d,
    ltv.monetary_avg AS predicted_avg_order_value,  -- Using avg monetary as proxy
    ltv.predicted_clv_12m,
    ltv.predicted_clv_24m,
    ltv.probability_alive,
    ltv.clv_tier AS ltv_segment,
    ltv.model_version,
    ltv.calculated_at
FROM dk.patient_ltv_predictions ltv;

CREATE UNIQUE INDEX idx_mvw_ltv_pred_mrn ON dk.mvw_patient_ltv_predictions (mrn);
CREATE INDEX idx_mvw_ltv_pred_segment ON dk.mvw_patient_ltv_predictions (ltv_segment);
CREATE INDEX idx_mvw_ltv_pred_alive ON dk.mvw_patient_ltv_predictions (probability_alive DESC);
CREATE INDEX idx_mvw_ltv_pred_clv ON dk.mvw_patient_ltv_predictions (predicted_clv_24m DESC);

COMMENT ON MATERIALIZED VIEW dk.mvw_patient_ltv_predictions IS 'Materialized view of patient lifetime value predictions. Refresh: Weekly after Python CLTV model run';

-- ============================================================================
-- SECTION 3: Refresh Function
-- ============================================================================

CREATE OR REPLACE FUNCTION dk.refresh_patient_intelligence_mvws()
RETURNS TABLE(mvw_name TEXT, status TEXT, duration_ms NUMERIC) AS $$
DECLARE
    start_time TIMESTAMP;
    mvw_record RECORD;
BEGIN
    FOR mvw_record IN 
        SELECT matviewname 
        FROM pg_matviews 
        WHERE schemaname = 'dk'
          AND matviewname LIKE 'mvw_%'
          AND matviewname IN (
              'mvw_followup_d3',
              'mvw_patient_risk',
              'mvw_patient_rfm_ntile',
              'mvw_cohort_retention',
              'mvw_visit_frequency',
              'mvw_visit_frequency_summary',
              'mvw_patient_dashboard'
          )
        ORDER BY matviewname
    LOOP
        start_time := clock_timestamp();
        
        BEGIN
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY dk.%I', mvw_record.matviewname);
            
            RETURN QUERY SELECT 
                mvw_record.matviewname::TEXT,
                'SUCCESS'::TEXT,
                EXTRACT(MILLISECONDS FROM clock_timestamp() - start_time)::NUMERIC;
        EXCEPTION WHEN OTHERS THEN
            BEGIN
                EXECUTE format('REFRESH MATERIALIZED VIEW dk.%I', mvw_record.matviewname);
                
                RETURN QUERY SELECT 
                    mvw_record.matviewname::TEXT,
                    'SUCCESS (non-concurrent)'::TEXT,
                    EXTRACT(MILLISECONDS FROM clock_timestamp() - start_time)::NUMERIC;
            EXCEPTION WHEN OTHERS THEN
                RETURN QUERY SELECT 
                    mvw_record.matviewname::TEXT,
                    ('FAILED: ' || SQLERRM)::TEXT,
                    EXTRACT(MILLISECONDS FROM clock_timestamp() - start_time)::NUMERIC;
            END;
        END;
    END LOOP;
    
    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.refresh_patient_intelligence_mvws() IS 'Refreshes all ST-03 patient intelligence materialized views. Returns status for each view.';

-- ============================================================================
-- SECTION 4: Grant Permissions
-- ============================================================================

-- Grant select on materialized views to roles
GRANT SELECT ON dk.mvw_followup_d3 TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_patient_risk TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_patient_rfm_ntile TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_cohort_retention TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_visit_frequency TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_visit_frequency_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_patient_dashboard TO healthcare_bi_reader;
GRANT SELECT ON dk.patient_ltv_predictions TO healthcare_bi_reader;

GRANT SELECT ON dk.mvw_followup_d3 TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_patient_risk TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_patient_rfm_ntile TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_cohort_retention TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_visit_frequency TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_visit_frequency_summary TO healthcare_bi_app;
GRANT SELECT ON dk.mvw_patient_dashboard TO healthcare_bi_app;
GRANT SELECT ON dk.patient_ltv_predictions TO healthcare_bi_app;

GRANT INSERT, UPDATE, DELETE ON dk.patient_ltv_predictions TO healthcare_bi_app;

-- Grant execute on refresh function
GRANT EXECUTE ON FUNCTION dk.refresh_patient_intelligence_mvws() TO healthcare_bi_app;
GRANT EXECUTE ON FUNCTION dk.refresh_patient_intelligence_mvws() TO healthcare_bi_admin;

-- ============================================================================
-- END OF FILE
-- ============================================================================
