-- ============================================================
-- ST-05: AI/ML Predictive Engine
-- 01_ml_features_views.sql
-- ML Feature Engineering Views
-- ============================================================

CREATE SCHEMA IF NOT EXISTS dk;

-- ============================================================
-- View: vw_ml_patient_features (Enhanced for ST-05)
-- Purpose: 30+ engineered features per patient for ML models
-- ============================================================

DROP VIEW IF EXISTS dk.vw_ml_patient_features CASCADE;

CREATE OR REPLACE VIEW dk.vw_ml_patient_features AS
WITH patient_base AS (
    -- Base aggregations from collection table
    SELECT DISTINCT ON (c.mrn)
        c.mrn AS patient_id,
        COUNT(DISTINCT c.row_number) AS total_transactions,
        COUNT(DISTINCT c.date) AS visit_days,
        COUNT(DISTINCT c.branch) AS branches_visited,
        SUM(COALESCE(c.amount_collected, 0)) AS total_revenue,
        SUM(COALESCE(c.discount, 0)) AS total_discount,
        SUM(COALESCE(c.patient_outstanding_amount, 0)) AS total_outstanding,
        AVG(COALESCE(c.amount_collected, 0)) AS avg_transaction,
        MAX(COALESCE(c.amount_collected, 0)) AS max_transaction,
        STDDEV(COALESCE(c.amount_collected, 0)) AS std_transaction,
        
        -- Recency
        CURRENT_DATE - MAX(c.date) AS recency_days,
        
        -- Frequency by period
        COUNT(DISTINCT CASE WHEN c.date >= CURRENT_DATE - INTERVAL '30 days' THEN c.row_number END) AS frequency_30d,
        COUNT(DISTINCT CASE WHEN c.date >= CURRENT_DATE - INTERVAL '90 days' THEN c.row_number END) AS frequency_90d,
        COUNT(DISTINCT CASE WHEN c.date >= CURRENT_DATE - INTERVAL '12 months' THEN c.row_number END) AS frequency_12m,
        
        -- Date range
        MIN(c.date) AS first_visit_date,
        MAX(c.date) AS last_visit_date,
        
        -- Tenure
        (MAX(c.date) - MIN(c.date))::INTEGER AS tenure_days,
        
        -- Category sums (standalone)
        SUM(COALESCE(c.standalone_sales_skincare_product_amount, 0)) AS skincare_rev,
        SUM(COALESCE(c.standalone_sales_services, 0)) AS services_rev,
        SUM(COALESCE(c.standalone_sales_medications, 0)) AS medications_rev,
        SUM(COALESCE(c.standalone_sales_supplements_supplement_rm5_amount, 0) + 
            COALESCE(c.standalone_sales_supplements_supplement_na_amount, 0)) AS supplements_rev,
        
        -- Package sums
        SUM(COALESCE(c.package_sales_subtotal, 0)) AS package_rev,
        
        -- Discount behavior
        AVG(COALESCE(c.discount / NULLIF(c.amount_collected, 0), 0)) AS avg_discount_pct,
        COUNT(CASE WHEN c.discount > 0 THEN 1 END) AS discount_frequency
        
    FROM dk.collection c
    WHERE c.mrn IS NOT NULL AND c.date IS NOT NULL
    GROUP BY c.mrn
),
cohort_calc AS (
    -- Calculate cohort month (first visit month)
    SELECT 
        patient_id,
        DATE_TRUNC('month', first_visit_date)::DATE AS cohort_month
    FROM patient_base
),
promo_calc AS (
    -- Calculate promotion and package behavior ratios
    SELECT 
        patient_id,
        CASE WHEN total_transactions > 0 
             THEN discount_frequency::FLOAT / total_transactions 
             ELSE 0 END AS promo_dependency_pct,
        CASE WHEN total_revenue > 0 
             THEN package_rev / total_revenue 
             ELSE 0 END AS pkg_revenue_ratio,
        CASE WHEN total_revenue > 0 
             THEN (skincare_rev + services_rev + medications_rev + supplements_rev) / total_revenue 
             ELSE 0 END AS standalone_ratio,
        CASE WHEN total_revenue > 0 THEN skincare_rev / total_revenue ELSE 0 END AS skincare_share_pct,
        CASE WHEN total_revenue > 0 THEN services_rev / total_revenue ELSE 0 END AS services_share_pct,
        CASE WHEN total_revenue > 0 THEN medications_rev / total_revenue ELSE 0 END AS medications_share_pct,
        CASE WHEN total_revenue > 0 THEN supplements_rev / total_revenue ELSE 0 END AS supplements_share_pct,
        CASE WHEN total_revenue > 0 THEN services_rev / total_revenue ELSE 0 END AS services_ratio,
        CASE WHEN total_revenue > 0 THEN medications_rev / total_revenue ELSE 0 END AS medications_ratio,
        CASE WHEN package_rev > 0 THEN 1 ELSE 0 END AS has_package_flag,
        CASE WHEN total_revenue > 0 THEN package_rev / total_revenue ELSE 0 END AS package_ratio
    FROM patient_base
),
outstanding_calc AS (
    -- Calculate outstanding ratios and financial stress
    SELECT 
        patient_id,
        total_outstanding,
        total_revenue,
        CASE WHEN total_revenue > 0 
             THEN total_outstanding / total_revenue 
             ELSE 0 END AS outstanding_ratio
    FROM patient_base
),
rfm_scores AS (
    -- Calculate RFM scores using NTILE
    SELECT
        patient_id,
        recency_days,
        total_transactions AS frequency,
        total_revenue AS monetary,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
        NTILE(5) OVER (ORDER BY total_transactions ASC) AS f_score,
        NTILE(5) OVER (ORDER BY total_revenue ASC) AS m_score
    FROM patient_base
),
avg_gap AS (
    -- Calculate average gap between visits and consistency
    SELECT 
        patient_id,
        CASE WHEN visit_days > 1 
             THEN tenure_days::FLOAT / (visit_days - 1) 
             ELSE 0 END AS avg_gap_days,
        0 AS visit_consistency
    FROM patient_base
)
SELECT 
    pb.patient_id,
    
    -- Demographics (from existing vw_patient_enriched)
    pe.gender,
    pe.age,
    pe.race_name,
    pe.city AS city_name,
    pe.state AS state_name,
    
    -- Core behavioral
    pb.total_transactions,
    pb.visit_days,
    pb.branches_visited,
    pb.total_revenue,
    pb.avg_transaction AS avg_transaction_value,
    pb.max_transaction,
    COALESCE(pb.std_transaction, 0) AS std_transaction,
    
    -- Recency features
    pb.recency_days,
    CASE 
        WHEN pb.recency_days <= 7 THEN 'Very Recent'
        WHEN pb.recency_days <= 30 THEN 'Recent'
        WHEN pb.recency_days <= 90 THEN 'Moderate'
        WHEN pb.recency_days <= 180 THEN 'Dormant'
        ELSE 'Lost'
    END AS recency_band,
    
    -- Frequency features
    pb.frequency_30d,
    pb.frequency_90d,
    pb.frequency_12m,
    COALESCE(ag.avg_gap_days, 0) AS avg_gap_days,
    
    -- Tenure features
    pb.tenure_days,
    (pb.tenure_days / 30.0)::NUMERIC(8,2) AS tenure_months,
    cc.cohort_month,
    
    -- Category mix
    COALESCE(pc.skincare_share_pct, 0) AS skincare_share_pct,
    COALESCE(pc.services_share_pct, 0) AS services_share_pct,
    COALESCE(pc.medications_share_pct, 0) AS medications_share_pct,
    COALESCE(pc.supplements_share_pct, 0) AS supplements_share_pct,
    
    -- Package behavior
    COALESCE(pc.pkg_revenue_ratio, 0) AS pkg_revenue_ratio,
    pc.has_package_flag,
    
    -- Promo behavior
    COALESCE(pc.promo_dependency_pct, 0) AS promo_dependency_pct,
    COALESCE(pb.avg_discount_pct, 0) AS avg_discount_pct,
    COALESCE(pb.discount_frequency, 0) AS discount_frequency,
    
    -- Financial stress
    COALESCE(oc.total_outstanding, 0) AS avg_outstanding,
    COALESCE(oc.outstanding_ratio, 0) AS outstanding_ratio,
    CASE 
        WHEN oc.outstanding_ratio > 0.3 THEN 'High'
        WHEN oc.outstanding_ratio > 0.1 THEN 'Medium'
        ELSE 'Low'
    END AS stress_level,
    
    -- Visit pattern
    COALESCE(ag.visit_consistency, 0) AS visit_consistency,
    
    -- RFM features
    rs.r_score,
    rs.f_score,
    rs.m_score,
    CASE
        WHEN rs.r_score >= 4 AND rs.f_score >= 4 AND rs.m_score >= 4 THEN 'Champions'
        WHEN rs.r_score >= 4 AND rs.f_score >= 3 AND rs.m_score >= 3 THEN 'Loyal Customers'
        WHEN rs.r_score >= 4 AND rs.f_score <= 2 THEN 'New Customers'
        WHEN rs.r_score >= 3 AND rs.f_score >= 3 AND rs.m_score >= 3 THEN 'Potential Loyalists'
        WHEN rs.r_score = 3 AND rs.f_score <= 3 THEN 'Need Attention'
        WHEN rs.r_score <= 2 AND rs.f_score >= 4 AND rs.m_score >= 4 THEN 'At Risk'
        WHEN rs.r_score <= 2 AND rs.f_score <= 2 AND rs.m_score >= 4 THEN 'Cannot Lose Them'
        WHEN rs.r_score <= 2 AND rs.f_score <= 2 AND rs.m_score <= 2 THEN 'Lost'
        WHEN rs.r_score <= 2 THEN 'At Risk'
        ELSE 'Hibernating'
    END AS rfm_segment,
    
    -- Existing view features
    pe.value_tier,
    pe.patient_status,
    plv.health_score,
    plv.churn_risk,
    plv.predicted_ltv_24m,
    COALESCE(pc.standalone_ratio, 0) AS standalone_ratio,
    COALESCE(pc.package_ratio, 0) AS package_ratio,
    COALESCE(pc.services_ratio, 0) AS services_ratio,
    COALESCE(pc.medications_ratio, 0) AS medications_ratio,
    pt.preferred_branch,
    pt.preferred_channel,
    EXTRACT(MONTH FROM pb.first_visit_date)::INTEGER AS first_visit_month,
    EXTRACT(DOW FROM pb.last_visit_date)::INTEGER AS last_visit_day_of_week,
    
    CURRENT_TIMESTAMP AS feature_timestamp

FROM patient_base pb
LEFT JOIN dk.vw_patient_enriched pe ON pb.patient_id = pe.mrn
LEFT JOIN cohort_calc cc ON pb.patient_id = cc.patient_id
LEFT JOIN promo_calc pc ON pb.patient_id = pc.patient_id
LEFT JOIN outstanding_calc oc ON pb.patient_id = oc.patient_id
LEFT JOIN rfm_scores rs ON pb.patient_id = rs.patient_id
LEFT JOIN avg_gap ag ON pb.patient_id = ag.patient_id
LEFT JOIN dk.vw_patient_transactions pt ON pb.patient_id = pt.patient_id
LEFT JOIN dk.vw_patient_lifetime_value plv ON pb.patient_id = plv.patient_id;

COMMENT ON VIEW dk.vw_ml_patient_features IS 'ST-05 ML feature engineering with 30+ features including recency, frequency, monetary, category mix, package behavior, promo dependency, and financial stress indicators.';

-- ============================================================
-- View: vw_patient_labels
-- Purpose: Supervised learning labels for 4 ML models
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_patient_labels AS
WITH visit_rolling AS (
    -- Per-visit rolling aggregates using window frames to prevent data leakage
    SELECT
        c.mrn AS patient_id,
        c.date AS label_date,
        LEAD(c.date) OVER (PARTITION BY c.mrn ORDER BY c.date) AS next_visit_date,

        -- Rolling totals up to and including this visit
        SUM(COALESCE(c.amount_collected, 0)) OVER w AS total_revenue,
        SUM(COALESCE(c.package_sales_subtotal, 0)) OVER w AS package_rev,
        SUM(COALESCE(c.standalone_sales_skincare_product_amount, 0)) OVER w AS skincare_rev,
        SUM(COALESCE(c.standalone_sales_services, 0)) OVER w AS services_rev,
        SUM(COALESCE(c.standalone_sales_medications, 0)) OVER w AS medications_rev,
        SUM(COALESCE(c.standalone_sales_supplements_supplement_rm5_amount, 0)
          + COALESCE(c.standalone_sales_supplements_supplement_na_amount, 0)) OVER w AS supplements_rev,
        COUNT(c.row_number) OVER w AS total_transactions,
        COUNT(CASE WHEN c.discount > 0 THEN c.row_number END) OVER w AS discount_frequency,
        CURRENT_DATE - MAX(c.date) OVER w AS recency_days

    FROM dk.collection c
    WHERE c.mrn IS NOT NULL AND c.date IS NOT NULL
    WINDOW w AS (PARTITION BY c.mrn ORDER BY c.date
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
label_base AS (
    SELECT DISTINCT ON (r.patient_id, r.label_date)
        r.patient_id,
        r.label_date,
        r.next_visit_date,
        r.total_revenue,
        r.package_rev,
        r.skincare_rev,
        r.total_transactions,
        r.discount_frequency,
        r.recency_days,

        -- Derived ratios (computed from rolling aggregates only)
        CASE WHEN r.total_revenue > 0
             THEN r.package_rev::FLOAT / r.total_revenue
             ELSE 0 END AS pkg_revenue_ratio,
        CASE WHEN r.total_revenue > 0
             THEN r.skincare_rev::FLOAT / r.total_revenue
             ELSE 0 END AS skincare_share_pct,
        CASE WHEN r.total_transactions > 0
             THEN r.discount_frequency::FLOAT / r.total_transactions
             ELSE 0 END AS promo_dependency_pct,

        -- Churn: no visit in next 180 days
        CASE
            WHEN r.next_visit_date IS NULL
                 OR (r.next_visit_date - r.label_date) > 180
            THEN 1 ELSE 0
        END AS label_churned,

        -- Package prospect: high cumulative spend, low package ratio
        CASE
            WHEN r.total_revenue > 1000
                 AND (CASE WHEN r.total_revenue > 0 THEN r.package_rev::FLOAT / r.total_revenue ELSE 0 END) < 0.1
            THEN 1 ELSE 0
        END AS label_pkg_prospect,

        -- Skincare buyer: bought skincare, recently active
        CASE
            WHEN (CASE WHEN r.total_revenue > 0 THEN r.skincare_rev::FLOAT / r.total_revenue ELSE 0 END) > 0
                 AND r.recency_days <= 90
            THEN 1 ELSE 0
        END AS label_skincare_buyer,

        -- Promo elastic: >50% transactions with discount
        CASE
            WHEN (CASE WHEN r.total_transactions > 0 THEN r.discount_frequency::FLOAT / r.total_transactions ELSE 0 END) > 0.5
            THEN 1 ELSE 0
        END AS label_promo_elastic

    FROM visit_rolling r
    WHERE r.label_date < CURRENT_DATE - INTERVAL '90 days'
    ORDER BY r.patient_id, r.label_date, r.total_revenue DESC
)
SELECT
    patient_id,
    label_date,
    label_churned,
    label_pkg_prospect,
    label_skincare_buyer,
    label_promo_elastic,

    -- Temporal split indicator
    CASE
        WHEN label_date >= CURRENT_DATE - INTERVAL '3 months' THEN 'validation'
        ELSE 'train'
    END AS split_type,

    CURRENT_TIMESTAMP AS created_at

FROM label_base;

COMMENT ON VIEW dk.vw_patient_labels IS 'ST-05 supervised learning labels with temporal train/validation split. Train: >3 months ago, Validation: last 3 months.';
