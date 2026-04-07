"""
ST-03: Patient Intelligence
Python module for patient analytics, RFM segmentation, and cohort analysis
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from database import execute_query


def get_patient_visit_patterns(mrn: Optional[str] = None) -> pd.DataFrame:
    """Get patient visit patterns and frequency analysis."""
    query = "SELECT * FROM dk.vw_patient_visit_patterns WHERE 1=1"
    if mrn:
        query += f" AND mrn = '{mrn}'"
    query += " ORDER BY total_visits DESC"
    return execute_query(query)


def get_cohort_analysis(cohort_month: Optional[str] = None) -> pd.DataFrame:
    """Get cohort retention analysis."""
    query = "SELECT * FROM dk.vw_patient_cohort_analysis WHERE 1=1"
    if cohort_month:
        query += f" AND cohort_month = '{cohort_month}'"
    query += " ORDER BY cohort_month, period_number"
    return execute_query(query)


def get_rfm_segments(segment: Optional[str] = None) -> pd.DataFrame:
    """Get RFM segments with recommendations."""
    query = "SELECT * FROM dk.vw_rfm_with_recommendations WHERE 1=1"
    if segment:
        query += f" AND rfm_segment = '{segment}'"
    query += " ORDER BY engagement_priority, monetary DESC"
    return execute_query(query)


def get_ltv_predictions(risk_level: Optional[str] = None) -> pd.DataFrame:
    """Get patient LTV predictions and churn risk."""
    query = "SELECT * FROM dk.vw_patient_ltv_prediction WHERE 1=1"
    if risk_level:
        query += f" AND churn_risk = '{risk_level}'"
    query += " ORDER BY predicted_ltv_24m DESC"
    return execute_query(query)


def get_d3_followup_list() -> pd.DataFrame:
    """Get D+3 follow-up list with enhanced context."""
    return execute_query(
        "SELECT * FROM dk.vw_d3_followup_enhanced ORDER BY followup_priority"
    )


def analyze_rfm_distribution() -> pd.DataFrame:
    """Analyze RFM segment distribution."""
    query = """
    SELECT 
        rfm_segment,
        COUNT(*) AS patient_count,
        ROUND(AVG(monetary), 2) AS avg_monetary,
        ROUND(AVG(frequency), 2) AS avg_frequency,
        ROUND(AVG(recency), 0) AS avg_recency,
        MIN(engagement_priority) AS priority
    FROM dk.vw_rfm_with_recommendations
    GROUP BY rfm_segment
    ORDER BY priority
    """
    return execute_query(query)


def calculate_cohort_retention_rate(cohort_month: str, period: int = 6) -> float:
    """Calculate retention rate for a specific cohort at given period."""
    query = f"""
    SELECT retention_rate_pct 
    FROM dk.vw_patient_cohort_analysis
    WHERE cohort_month = '{cohort_month}'::TIMESTAMP
      AND period_number = {period}
    """
    df = execute_query(query)
    if df.empty:
        return 0.0
    return df["retention_rate_pct"].iloc[0] or 0.0


def identify_at_risk_patients(min_ltv: float = 1000) -> pd.DataFrame:
    """Identify patients at risk of churning with high LTV."""
    query = f"""
    SELECT 
        mrn,
        patient_name,
        phone,
        email,
        rfm_segment,
        predicted_ltv_24m,
        churn_risk,
        days_since_last_visit,
        recommended_action,
        preferred_channel
    FROM dk.vw_rfm_with_recommendations r
    JOIN dk.vw_patient_ltv_prediction l ON r.mrn = l.mrn
    JOIN dk.vw_patient_visit_patterns v ON r.mrn = v.mrn
    WHERE r.rfm_segment IN ('At Risk', 'Cannot Lose Them', 'Hibernating')
      AND l.predicted_ltv_24m >= {min_ltv}
    ORDER BY predicted_ltv_24m DESC
    """
    return execute_query(query)


def get_patient_journey(mrn: str) -> pd.DataFrame:
    """Get complete patient journey/transaction history."""
    query = f"""
    SELECT 
        transaction_date,
        branch_name,
        doctor_name,
        product_name,
        category,
        net_amount,
        is_package,
        package_name
    FROM dk.mvw_transaction_flat
    WHERE mrn = '{mrn}'
    ORDER BY transaction_date
    """
    return execute_query(query)


def generate_campaign_list(
    segment: Optional[str] = None, min_ltv: float = 0, max_recency_days: int = 90
) -> pd.DataFrame:
    """Generate campaign target list based on criteria."""
    query = """
    SELECT 
        pi.mrn,
        pi.name,
        pi.phone,
        pi.email,
        pi.rfm_segment,
        pi.ltv_segment,
        pi.predicted_annual_ltv,
        pi.visit_frequency_segment,
        pi.loyalty_segment,
        pi.churn_risk,
        pi.value_tier,
        r.recommended_action,
        r.preferred_channel
    FROM dk.mvw_patient_intelligence pi
    JOIN dk.vw_rfm_with_recommendations r ON pi.mrn = r.mrn
    WHERE pi.days_since_last_visit <= {}
      AND pi.predicted_annual_ltv >= {}
    """.format(max_recency_days, min_ltv)

    if segment:
        query += f" AND pi.rfm_segment = '{segment}'"

    query += " ORDER BY pi.predicted_annual_ltv DESC"

    return execute_query(query)


def calculate_rfm_scores(mrn: str) -> Dict:
    """Calculate individual RFM scores for a patient."""
    query = f"""
    SELECT r_score, f_score, m_score, rfm_segment
    FROM dk.mvw_patient_rfm
    WHERE mrn = '{mrn}'
    """
    df = execute_query(query)
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


def export_patient_segments(
    output_path: str = "./docs/output/patient_segments.xlsx",
) -> str:
    """Export patient segments to Excel."""
    rfm = analyze_rfm_distribution()
    ltv = get_ltv_predictions()
    at_risk = identify_at_risk_patients()
    d3_list = get_d3_followup_list()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        rfm.to_excel(writer, sheet_name="RFM Distribution", index=False)
        ltv.to_excel(writer, sheet_name="LTV Predictions", index=False)
        at_risk.to_excel(writer, sheet_name="At Risk Patients", index=False)
        d3_list.to_excel(writer, sheet_name="D+3 Follow-up", index=False)

    return output_path


if __name__ == "__main__":
    print("ST-03 Patient Intelligence Module")
    print("=" * 50)

    rfm_dist = analyze_rfm_distribution()
    print("\nRFM Segment Distribution:")
    print(
        rfm_dist[["rfm_segment", "patient_count", "avg_monetary"]].to_string(
            index=False
        )
    )

    at_risk = identify_at_risk_patients(min_ltv=1000)
    print(f"\nHigh-Value At-Risk Patients: {len(at_risk)}")
