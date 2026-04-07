-- ============================================================
-- ST-05: AI/ML Predictive Models
-- ml_model_views.sql
-- Views and tables for ML features and predictions
-- ============================================================

-- ============================================================
-- TABLE: ML Model Registry
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.ml_model_registry (
    model_id SERIAL PRIMARY KEY,
    model_name VARCHAR(200) NOT NULL,
    model_version VARCHAR(50) DEFAULT '1.0',
    model_type VARCHAR(100),  -- 'propensity', 'churn', 'ltv', 'next_best'
    model_algorithm VARCHAR(100),  -- 'xgboost', 'logistic_regression', etc.
    model_path VARCHAR(500),
    training_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_trained_date TIMESTAMP,
    auc_roc_score DECIMAL(5,4),
    accuracy_score DECIMAL(5,4),
    precision_score DECIMAL(5,4),
    recall_score DECIMAL(5,4),
    f1_score DECIMAL(5,4),
    training_rows INTEGER,
    feature_columns TEXT[],
    hyperparameters JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE: ML Predictions
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.ml_predictions (
    prediction_id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES dk.ml_model_registry(model_id),
    mrn VARCHAR(50) REFERENCES dk.patient(mrn),
    prediction_type VARCHAR(100),  -- 'propensity_to_return', 'churn_risk', etc.
    prediction_score DECIMAL(5,4),
    prediction_class VARCHAR(50),  -- 'high', 'medium', 'low'
    prediction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_version VARCHAR(50),
    feature_values JSONB,
    confidence_interval_lower DECIMAL(5,4),
    confidence_interval_upper DECIMAL(5,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_predictions_mrn ON dk.ml_predictions(mrn);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_model ON dk.ml_predictions(model_id);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_date ON dk.ml_predictions(prediction_date);

-- ============================================================
-- TABLE: A/B Testing Framework
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.ab_tests (
    test_id SERIAL PRIMARY KEY,
    test_name VARCHAR(200) NOT NULL,
    test_type VARCHAR(100),  -- 'pricing', 'messaging', 'timing', 'offer'
    start_date DATE,
    end_date DATE,
    control_group_size INTEGER,
    treatment_group_size INTEGER,
    control_conversion_rate DECIMAL(5,4),
    treatment_conversion_rate DECIMAL(5,4),
    lift_percentage DECIMAL(5,4),
    p_value DECIMAL(10,8),
    is_statistically_significant BOOLEAN DEFAULT FALSE,
    status VARCHAR(50) DEFAULT 'draft',  -- 'draft', 'running', 'completed', 'stopped'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dk.ab_test_assignments (
    assignment_id SERIAL PRIMARY KEY,
    test_id INTEGER REFERENCES dk.ab_tests(test_id),
    mrn VARCHAR(50),
    variant VARCHAR(50),  -- 'control', 'treatment'
    assigned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    converted BOOLEAN DEFAULT FALSE,
    conversion_date TIMESTAMP,
    revenue_impact DECIMAL(15,2) DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ab_test_mrn ON dk.ab_test_assignments(mrn);
CREATE INDEX IF NOT EXISTS idx_ab_test_variant ON dk.ab_test_assignments(test_id, variant);

-- ============================================================
-- TABLE: Dynamic Pricing Rules
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.dynamic_pricing_rules (
    rule_id SERIAL PRIMARY KEY,
    rule_name VARCHAR(200),
    product_code VARCHAR(100),
    patient_segment VARCHAR(100),  -- 'VIP', 'High Value', etc.
    rfm_segment VARCHAR(100),
    base_discount_pct DECIMAL(5,2) DEFAULT 0,
    max_discount_pct DECIMAL(5,2) DEFAULT 0,
    min_discount_pct DECIMAL(5,2) DEFAULT 0,
    price_elasticity_factor DECIMAL(5,4) DEFAULT 1.0,
    seasonal_multiplier DECIMAL(5,4) DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- VIEW: ML Feature Store
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_ml_feature_store AS
SELECT 
    mf.*,
    -- Additional engineered features
    CASE 
        WHEN mf.frequency >= 6 AND mf.monetary >= 1000 THEN 1
        ELSE 0
    END AS is_high_value_customer,
    CASE 
        WHEN mf.recency_days <= 30 THEN 1
        ELSE 0
    END AS is_recent_customer,
    -- Time-based features
    EXTRACT(DOW FROM CURRENT_DATE)::INTEGER AS current_day_of_week,
    EXTRACT(MONTH FROM CURRENT_DATE)::INTEGER AS current_month,
    EXTRACT(QUARTER FROM CURRENT_DATE)::INTEGER AS current_quarter,
    -- Interaction features
    mf.frequency * mf.monetary / NULLIF(mf.recency_days, 0) AS engagement_intensity
FROM dk.vw_ml_patient_features mf;

-- ============================================================
-- VIEW: Propensity to Return Predictions
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_propensity_predictions AS
SELECT 
    mrn,
    patient_name,
    recency_days,
    frequency,
    monetary,
    patient_status,
    rfm_segment,
    CASE 
        WHEN rfm_segment IN ('Champions', 'Loyal Customers', 'Potential Loyalists') THEN 0.85
        WHEN rfm_segment IN ('New Customers') THEN 0.70
        WHEN rfm_segment IN ('At Risk', 'Cannot Lose Them') THEN 0.45
        WHEN rfm_segment IN ('Hibernating', 'Lost') THEN 0.15
        ELSE 0.50
    END AS predicted_propensity_score,
    CASE 
        WHEN rfm_segment IN ('Champions', 'Loyal Customers', 'Potential Loyalists') THEN 'High'
        WHEN rfm_segment IN ('New Customers') THEN 'Medium'
        WHEN rfm_segment IN ('At Risk', 'Cannot Lose Them') THEN 'Medium-Low'
        ELSE 'Low'
    END AS propensity_class
FROM dk.mvw_patient_transactions;

-- ============================================================
-- VIEW: Next Best Treatment Recommendations
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_next_best_treatment AS
WITH patient_categories AS (
    SELECT 
        mrn,
        category,
        COUNT(*) AS purchase_count,
        SUM(net_amount) AS total_spent
    FROM dk.mvw_transaction_flat
    GROUP BY mrn, category
),
patient_top_categories AS (
    SELECT 
        mrn,
        category,
        purchase_count,
        ROW_NUMBER() OVER (PARTITION BY mrn ORDER BY purchase_count DESC, total_spent DESC) AS category_rank
    FROM patient_categories
),
cross_sell_candidates AS (
    SELECT 
        ptc.mrn,
        csp.category_b AS recommended_category,
        csp.affinity_score
    FROM patient_top_categories ptc
    JOIN dk.vw_cross_sell_patterns csp ON ptc.category = csp.category_a
    WHERE ptc.category_rank = 1
      AND csp.affinity_score >= 0.1
)
SELECT 
    csc.mrn,
    pt.patient_name,
    pt.rfm_segment,
    pt.total_orders,
    csc.recommended_category,
    ROUND(csc.affinity_score * 100, 2) AS recommendation_strength,
    -- Priority based on patient value
    CASE 
        WHEN pt.rfm_segment IN ('Champions', 'Loyal Customers') THEN 1
        WHEN pt.rfm_segment IN ('Potential Loyalists') THEN 2
        ELSE 3
    END AS priority
FROM cross_sell_candidates csc
JOIN dk.mvw_patient_transactions pt ON csc.mrn = pt.mrn
ORDER BY csc.mrn, csc.affinity_score DESC;

-- ============================================================
-- VIEW: Churn Risk Scoring
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_churn_risk_scoring AS
SELECT 
    mrn,
    patient_name,
    recency_days,
    frequency,
    monetary,
    rfm_segment,
    -- Churn risk factors
    CASE 
        WHEN recency_days > 180 THEN 0.9
        WHEN recency_days > 90 THEN 0.7
        WHEN recency_days > 60 THEN 0.5
        WHEN recency_days > 30 THEN 0.3
        ELSE 0.1
    END AS recency_risk,
    CASE 
        WHEN frequency = 1 THEN 0.8
        WHEN frequency <= 3 THEN 0.5
        WHEN frequency <= 6 THEN 0.3
        ELSE 0.1
    END AS frequency_risk,
    -- Combined churn score
    ROUND((
        (CASE 
            WHEN recency_days > 180 THEN 0.9
            WHEN recency_days > 90 THEN 0.7
            WHEN recency_days > 60 THEN 0.5
            WHEN recency_days > 30 THEN 0.3
            ELSE 0.1
        END * 0.5) +
        (CASE 
            WHEN frequency = 1 THEN 0.8
            WHEN frequency <= 3 THEN 0.5
            WHEN frequency <= 6 THEN 0.3
            ELSE 0.1
        END * 0.3) +
        (CASE 
            WHEN monetary < 500 THEN 0.6
            WHEN monetary < 1000 THEN 0.4
            WHEN monetary < 5000 THEN 0.2
            ELSE 0.1
        END * 0.2)
    )::NUMERIC, 4) AS churn_probability,
    -- Risk class
    CASE 
        WHEN recency_days > 180 THEN 'Critical'
        WHEN recency_days > 90 OR frequency = 1 THEN 'High'
        WHEN recency_days > 60 THEN 'Medium'
        WHEN recency_days > 30 THEN 'Low'
        ELSE 'Safe'
    END AS churn_risk_class
FROM dk.mvw_patient_transactions;

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE dk.ml_model_registry IS 'Registry of trained ML models with performance metrics';
COMMENT ON TABLE dk.ml_predictions IS 'Individual patient predictions from ML models';
COMMENT ON TABLE dk.ab_tests IS 'A/B testing experiment definitions';
COMMENT ON TABLE dk.ab_test_assignments IS 'Patient assignments to A/B test variants';
COMMENT ON TABLE dk.dynamic_pricing_rules IS 'Rules for dynamic pricing and discounts';
COMMENT ON VIEW dk.vw_ml_feature_store IS 'Feature store for ML model training';
COMMENT ON VIEW dk.vw_propensity_predictions IS 'Patient propensity to return predictions';
COMMENT ON VIEW dk.vw_next_best_treatment IS 'Next best treatment/category recommendations';
COMMENT ON VIEW dk.vw_churn_risk_scoring IS 'Churn risk scoring based on RFM features';
