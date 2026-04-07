-- ============================================================================
-- ST-03: Patient Intelligence & Retention
-- File: 01_patient_intelligence_views.sql
-- Description: Patient analytics views using ST-01 base tables
-- Schema: dk
-- Dependencies: dk.patient, dk.collection
-- Actual Schema Fields:
--   dk.patient: location (PK), mrn, gender, dob, race_name, city_name, state_name
--   dk.collection: row_number, date, branch, mrn, amount_collected, discount
-- ============================================================================

-- ============================================================================
-- SECTION 1: D+3 Follow-Up Tracker View
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_followup_d3 AS
WITH reference_date AS (
    SELECT MAX(date) AS max_date FROM dk.collection
),
patient_last_visit AS (
    SELECT DISTINCT ON (c.mrn)
        c.mrn AS patient_id,
        c.row_number AS collection_id,
        c.date AS last_visit_date,
        c.branch,
        c.amount_collected AS last_transaction_amount,
        (SELECT max_date FROM reference_date) - c.date AS days_since_visit
    FROM dk.collection c
    WHERE c.date IS NOT NULL
    ORDER BY c.mrn, c.date DESC
),
patient_summary AS (
    SELECT
        pt.mrn AS patient_id,
        COUNT(DISTINCT c.row_number) AS total_visits,
        SUM(c.amount_collected) AS total_spent,
        MAX(c.date) AS last_visit,
        MIN(c.date) AS first_visit
    FROM dk.patient pt
    LEFT JOIN dk.collection c ON pt.mrn = c.mrn
    GROUP BY pt.mrn
)
SELECT
    plv.patient_id,
    plv.collection_id,
    plv.last_visit_date,
    plv.days_since_visit,
    plv.branch,
    plv.last_transaction_amount,
    ps.total_visits,
    ROUND(ps.total_spent::NUMERIC, 2) AS total_spent,
    ps.first_visit,
    
    CASE
        WHEN ps.total_spent >= 5000 THEN 'HIGH'
        WHEN ps.total_spent >= 1500 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS value_segment,
    
    CASE
        WHEN plv.days_since_visit = 3 THEN 'READY'
        WHEN plv.days_since_visit > 3 AND plv.days_since_visit <= 7 THEN 'OVERDUE'
        WHEN plv.days_since_visit < 3 THEN 'PENDING'
        ELSE 'EXPIRED'
    END AS followup_status,
    
    CASE
        WHEN ps.total_spent >= 5000 AND plv.days_since_visit = 3 THEN 1
        WHEN ps.total_spent >= 1500 AND plv.days_since_visit = 3 THEN 2
        WHEN plv.days_since_visit = 3 THEN 3
        WHEN plv.days_since_visit BETWEEN 4 AND 7 THEN 4
        ELSE 5
    END AS priority_rank,
    
    CASE
        WHEN ps.total_spent >= 5000 THEN 'VIP Follow-up Call - Thank you & Next Appointment'
        WHEN ps.total_spent >= 1500 THEN 'Loyal Customer Check-in - Satisfaction & Upsell'
        WHEN ps.total_visits = 1 THEN 'New Patient Welcome - Complete Health Journey'
        ELSE 'Standard Follow-up - Build Relationship'
    END AS recommended_action,
    
    CURRENT_TIMESTAMP AS generated_at

FROM patient_last_visit plv
LEFT JOIN patient_summary ps ON plv.patient_id = ps.patient_id
WHERE plv.days_since_visit BETWEEN 3 AND 30
ORDER BY priority_rank, total_spent DESC;

COMMENT ON VIEW dk.vw_followup_d3 IS 'D+3 follow-up tracker using ST-01 schema fields.';

-- ============================================================================
-- SECTION 2: Patient Risk Classification View
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_patient_risk AS
WITH reference_date AS (
    SELECT MAX(date) AS max_date FROM dk.collection
),
patient_metrics AS (
    SELECT DISTINCT ON (p.mrn)
        p.mrn AS patient_id,
        p.city_name AS location,
        p.gender,
        p.dob,
        p.city_name,
        p.state_name,
        
        COUNT(DISTINCT c.row_number) AS total_transactions,
        SUM(c.amount_collected) AS total_revenue,
        MAX(c.date) AS last_transaction_date,
        MIN(c.date) AS first_transaction_date,
        (SELECT max_date FROM reference_date) - MAX(c.date) AS days_since_last_visit,
        MODE() WITHIN GROUP (ORDER BY c.branch) AS preferred_branch
    FROM dk.patient p
    LEFT JOIN dk.collection c ON p.mrn = c.mrn
    GROUP BY p.mrn, p.city_name, p.gender, p.dob, p.state_name
    ORDER BY p.mrn
),
patient_status AS (
    SELECT
        *,
        CASE
            WHEN days_since_last_visit IS NULL THEN 'NEW'
            WHEN days_since_last_visit <= 30 THEN 'ACTIVE'
            WHEN days_since_last_visit <= 60 THEN 'AT RISK'
            WHEN days_since_last_visit <= 90 THEN 'HIGH RISK'
            ELSE 'LOST'
        END AS patient_status,
        
        CASE
            WHEN total_revenue >= 5000 THEN 'Platinum'
            WHEN total_revenue >= 2500 THEN 'Gold'
            WHEN total_revenue >= 1000 THEN 'Silver'
            WHEN total_revenue >= 500 THEN 'Bronze'
            WHEN total_revenue > 0 THEN 'Standard'
            ELSE 'No Spend'
        END AS value_tier
    FROM patient_metrics
)
SELECT
    patient_id,
    location,
    gender,
    dob,
    CASE
        WHEN dob IS NOT NULL THEN EXTRACT(YEAR FROM AGE((SELECT max_date FROM reference_date), dob))::INTEGER
        ELSE NULL
    END AS age,
    city_name,
    state_name,
    total_transactions,
    ROUND(total_revenue::NUMERIC, 2) AS total_revenue,
    last_transaction_date,
    first_transaction_date,
    days_since_last_visit,
    preferred_branch,
    patient_status,
    value_tier,
    
    CASE patient_status
        WHEN 'ACTIVE' THEN 'Green'
        WHEN 'AT RISK' THEN 'Amber'
        WHEN 'HIGH RISK' THEN 'Orange'
        WHEN 'LOST' THEN 'Red'
        WHEN 'NEW' THEN 'Blue'
    END AS status_color,
    
    CASE
        WHEN patient_status = 'ACTIVE' THEN 0
        WHEN patient_status = 'AT RISK' THEN 33
        WHEN patient_status = 'HIGH RISK' THEN 66
        WHEN patient_status = 'LOST' THEN 100
        ELSE 50
    END AS risk_score,
    
    CASE
        WHEN patient_status IN ('AT RISK', 'HIGH RISK', 'LOST') THEN ROUND(total_revenue::NUMERIC, 2)
        ELSE 0
    END AS revenue_at_risk,
    
    CASE
        WHEN patient_status = 'ACTIVE' AND value_tier IN ('Platinum', 'Gold') THEN 'VIP Retention - Exclusive offers'
        WHEN patient_status = 'ACTIVE' THEN 'Maintain - Regular engagement'
        WHEN patient_status = 'AT RISK' AND value_tier IN ('Platinum', 'Gold') THEN 'Urgent Win-back - Personal outreach'
        WHEN patient_status = 'AT RISK' THEN 'Win-back - Special discount'
        WHEN patient_status = 'HIGH RISK' AND total_revenue > 1000 THEN 'Critical - Manager intervention'
        WHEN patient_status = 'HIGH RISK' THEN 'Reactivation - Survey & offer'
        WHEN patient_status = 'LOST' AND total_revenue > 2000 THEN 'Last chance - Exclusive package'
        WHEN patient_status = 'LOST' THEN 'Revive - Deep discount'
        ELSE 'Nurture - Welcome series'
    END AS retention_action,
    
    CASE
        WHEN patient_status = 'ACTIVE' THEN 30 - COALESCE(days_since_last_visit, 0)
        WHEN patient_status = 'AT RISK' THEN 60 - COALESCE(days_since_last_visit, 0)
        WHEN patient_status = 'HIGH RISK' THEN 90 - COALESCE(days_since_last_visit, 0)
        ELSE 0
    END AS days_until_escalation,
    
    CURRENT_TIMESTAMP AS assessed_at

FROM patient_status
ORDER BY 
    CASE patient_status
        WHEN 'ACTIVE' THEN 1
        WHEN 'AT RISK' THEN 2
        WHEN 'HIGH RISK' THEN 3
        WHEN 'LOST' THEN 4
        ELSE 5
    END,
    total_revenue DESC;

COMMENT ON VIEW dk.vw_patient_risk IS 'Patient risk classification using ST-01 schema.';

-- ============================================================================
-- SECTION 3: Enhanced RFM Segmentation with NTILE
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_patient_rfm_ntile AS
WITH reference_date AS (
    SELECT MAX(date) AS max_date FROM dk.collection
),
patient_metrics AS (
    SELECT DISTINCT ON (p.mrn)
        p.mrn AS patient_id,
        p.gender,
        p.city_name,
        p.state_name,
        COUNT(DISTINCT c.row_number) AS frequency,
        SUM(c.amount_collected) AS monetary,
        MAX(c.date) AS last_visit_date,
        (SELECT max_date FROM reference_date) - MAX(c.date) AS recency_days,
        MIN(c.date) AS first_visit_date,
        (SELECT max_date FROM reference_date) - MIN(c.date) AS customer_tenure_days
    FROM dk.patient p
    LEFT JOIN dk.collection c ON p.mrn = c.mrn
    GROUP BY p.mrn, p.gender, p.city_name, p.state_name
    HAVING COUNT(DISTINCT c.row_number) > 0
    ORDER BY p.mrn
),
rfm_scored AS (
    SELECT
        *,
        NTILE(5) OVER (ORDER BY recency_days ASC) AS r_score,
        NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,
        NTILE(5) OVER (ORDER BY monetary ASC) AS m_score
    FROM patient_metrics
),
rfm_segmented AS (
    SELECT
        *,
        (r_score * 100 + f_score * 10 + m_score) AS rfm_score,
        r_score::TEXT || f_score::TEXT || m_score::TEXT AS rfm_cell,
        ROUND((r_score * 0.35 + f_score * 0.35 + m_score * 0.30)::NUMERIC, 2) AS rfm_weighted_score,
        
        CASE
            WHEN r_score = 5 AND f_score >= 4 AND m_score >= 4 THEN 'VIP'
            WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 3 THEN 'LOYAL'
            WHEN r_score >= 4 AND f_score >= 2 THEN 'POTENTIAL LOYALIST'
            WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4 THEN 'AT RISK HIGH VALUE'
            WHEN r_score <= 2 AND f_score <= 2 AND m_score <= 2 THEN 'LOST LOW VALUE'
            WHEN r_score <= 2 THEN 'AT RISK'
            WHEN f_score <= 2 THEN 'NEW/INFREQUENT'
            ELSE 'REGULAR'
        END AS rfm_segment
    FROM rfm_scored
)
SELECT
    patient_id,
    gender,
    city_name,
    state_name,
    frequency,
    ROUND(monetary::NUMERIC, 2) AS monetary,
    last_visit_date,
    recency_days,
    first_visit_date,
    customer_tenure_days,
    r_score,
    f_score,
    m_score,
    rfm_score,
    rfm_cell,
    rfm_weighted_score,
    rfm_segment,
    
    CASE rfm_segment
        WHEN 'VIP' THEN 1
        WHEN 'AT RISK HIGH VALUE' THEN 2
        WHEN 'LOYAL' THEN 3
        WHEN 'POTENTIAL LOYALIST' THEN 4
        WHEN 'AT RISK' THEN 5
        WHEN 'REGULAR' THEN 6
        WHEN 'NEW/INFREQUENT' THEN 7
        WHEN 'LOST LOW VALUE' THEN 8
        ELSE 9
    END AS segment_priority,
    
    rfm_segment IN ('VIP', 'LOYAL', 'AT RISK HIGH VALUE') AS is_high_value,
    rfm_segment IN ('AT RISK', 'AT RISK HIGH VALUE', 'LOST LOW VALUE') AS is_at_risk,
    rfm_segment IN ('POTENTIAL LOYALIST', 'NEW/INFREQUENT') AS has_growth_potential,
    
    CASE rfm_segment
        WHEN 'VIP' THEN 'Exclusive rewards & early access to new services'
        WHEN 'LOYAL' THEN 'Upsell premium packages & referral incentives'
        WHEN 'POTENTIAL LOYALIST' THEN 'Membership programs & cross-sell'
        WHEN 'AT RISK HIGH VALUE' THEN 'Immediate personal outreach & win-back offer'
        WHEN 'AT RISK' THEN 'Engagement campaign & satisfaction survey'
        WHEN 'REGULAR' THEN 'Frequency incentives & service education'
        WHEN 'NEW/INFREQUENT' THEN 'Welcome series & service awareness'
        WHEN 'LOST LOW VALUE' THEN 'Deep discount reactivation'
        ELSE 'Nurture with relevant content'
    END AS campaign_recommendation,
    
    CURRENT_TIMESTAMP AS scored_at

FROM rfm_segmented
ORDER BY segment_priority, monetary DESC;

COMMENT ON VIEW dk.vw_patient_rfm_ntile IS 'RFM segmentation using NTILE(5) with ST-01 schema.';

-- ============================================================================
-- SECTION 4: Monthly Cohort Retention Analysis
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_cohort_retention AS
WITH patient_first_visit AS (
    SELECT DISTINCT ON (c.mrn)
        c.mrn AS patient_id,
        c.date AS first_visit_date,
        DATE_TRUNC('month', c.date)::date AS cohort_month,
        c.branch
    FROM dk.collection c
    WHERE c.date IS NOT NULL
    ORDER BY c.mrn, c.date ASC
),
patient_visits AS (
    SELECT
        c.mrn AS patient_id,
        c.date AS visit_date,
        DATE_TRUNC('month', c.date)::date AS visit_month
    FROM dk.collection c
    WHERE c.date IS NOT NULL
),
cohort_activity AS (
    SELECT
        pfv.patient_id,
        pfv.cohort_month,
        pfv.branch,
        pfv.first_visit_date,
        pv.visit_month,
        EXTRACT(YEAR FROM pv.visit_month)::INTEGER * 12 + EXTRACT(MONTH FROM pv.visit_month)::INTEGER -
        (EXTRACT(YEAR FROM pfv.cohort_month)::INTEGER * 12 + EXTRACT(MONTH FROM pfv.cohort_month)::INTEGER) AS months_since_first
    FROM patient_first_visit pfv
    JOIN patient_visits pv ON pfv.patient_id = pv.patient_id
),
cohort_sizes AS (
    SELECT
        cohort_month,
        branch,
        COUNT(DISTINCT patient_id) AS cohort_size
    FROM patient_first_visit
    GROUP BY cohort_month, branch
),
retention_counts AS (
    SELECT
        ca.cohort_month,
        ca.branch,
        ca.months_since_first,
        cs.cohort_size,
        COUNT(DISTINCT ca.patient_id) AS retained_patients
    FROM cohort_activity ca
    JOIN cohort_sizes cs ON ca.cohort_month = cs.cohort_month AND ca.branch = cs.branch
    WHERE ca.months_since_first >= 0
    GROUP BY ca.cohort_month, ca.branch, ca.months_since_first, cs.cohort_size
)
SELECT
    rc.cohort_month,
    TO_CHAR(rc.cohort_month, 'YYYY-MM') AS cohort_month_label,
    rc.branch,
    rc.cohort_size,
    rc.months_since_first,
    rc.retained_patients,
    
    CASE
        WHEN rc.cohort_size > 0 THEN ROUND((rc.retained_patients::NUMERIC / rc.cohort_size * 100), 2)
        ELSE 0
    END AS retention_rate_pct,
    
    EXTRACT(YEAR FROM (SELECT MAX(date) FROM dk.collection))::INTEGER * 12 + EXTRACT(MONTH FROM (SELECT MAX(date) FROM dk.collection))::INTEGER -
    (EXTRACT(YEAR FROM rc.cohort_month)::INTEGER * 12 + EXTRACT(MONTH FROM rc.cohort_month)::INTEGER) AS cohort_age_months,
    
    CASE rc.months_since_first
        WHEN 0 THEN 'Month 0 (First Visit)'
        WHEN 1 THEN 'Month 1'
        WHEN 3 THEN 'Month 3'
        WHEN 6 THEN 'Month 6'
        WHEN 12 THEN 'Month 12'
        ELSE 'Month ' || rc.months_since_first::TEXT
    END AS period_label,
    
    CASE
        WHEN rc.months_since_first = 0 THEN 100.0
        WHEN rc.months_since_first = 1 THEN 60.0
        WHEN rc.months_since_first = 3 THEN 45.0
        WHEN rc.months_since_first = 6 THEN 30.0
        WHEN rc.months_since_first = 12 THEN 20.0
        ELSE NULL
    END AS benchmark_retention_pct,
    
    CASE
        WHEN rc.months_since_first IN (0, 1, 3, 6, 12) AND rc.cohort_size > 0 THEN
            ROUND((rc.retained_patients::NUMERIC / rc.cohort_size * 100), 2) -
            CASE
                WHEN rc.months_since_first = 0 THEN 100.0
                WHEN rc.months_since_first = 1 THEN 60.0
                WHEN rc.months_since_first = 3 THEN 45.0
                WHEN rc.months_since_first = 6 THEN 30.0
                WHEN rc.months_since_first = 12 THEN 20.0
            END
        ELSE NULL
    END AS vs_benchmark_pct,
    
    CURRENT_TIMESTAMP AS calculated_at

FROM retention_counts rc
ORDER BY rc.cohort_month DESC, rc.months_since_first;

COMMENT ON VIEW dk.vw_cohort_retention IS 'Monthly cohort retention using ST-01 schema.';

-- ============================================================================
-- SECTION 5: Visit Frequency Distribution
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_visit_frequency AS
WITH patient_visit_counts AS (
    SELECT
        c.mrn AS patient_id,
        c.branch,
        COUNT(DISTINCT c.row_number) AS total_visits,
        COUNT(DISTINCT DATE_TRUNC('month', c.date)) AS active_months,
        SUM(c.amount_collected) AS total_revenue,
        MAX(c.date) AS last_visit_date,
        MIN(c.date) AS first_visit_date
    FROM dk.collection c
    WHERE c.date IS NOT NULL
    GROUP BY c.mrn, c.branch
),
visit_buckets AS (
    SELECT
        *,
        CASE
            WHEN total_visits = 1 THEN '1 Visit'
            WHEN total_visits = 2 THEN '2 Visits'
            WHEN total_visits BETWEEN 3 AND 5 THEN '3-5 Visits'
            WHEN total_visits BETWEEN 6 AND 10 THEN '6-10 Visits'
            WHEN total_visits > 10 THEN '10+ Visits'
        END AS visit_bucket,
        total_visits > 1 AS is_repeat_patient,
        CASE
            WHEN total_visits >= 10 THEN 'Platinum'
            WHEN total_visits >= 6 THEN 'Gold'
            WHEN total_visits >= 3 THEN 'Silver'
            WHEN total_visits >= 2 THEN 'Bronze'
            ELSE 'New'
        END AS loyalty_tier
    FROM patient_visit_counts
)
SELECT
    patient_id,
    branch,
    total_visits,
    active_months,
    ROUND(total_revenue::NUMERIC, 2) AS total_revenue,
    first_visit_date,
    last_visit_date,
    (SELECT MAX(date) FROM dk.collection) - last_visit_date AS days_since_last_visit,
    visit_bucket,
    is_repeat_patient,
    loyalty_tier,
    
    CASE
        WHEN active_months > 0 THEN ROUND((total_visits::NUMERIC / active_months), 2)
        ELSE total_visits
    END AS avg_visits_per_month,
    
    CASE
        WHEN total_visits > 0 THEN ROUND((total_revenue / total_visits)::NUMERIC, 2)
        ELSE 0
    END AS revenue_per_visit,
    
    CASE
        WHEN first_visit_date != last_visit_date THEN last_visit_date - first_visit_date
        ELSE 0
    END AS customer_lifespan_days,
    
    CURRENT_TIMESTAMP AS calculated_at

FROM visit_buckets
ORDER BY total_visits DESC, total_revenue DESC;

COMMENT ON VIEW dk.vw_visit_frequency IS 'Visit frequency distribution with ST-01 schema.';

-- ============================================================================
-- SECTION 6: Branch-Level Frequency Summary
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_visit_frequency_summary AS
WITH branch_stats AS (
    SELECT
        branch,
        COUNT(DISTINCT patient_id) AS total_patients,
        SUM(CASE WHEN total_visits = 1 THEN 1 ELSE 0 END) AS one_visit_patients,
        SUM(CASE WHEN total_visits >= 2 THEN 1 ELSE 0 END) AS repeat_patients,
        SUM(total_visits) AS total_visits,
        SUM(total_revenue) AS total_revenue,
        AVG(total_visits) AS avg_visits_per_patient,
        AVG(total_revenue) AS avg_revenue_per_patient
    FROM dk.vw_visit_frequency
    GROUP BY branch
)
SELECT
    branch,
    total_patients,
    one_visit_patients,
    repeat_patients,
    total_visits,
    ROUND(total_revenue::NUMERIC, 2) AS total_revenue,
    ROUND(avg_visits_per_patient::NUMERIC, 2) AS avg_visits_per_patient,
    ROUND(avg_revenue_per_patient::NUMERIC, 2) AS avg_revenue_per_patient,
    
    CASE
        WHEN total_patients > 0 THEN ROUND((repeat_patients::NUMERIC / total_patients * 100), 2)
        ELSE 0
    END AS repeat_rate_pct,
    
    CASE
        WHEN total_patients > 0 THEN ROUND((one_visit_patients::NUMERIC / total_patients * 100), 2)
        ELSE 0
    END AS one_visit_pct,
    
    CASE
        WHEN total_visits > 0 THEN ROUND((total_revenue / total_visits)::NUMERIC, 2)
        ELSE 0
    END AS revenue_per_visit,
    
    CASE
        WHEN avg_visits_per_patient >= 5 THEN 'High Loyalty'
        WHEN avg_visits_per_patient >= 3 THEN 'Medium Loyalty'
        WHEN avg_visits_per_patient >= 2 THEN 'Low Loyalty'
        ELSE 'New Patient Focus'
    END AS loyalty_tier,
    
    CURRENT_TIMESTAMP AS calculated_at

FROM branch_stats
ORDER BY avg_visits_per_patient DESC, total_revenue DESC;

COMMENT ON VIEW dk.vw_visit_frequency_summary IS 'Branch-level visit frequency summary with ST-01 schema.';

-- ============================================================================
-- SECTION 7: Executive Patient Dashboard View
-- ============================================================================

CREATE OR REPLACE VIEW dk.vw_patient_dashboard AS
WITH branch_patient_metrics AS (
    SELECT
        pr.preferred_branch AS branch,
        COUNT(DISTINCT pr.patient_id) AS total_patients,
        SUM(CASE WHEN pr.patient_status = 'ACTIVE' THEN 1 ELSE 0 END) AS active_patients,
        SUM(CASE WHEN pr.patient_status = 'AT RISK' THEN 1 ELSE 0 END) AS at_risk_patients,
        SUM(CASE WHEN pr.patient_status = 'HIGH RISK' THEN 1 ELSE 0 END) AS high_risk_patients,
        SUM(CASE WHEN pr.patient_status = 'LOST' THEN 1 ELSE 0 END) AS lost_patients,
        SUM(CASE WHEN pr.patient_status = 'NEW' THEN 1 ELSE 0 END) AS new_patients,
        SUM(CASE WHEN pr.value_tier = 'Platinum' THEN 1 ELSE 0 END) AS platinum_patients,
        SUM(CASE WHEN pr.value_tier = 'Gold' THEN 1 ELSE 0 END) AS gold_patients,
        SUM(CASE WHEN pr.value_tier = 'Silver' THEN 1 ELSE 0 END) AS silver_patients,
        SUM(CASE WHEN pr.value_tier = 'Bronze' THEN 1 ELSE 0 END) AS bronze_patients,
        SUM(pr.total_revenue) AS total_revenue,
        SUM(CASE WHEN pr.patient_status IN ('AT RISK', 'HIGH RISK', 'LOST') THEN pr.total_revenue ELSE 0 END) AS revenue_at_risk,
        AVG(pr.total_transactions) AS avg_transactions_per_patient,
        AVG(CASE WHEN pr.days_since_last_visit IS NOT NULL THEN pr.days_since_last_visit END) AS avg_days_since_visit
    FROM dk.vw_patient_risk pr
    GROUP BY pr.preferred_branch
)
SELECT
    branch,
    total_patients,
    active_patients,
    at_risk_patients,
    high_risk_patients,
    lost_patients,
    new_patients,
    
    CASE WHEN total_patients > 0 THEN ROUND((active_patients::NUMERIC / total_patients * 100), 2) ELSE 0 END AS active_pct,
    CASE WHEN total_patients > 0 THEN ROUND((at_risk_patients::NUMERIC / total_patients * 100), 2) ELSE 0 END AS at_risk_pct,
    CASE WHEN total_patients > 0 THEN ROUND((high_risk_patients::NUMERIC / total_patients * 100), 2) ELSE 0 END AS high_risk_pct,
    CASE WHEN total_patients > 0 THEN ROUND((lost_patients::NUMERIC / total_patients * 100), 2) ELSE 0 END AS lost_pct,
    
    platinum_patients,
    gold_patients,
    silver_patients,
    bronze_patients,
    
    CASE WHEN total_patients > 0 THEN ROUND(((platinum_patients + gold_patients)::NUMERIC / total_patients * 100), 2) ELSE 0 END AS high_value_pct,
    
    ROUND(total_revenue::NUMERIC, 2) AS total_revenue,
    ROUND(revenue_at_risk::NUMERIC, 2) AS revenue_at_risk,
    CASE WHEN total_patients > 0 THEN ROUND((total_revenue / total_patients)::NUMERIC, 2) ELSE 0 END AS avg_revenue_per_patient,
    ROUND(avg_transactions_per_patient::NUMERIC, 2) AS avg_transactions_per_patient,
    ROUND(avg_days_since_visit::NUMERIC, 0) AS avg_days_since_visit,
    
    CASE
        WHEN total_patients > 0 THEN
            ROUND((
                (active_patients::NUMERIC / total_patients * 40) +
                ((platinum_patients + gold_patients)::NUMERIC / total_patients * 30) +
                (CASE WHEN avg_transactions_per_patient >= 3 THEN 20 ELSE avg_transactions_per_patient * 7 END) +
                (CASE WHEN avg_days_since_visit <= 30 THEN 10 ELSE GREATEST(0, 10 - (avg_days_since_visit - 30) / 10) END)
            ), 0)
        ELSE 0
    END AS patient_base_health_score,
    
    CASE
        WHEN high_risk_patients > lost_patients * 0.5 THEN 'Urgent: High risk patients need attention'
        WHEN at_risk_patients > active_patients * 0.3 THEN 'Warning: Many patients at risk'
        WHEN revenue_at_risk > total_revenue * 0.2 THEN 'Alert: Significant revenue at risk'
        ELSE 'Healthy: Patient base stable'
    END AS priority_alert,
    
    CURRENT_TIMESTAMP AS generated_at

FROM branch_patient_metrics
ORDER BY total_revenue DESC;

COMMENT ON VIEW dk.vw_patient_dashboard IS 'Executive patient dashboard using ST-01 schema.';

-- ============================================================================
-- SECTION 8: Grant Permissions
-- ============================================================================

GRANT SELECT ON dk.vw_followup_d3 TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_risk TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_rfm_ntile TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_cohort_retention TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_visit_frequency TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_visit_frequency_summary TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_dashboard TO healthcare_bi_reader;

GRANT SELECT ON dk.vw_followup_d3 TO healthcare_bi_app;
GRANT SELECT ON dk.vw_patient_risk TO healthcare_bi_app;
GRANT SELECT ON dk.vw_patient_rfm_ntile TO healthcare_bi_app;
GRANT SELECT ON dk.vw_cohort_retention TO healthcare_bi_app;
GRANT SELECT ON dk.vw_visit_frequency TO healthcare_bi_app;
GRANT SELECT ON dk.vw_visit_frequency_summary TO healthcare_bi_app;
GRANT SELECT ON dk.vw_patient_dashboard TO healthcare_bi_app;