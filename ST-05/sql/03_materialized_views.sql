-- ============================================================================
-- ST-05: AI/ML Predictive Engine
-- File: 03_materialized_views.sql
-- Description: Materialized views for ML caching
-- Schema: dk
-- Dependencies: Tables (dk.ml_predictions, dk.model_metadata, dk.ab_results)
--               created in 02_dynamic_pricing_views.sql
-- ============================================================================

-- ============================================================================
-- SECTION 1: Materialized Views for ML Caching
-- ============================================================================

-- ============================================================
-- Materialized View: mvw_ml_patient_features
-- Purpose: Cached ML features for fast model training
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_ml_patient_features AS
SELECT * FROM dk.vw_ml_patient_features;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_features_mrn ON dk.mvw_ml_patient_features (patient_id);
CREATE INDEX IF NOT EXISTS idx_mvw_features_recency ON dk.mvw_ml_patient_features (recency_days);
CREATE INDEX IF NOT EXISTS idx_mvw_features_segment ON dk.mvw_ml_patient_features (rfm_segment);
CREATE INDEX IF NOT EXISTS idx_mvw_features_churn ON dk.mvw_ml_patient_features (churn_risk);

COMMENT ON MATERIALIZED VIEW dk.mvw_ml_patient_features IS 'ST-05 cached ML features, refresh daily at 02:00 AM';

-- ============================================================
-- Materialized View: mvw_ml_predictions
-- Purpose: Cached predictions for Power BI
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_ml_predictions AS
SELECT 
    mp.mrn,
    mp.prediction_date,
    mp.churn_probability,
    mp.churn_risk_band,
    mp.pkg_upsell_prob,
    mp.upsell_action,
    mp.rec_skincare_prob,
    mp.rec_services_prob,
    mp.rec_medications_prob,
    mp.rec_supplements_prob,
    mp.top_recommendation,
    mp.promo_elastic_prob,
    mp.promo_segment,
    mp.top_feature_1,
    mp.top_feature_2,
    mp.model_version,
    
    -- Patient context for dashboard
    cr.patient_name,
    pe.age,
    pe.gender_display,
    pe.city,
    pe.state,
    pr.segment AS rfm_segment,
    pr.priority AS rfm_priority
    
FROM dk.ml_predictions mp
LEFT JOIN (
    SELECT mrn, MAX(csv_date) AS latest_date
    FROM dk.collection_report
    GROUP BY mrn
) latest ON mp.mrn = latest.mrn
LEFT JOIN dk.collection_report cr ON mp.mrn = cr.mrn AND cr.csv_date = latest.latest_date
LEFT JOIN dk.vw_patient_enriched pe ON mp.mrn = pe.mrn
LEFT JOIN dk.vw_patient_rfm pr ON mp.mrn = pr.patient_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_predictions_mrn ON dk.mvw_ml_predictions (mrn);
CREATE INDEX IF NOT EXISTS idx_mvw_predictions_churn ON dk.mvw_ml_predictions (churn_risk_band);
CREATE INDEX IF NOT EXISTS idx_mvw_predictions_upsell ON dk.mvw_ml_predictions (upsell_action);
CREATE INDEX IF NOT EXISTS idx_mvw_predictions_segment ON dk.mvw_ml_predictions (rfm_segment);

COMMENT ON MATERIALIZED VIEW dk.mvw_ml_predictions IS 'ST-05 cached ML predictions for Power BI, refresh after ML pipeline';

-- ============================================================
-- Materialized View: mvw_dynamic_pricing
-- Purpose: Cached dynamic pricing for Power BI
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS dk.mvw_dynamic_pricing AS
SELECT * FROM dk.vw_dynamic_pricing;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_pricing_mrn ON dk.mvw_dynamic_pricing (mrn);
CREATE INDEX IF NOT EXISTS idx_mvw_pricing_offer ON dk.mvw_dynamic_pricing (offer_type);

COMMENT ON MATERIALIZED VIEW dk.mvw_dynamic_pricing IS 'ST-05 cached dynamic pricing for Power BI';

-- ============================================================
-- Function: refresh_ml_mvws()
-- Purpose: Refresh all ST-05 materialized views in order
-- ============================================================

CREATE OR REPLACE FUNCTION dk.refresh_ml_mvws()
RETURNS TABLE (
    mvw_name VARCHAR(100),
    status VARCHAR(20),
    duration_ms FLOAT
) AS $$
DECLARE
    view_record RECORD;
    start_time TIMESTAMP;
    duration_ms FLOAT;
BEGIN
    FOR view_record IN 
        SELECT unnest(ARRAY[
            'mvw_ml_patient_features',
            'mvw_ml_predictions',
            'mvw_dynamic_pricing'
        ]) AS view_name
    LOOP
        start_time := clock_timestamp();
        
        BEGIN
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', 
                          'dk.' || view_record.view_name);
            duration_ms := EXTRACT(EPOCH FROM (clock_timestamp() - start_time)) * 1000;
            
            mvw_name := view_record.view_name;
            status := 'SUCCESS';
            duration_ms := duration_ms;
            RETURN NEXT;
        EXCEPTION WHEN OTHERS THEN
            -- Fall back to non-concurrent refresh
            BEGIN
                EXECUTE format('REFRESH MATERIALIZED VIEW %I', 
                              'dk.' || view_record.view_name);
                duration_ms := EXTRACT(EPOCH FROM (clock_timestamp() - start_time)) * 1000;
                
                mvw_name := view_record.view_name;
                status := 'SUCCESS (non-concurrent)';
                duration_ms := duration_ms;
                RETURN NEXT;
            EXCEPTION WHEN OTHERS THEN
                mvw_name := view_record.view_name;
                status := 'FAILED: ' || SQLERRM;
                duration_ms := 0;
                RETURN NEXT;
            END;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
