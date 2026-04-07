-- ============================================================================
-- ST-05: AI/ML Predictive Engine
-- File: 02_dynamic_pricing_views.sql
-- Description: Dynamic pricing and A/B testing views
-- Schema: dk
-- Dependencies: dk.vw_patient_enriched, dk.vw_patient_rfm
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS dk;

-- ============================================================
-- Table: dk.ml_predictions
-- Purpose: Stores all 4 model predictions per patient (must exist before views)
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.ml_predictions (
    mrn VARCHAR(50) PRIMARY KEY,
    prediction_date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Model 1: Churn Risk
    churn_probability FLOAT,
    churn_risk_band VARCHAR(20),

    -- Model 2: Package Upsell
    pkg_upsell_prob FLOAT,
    upsell_action VARCHAR(20),

    -- Model 3: NBT Recommendations
    rec_skincare_prob FLOAT,
    rec_services_prob FLOAT,
    rec_medications_prob FLOAT,
    rec_supplements_prob FLOAT,
    top_recommendation VARCHAR(50),

    -- Model 4: Promo Elasticity
    promo_elastic_prob FLOAT,
    promo_segment VARCHAR(50),

    -- SHAP interpretability
    top_feature_1 VARCHAR(100),
    top_feature_2 VARCHAR(100),
    shap_contribution FLOAT,

    -- Model versioning
    model_version VARCHAR(50) NOT NULL,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_predictions_date ON dk.ml_predictions (prediction_date);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_churn ON dk.ml_predictions (churn_risk_band);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_upsell ON dk.ml_predictions (upsell_action);

COMMENT ON TABLE dk.ml_predictions IS 'ST-05 ML model predictions: churn risk, package upsell, NBT recommendations, promo elasticity';

-- ============================================================
-- Table: dk.model_metadata
-- Purpose: Model versions, metrics, SHAP values
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.model_metadata (
    model_name VARCHAR(50) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    train_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    train_end_date DATE NOT NULL,

    -- Performance metrics
    auc_roc FLOAT,
    avg_precision FLOAT,
    positive_samples INTEGER,
    negative_samples INTEGER,

    -- Hyperparameters
    parameters JSONB,

    -- Global feature importance (SHAP)
    feature_importance JSONB,

    -- Model artifact path (optional)
    model_artifact_path VARCHAR(255),

    -- Calibration info
    calibration_method VARCHAR(50) DEFAULT 'isotonic',

    PRIMARY KEY (model_name, model_version)
);

CREATE INDEX IF NOT EXISTS idx_model_metadata_date ON dk.model_metadata (train_date);

COMMENT ON TABLE dk.model_metadata IS 'ST-05 model metadata: versions, metrics, SHAP importance, hyperparameters';

-- ============================================================
-- Table: dk.ab_results
-- Purpose: A/B test statistical results
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.ab_results (
    experiment_name VARCHAR(100) NOT NULL,
    analysis_date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Control group (A) stats
    group_a_patients INTEGER,
    group_a_conversions INTEGER,
    group_a_revenue NUMERIC(15, 2),
    group_a_conversion_rate FLOAT,

    -- Treatment group (B) stats
    group_b_patients INTEGER,
    group_b_conversions INTEGER,
    group_b_revenue NUMERIC(15, 2),
    group_b_conversion_rate FLOAT,

    -- Statistical analysis
    chi2_statistic FLOAT,
    p_value FLOAT,
    is_significant BOOLEAN,

    -- Effect size
    relative_lift_pct FLOAT,
    absolute_lift_pct FLOAT,
    confidence_interval_lower FLOAT,
    confidence_interval_upper FLOAT,

    PRIMARY KEY (experiment_name, analysis_date)
);

COMMENT ON TABLE dk.ab_results IS 'ST-05 A/B test results with chi-square statistical analysis';

-- ============================================================
-- View: vw_dynamic_pricing
-- Purpose: Generate personalized pricing offers based on ML predictions
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_dynamic_pricing AS
WITH patient_scores AS (
    -- Get latest predictions with patient context
    SELECT 
        mp.mrn,
        mp.promo_elastic_prob,
        mp.promo_segment,
        mp.pkg_upsell_prob,
        mp.upsell_action,
        mp.churn_probability,
        mp.churn_risk_band,
        pe.value_tier,
        pe.patient_status,
        pr.segment AS rfm_segment,
        pr.priority AS rfm_priority
    FROM dk.ml_predictions mp
    LEFT JOIN dk.vw_patient_enriched pe ON mp.mrn = pe.mrn
    LEFT JOIN dk.vw_patient_rfm pr ON mp.mrn = pr.patient_id
)
SELECT 
    mrn,
    promo_elastic_prob,
    promo_segment,
    pkg_upsell_prob,
    upsell_action,
    churn_probability,
    churn_risk_band,
    value_tier,
    patient_status,
    rfm_segment,
    rfm_priority,
    
    -- Determine offer type based on segmentation
    CASE 
        -- High promo elasticity: offer discount
        WHEN promo_elastic_prob > 0.7 THEN 'discount'
        -- Package upsell opportunity: offer bundle
        WHEN pkg_upsell_prob > 0.6 THEN 'bundle'
        -- High churn risk: offer retention deal
        WHEN churn_probability > 0.7 THEN 'retention'
        -- Loyal customer (Champions, Loyal): offer VIP perk
        WHEN rfm_segment IN ('Champions', 'Loyal Customers') THEN 'vip_perk'
        -- At risk: offer win-back deal
        WHEN rfm_segment IN ('At Risk', 'Cannot Lose Them') THEN 'win_back'
        -- New customer: offer welcome deal
        WHEN rfm_segment = 'New Customers' THEN 'welcome'
        -- Default: standard offer
        ELSE 'standard'
    END AS offer_type,
    
    -- Calculate discount percentage based on elasticity and segment
    CASE 
        WHEN promo_elastic_prob > 0.8 THEN 25
        WHEN promo_elastic_prob > 0.7 THEN 20
        WHEN promo_elastic_prob > 0.6 THEN 15
        WHEN pkg_upsell_prob > 0.7 THEN 15
        WHEN churn_probability > 0.8 THEN 20
        WHEN churn_probability > 0.7 THEN 15
        WHEN rfm_segment IN ('Champions', 'Loyal Customers') THEN 10
        WHEN rfm_segment IN ('At Risk', 'Cannot Lose Them') THEN 15
        WHEN rfm_segment = 'New Customers' THEN 10
        ELSE 5
    END AS discount_pct,
    
    -- Calculate offer value (max discount cap based on value tier)
    CASE 
        WHEN value_tier = 'Platinum' THEN 500
        WHEN value_tier = 'Gold' THEN 300
        WHEN value_tier = 'Silver' THEN 150
        ELSE 100
    END AS max_discount_rm,
    
    -- Offer priority score (higher = more urgent)
    ROUND(
        (churn_probability * 0.4 + 
         promo_elastic_prob * 0.3 + 
         pkg_upsell_prob * 0.3) * 100
    )::INTEGER AS offer_priority,
    
    -- Recommended action
    CASE 
        WHEN churn_probability > 0.7 THEN 'Immediate outreach with retention offer'
        WHEN pkg_upsell_prob > 0.6 THEN 'Suggest package bundle during next visit'
        WHEN promo_elastic_prob > 0.7 THEN 'Send targeted promo campaign'
        WHEN rfm_segment IN ('Champions', 'Loyal Customers') THEN 'Invite to VIP program'
        ELSE 'Standard engagement'
    END AS recommended_action,
    
    CURRENT_TIMESTAMP AS offer_generated_at
    
FROM patient_scores;

COMMENT ON VIEW dk.vw_dynamic_pricing IS 'ST-05 dynamic pricing engine: personalized offers based on promo elasticity, churn risk, package upsell probability, and RFM segmentation';

-- ============================================================
-- Table: dk.dynamic_pricing_offers
-- Purpose: Persisted personalized offers for Power BI and outreach
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.dynamic_pricing_offers (
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(50) NOT NULL,
    offer_type VARCHAR(20) NOT NULL,
    discount_pct INTEGER,
    max_discount_rm NUMERIC(10, 2),
    offer_priority INTEGER,
    recommended_action TEXT,
    promo_elastic_prob FLOAT,
    pkg_upsell_prob FLOAT,
    churn_probability FLOAT,
    value_tier VARCHAR(20),
    rfm_segment VARCHAR(50),
    generated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dpo_mrn ON dk.dynamic_pricing_offers (mrn);
CREATE INDEX IF NOT EXISTS idx_dpo_offer_type ON dk.dynamic_pricing_offers (offer_type);
CREATE INDEX IF NOT EXISTS idx_dpo_priority ON dk.dynamic_pricing_offers (offer_priority DESC);
CREATE INDEX IF NOT EXISTS idx_dpo_generated_at ON dk.dynamic_pricing_offers (generated_at);

COMMENT ON TABLE dk.dynamic_pricing_offers IS 'ST-05 persisted dynamic pricing offers generated by Python engine';

-- ============================================================
-- View: vw_ab_assignment
-- Purpose: Deterministic A/B test assignment using hash
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_ab_assignment AS
SELECT 
    mrn,
    offer_type,
    discount_pct,
    max_discount_rm,
    offer_priority,
    recommended_action,
    offer_generated_at,
    
    -- Deterministic assignment based on MRN hash
    CASE 
        WHEN ABS(MOD(hashtext(mrn || '_' || CURRENT_DATE::text), 2)) = 0 THEN 'A'
        ELSE 'B'
    END AS test_group,
    
    -- Experiment name
    'dynamic_pricing_v1' AS experiment_id,
    
    -- Assignment date
    CURRENT_DATE AS assignment_date
    
FROM dk.vw_dynamic_pricing;

COMMENT ON VIEW dk.vw_ab_assignment IS 'ST-05 A/B test assignment for dynamic pricing experiments using deterministic hash-based allocation';
