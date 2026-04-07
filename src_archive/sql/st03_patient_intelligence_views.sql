-- ============================================================
-- ST-03: Patient Intelligence
-- patient_intelligence_views.sql
-- Views for Patient Analytics and Segmentation
-- ============================================================

-- ============================================================
-- VIEW 1: Patient Visit Patterns
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_patient_visit_patterns AS
WITH patient_visits AS (
    SELECT 
        mrn,
        transaction_date,
        net_amount,
        branch_name,
        LAG(transaction_date) OVER (PARTITION BY mrn ORDER BY transaction_date) AS prev_visit_date,
        LEAD(transaction_date) OVER (PARTITION BY mrn ORDER BY transaction_date) AS next_visit_date
    FROM dk.mvw_transaction_flat
),
visit_intervals AS (
    SELECT 
        mrn,
        transaction_date,
        net_amount,
        branch_name,
        prev_visit_date,
        next_visit_date,
        CASE 
            WHEN prev_visit_date IS NOT NULL 
            THEN transaction_date - prev_visit_date 
            ELSE NULL 
        END AS days_since_prev_visit,
        CASE 
            WHEN next_visit_date IS NOT NULL 
            THEN next_visit_date - transaction_date 
            ELSE NULL 
        END AS days_until_next_visit
    FROM patient_visits
),
patient_metrics AS (
    SELECT 
        mrn,
        COUNT(*) AS total_visits,
        MIN(transaction_date) AS first_visit,
        MAX(transaction_date) AS last_visit,
        AVG(net_amount) AS avg_visit_value,
        SUM(net_amount) AS total_spent,
        AVG(days_since_prev_visit) AS avg_days_between_visits,
        STDDEV(days_since_prev_visit) AS stddev_days_between,
        MIN(days_since_prev_visit) AS min_interval,
        MAX(days_since_prev_visit) AS max_interval,
        COUNT(DISTINCT branch_name) AS branches_visited
    FROM visit_intervals
    GROUP BY mrn
)
SELECT 
    pm.*,
    CURRENT_DATE - pm.last_visit AS days_since_last_visit,
    CASE 
        WHEN pm.avg_days_between_visits IS NULL THEN 'New Patient'
        WHEN pm.avg_days_between_visits <= 30 THEN 'Frequent (<=30 days)'
        WHEN pm.avg_days_between_visits <= 90 THEN 'Regular (31-90 days)'
        WHEN pm.avg_days_between_visits <= 180 THEN 'Occasional (91-180 days)'
        ELSE 'Infrequent (>180 days)'
    END AS visit_frequency_segment,
    CASE 
        WHEN pm.total_visits = 1 THEN 'One-Time'
        WHEN pm.total_visits <= 3 THEN 'Occasional'
        WHEN pm.total_visits <= 6 THEN 'Regular'
        ELSE 'Loyal'
    END AS loyalty_segment,
    CASE 
        WHEN CURRENT_DATE - pm.last_visit <= 30 THEN 'Active'
        WHEN CURRENT_DATE - pm.last_visit <= 90 THEN 'At Risk'
        ELSE 'Lapsed'
    END AS current_status
FROM patient_metrics pm;

-- ============================================================
-- VIEW 2: Patient Cohort Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_patient_cohort_analysis AS
WITH first_visits AS (
    SELECT DISTINCT
        mrn,
        MIN(transaction_date) OVER (PARTITION BY mrn) AS first_visit_date,
        DATE_TRUNC('month', MIN(transaction_date) OVER (PARTITION BY mrn)) AS cohort_month
    FROM dk.mvw_transaction_flat
),
monthly_activity AS (
    SELECT 
        fv.mrn,
        fv.cohort_month,
        fv.first_visit_date,
        tf.transaction_date,
        tf.net_amount,
        DATE_TRUNC('month', tf.transaction_date) AS activity_month,
        EXTRACT(YEAR FROM AGE(DATE_TRUNC('month', tf.transaction_date), fv.cohort_month)) * 12 +
        EXTRACT(MONTH FROM AGE(DATE_TRUNC('month', tf.transaction_date), fv.cohort_month)) AS period_number
    FROM first_visits fv
    JOIN dk.mvw_transaction_flat tf ON fv.mrn = tf.mrn
),
cohort_metrics AS (
    SELECT 
        cohort_month,
        period_number,
        COUNT(DISTINCT mrn) AS active_patients,
        SUM(net_amount) AS cohort_revenue,
        COUNT(DISTINCT mrn) FILTER (WHERE period_number = 0) AS cohort_size
    FROM monthly_activity
    GROUP BY cohort_month, period_number
)
SELECT 
    cohort_month,
    period_number,
    active_patients,
    cohort_revenue,
    cohort_size,
    ROUND(active_patients::NUMERIC / NULLIF(cohort_size, 0) * 100, 2) AS retention_rate_pct,
    ROUND(cohort_revenue / NULLIF(active_patients, 0), 2) AS revenue_per_active_patient
FROM cohort_metrics
ORDER BY cohort_month, period_number;

-- ============================================================
-- VIEW 3: RFM Customer Segments with Recommendations
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_rfm_with_recommendations AS
SELECT 
    mrn,
    patient_name,
    phone,
    email,
    rfm_segment,
    r_score,
    f_score,
    m_score,
    recency,
    frequency,
    monetary,
    -- Marketing recommendations
    CASE rfm_segment
        WHEN 'Champions' THEN 'Reward them. Early adopter for new products. Can provide highest discount.'
        WHEN 'Loyal Customers' THEN 'Upsell higher value products. Ask for reviews.'
        WHEN 'Potential Loyalists' THEN 'Offer membership / loyalty program. Keep them engaged.'
        WHEN 'New Customers' THEN 'Provide onboarding support. Give them early success.'
        WHEN 'At Risk' THEN 'Make limited time offers. Recommend new products.'
        WHEN 'Cannot Lose Them' THEN 'Win them back via renewals / helpful products.'
        WHEN 'Hibernating' THEN 'Offer other relevant products and special discounts.'
        WHEN 'Lost' THEN 'Revive interest with reach-out campaign. Ignore otherwise.'
        ELSE 'Monitor and analyze behavior'
    END AS recommended_action,
    -- Channel preference
    CASE 
        WHEN rfm_segment IN ('Champions', 'Loyal Customers') THEN 'WhatsApp Personal'
        WHEN rfm_segment IN ('Potential Loyalists', 'New Customers') THEN 'WhatsApp + Email'
        WHEN rfm_segment IN ('At Risk', 'Cannot Lose Them') THEN 'Phone Call + WhatsApp'
        ELSE 'Email'
    END AS preferred_channel,
    -- Priority
    CASE rfm_segment
        WHEN 'Champions' THEN 1
        WHEN 'Loyal Customers' THEN 2
        WHEN 'Potential Loyalists' THEN 3
        WHEN 'At Risk' THEN 4
        WHEN 'Cannot Lose Them' THEN 5
        ELSE 6
    END AS engagement_priority
FROM dk.mvw_patient_rfm;

-- ============================================================
-- VIEW 4: Patient LTV Prediction
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_patient_ltv_prediction AS
WITH patient_history AS (
    SELECT 
        mrn,
        COUNT(DISTINCT DATE_TRUNC('month', transaction_date)) AS active_months,
        COUNT(*) AS total_transactions,
        SUM(net_amount) AS total_revenue,
        AVG(net_amount) AS avg_transaction_value,
        MIN(transaction_date) AS first_transaction,
        MAX(transaction_date) AS last_transaction
    FROM dk.mvw_transaction_flat
    GROUP BY mrn
),
monthly_spending AS (
    SELECT 
        mrn,
        DATE_TRUNC('month', transaction_date) AS month,
        SUM(net_amount) AS monthly_spend
    FROM dk.mvw_transaction_flat
    GROUP BY mrn, DATE_TRUNC('month', transaction_date)
),
spending_trend AS (
    SELECT 
        mrn,
        REGR_SLOPE(monthly_spend, EXTRACT(EPOCH FROM month)) AS spending_slope,
        AVG(monthly_spend) AS avg_monthly_spend
    FROM monthly_spending
    GROUP BY mrn
    HAVING COUNT(*) >= 3
)
SELECT 
    ph.mrn,
    ph.active_months,
    ph.total_transactions,
    ph.total_revenue,
    ph.avg_transaction_value,
    ph.first_transaction,
    ph.last_transaction,
    CURRENT_DATE - ph.last_transaction AS days_since_last_transaction,
    st.spending_slope,
    st.avg_monthly_spend,
    -- LTV Prediction
    CASE 
        WHEN ph.active_months >= 12 THEN 
            ph.total_revenue + (st.avg_monthly_spend * 12)
        WHEN ph.active_months >= 6 THEN 
            ph.total_revenue + (st.avg_monthly_spend * 18)
        WHEN ph.active_months >= 3 THEN 
            ph.total_revenue + (st.avg_monthly_spend * 24)
        ELSE 
            ph.total_revenue * 2
    END AS predicted_ltv_24m,
    -- Churn risk
    CASE 
        WHEN CURRENT_DATE - ph.last_transaction > 180 THEN 'High Risk'
        WHEN CURRENT_DATE - ph.last_transaction > 90 THEN 'Medium Risk'
        WHEN st.spending_slope IS NOT NULL AND st.spending_slope < 0 THEN 'Declining'
        ELSE 'Stable'
    END AS churn_risk,
    -- Value tier
    CASE 
        WHEN predicted_ltv_24m >= 10000 THEN 'VIP'
        WHEN predicted_ltv_24m >= 5000 THEN 'High Value'
        WHEN predicted_ltv_24m >= 1000 THEN 'Medium Value'
        ELSE 'Low Value'
    END AS value_tier
FROM patient_history ph
LEFT JOIN spending_trend st ON ph.mrn = st.mrn;

-- ============================================================
-- VIEW 5: D+3 Follow-up Tracker Enhanced
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_d3_followup_enhanced AS
SELECT 
    d3.mrn,
    d3.patient_name,
    d3.phone,
    d3.email,
    d3.last_visit_date,
    d3.last_branch,
    d3.last_doctor,
    d3.last_visit_amount,
    d3.days_since_visit,
    d3.days_between_visits,
    d3.followup_priority,
    d3.recommended_action,
    d3.patient_status,
    d3.rfm_segment,
    d3.ltv_segment,
    -- Add contextual information
    vp.visit_frequency_segment,
    vp.loyalty_segment,
    vr.churn_risk,
    vr.predicted_ltv_24m,
    vr.value_tier,
    -- Recommended message template
    CASE 
        WHEN d3.followup_priority = 'High Priority' THEN 
            'Hi ' || d3.patient_name || ', thank you for your recent visit. We hope you''re satisfied with your treatment. Would you like to schedule your next session?'
        WHEN d3.followup_priority = 'Medium Priority' THEN 
            'Hi ' || d3.patient_name || ', we noticed it''s been ' || d3.days_since_visit || ' days since your visit. Is everything going well?'
        ELSE 
            'Hi ' || d3.patient_name || ', we''re checking in after your recent visit. Let us know if you need anything!'
    END AS suggested_whatsapp_message,
    -- Campaign eligibility
    CASE 
        WHEN d3.followup_priority IN ('High Priority', 'Medium Priority') 
             AND d3.rfm_segment NOT IN ('Lost', 'Hibernating')
        THEN TRUE
        ELSE FALSE
    END AS is_campaign_eligible
FROM dk.mvw_d3_followup_list d3
LEFT JOIN dk.vw_patient_visit_patterns vp ON d3.mrn = vp.mrn
LEFT JOIN dk.vw_patient_ltv_prediction vr ON d3.mrn = vr.mrn
WHERE d3.days_since_visit = 3;

-- ============================================================
-- MATERIALIZED VIEW: Patient Intelligence Summary
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_patient_intelligence CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_patient_intelligence AS
SELECT 
    pe.mrn,
    pe.name,
    pe.email,
    pe.phone,
    pe.age,
    pe.age_group,
    pe.gender,
    pe.city,
    pe.state,
    pe.patient_status,
    pr.rfm_segment,
    pr.r_score,
    pr.f_score,
    pr.m_score,
    pl.ltv_segment,
    pl.predicted_annual_ltv,
    vp.visit_frequency_segment,
    vp.loyalty_segment,
    vp.current_status,
    vp.total_visits,
    vp.avg_visit_value,
    vp.avg_days_between_visits,
    vp.days_since_last_visit,
    vr.churn_risk,
    vr.predicted_ltv_24m,
    vr.value_tier,
    CURRENT_DATE AS snapshot_date
FROM dk.mvw_patient_enriched pe
LEFT JOIN dk.mvw_patient_rfm pr ON pe.mrn = pr.mrn
LEFT JOIN dk.mvw_patient_ltv pl ON pe.mrn = pl.mrn
LEFT JOIN dk.vw_patient_visit_patterns vp ON pe.mrn = vp.mrn
LEFT JOIN dk.vw_patient_ltv_prediction vr ON pe.mrn = vr.mrn;

CREATE UNIQUE INDEX idx_mvw_patient_intel_mrn ON dk.mvw_patient_intelligence(mrn);
CREATE INDEX idx_mvw_patient_intel_rfm ON dk.mvw_patient_intelligence(rfm_segment);
CREATE INDEX idx_mvw_patient_intel_ltv ON dk.mvw_patient_intelligence(ltv_segment);

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON VIEW dk.vw_patient_visit_patterns IS 'Patient visit frequency and pattern analysis';
COMMENT ON VIEW dk.vw_patient_cohort_analysis IS 'Monthly cohort retention analysis';
COMMENT ON VIEW dk.vw_rfm_with_recommendations IS 'RFM segments with marketing recommendations';
COMMENT ON VIEW dk.vw_patient_ltv_prediction IS 'Patient lifetime value prediction with churn risk';
COMMENT ON VIEW dk.vw_d3_followup_enhanced IS 'Enhanced D+3 follow-up tracker with LTV context';
COMMENT ON MATERIALIZED VIEW dk.mvw_patient_intelligence IS 'Consolidated patient intelligence for Power BI';
