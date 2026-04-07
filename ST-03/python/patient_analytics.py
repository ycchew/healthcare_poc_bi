"""
ST-03: Patient Intelligence
Database utilities and analytics functions for patient data analysis.
"""

import os
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

import pandas as pd
import numpy as np
from sqlalchemy import text

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import importlib.util

db_path = Path(__file__).parent.parent.parent / "ST-01" / "python" / "database.py"
spec = importlib.util.spec_from_file_location("database", db_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load database module from {db_path}")
database_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database_module)
DatabaseManager = database_module.DatabaseManager
get_db_manager = database_module.get_db_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PatientAnalyticsManager:
    """Manager for patient analytics queries and reports."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or get_db_manager()

    def get_followup_d3(self, branch: Optional[str] = None) -> pd.DataFrame:
        """
        Get D+3 follow-up tracker for callback scheduling.

        Args:
            branch: Specific branch, or None for all

        Returns:
            DataFrame with patients due for D+3 callback
        """
        if branch:
            query = """
                SELECT 
                    patient_name,
                    patient_contact,
                    mrn,
                    last_visit_date,
                    days_since_visit,
                    last_branch,
                    last_doctor,
                    last_service_group,
                    last_payment_method,
                    followup_status,
                    total_lifetime_value,
                    visit_count
                FROM dk.vw_followup_d3
                WHERE last_branch = :branch
                  AND followup_status = 'DUE FOR CALLBACK'
                ORDER BY last_visit_date DESC
            """
            return self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    patient_name,
                    patient_contact,
                    mrn,
                    last_visit_date,
                    days_since_visit,
                    last_branch,
                    last_doctor,
                    last_service_group,
                    last_payment_method,
                    followup_status,
                    total_lifetime_value,
                    visit_count
                FROM dk.vw_followup_d3
                WHERE followup_status = 'DUE FOR CALLBACK'
                ORDER BY last_visit_date DESC
            """
            return self.db.execute_query(query)

    def get_patient_risk_summary(
        self, risk_status: Optional[str] = None, branch: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get patient risk classification summary.

        Args:
            risk_status: Filter by 'ACTIVE', 'AT RISK', 'HIGH RISK', or 'LOST'
            branch: Specific branch, or None for all

        Returns:
            DataFrame with patient risk classifications
        """
        base_query = """
            SELECT 
                mrn,
                patient_name,
                risk_status,
                last_visit_date,
                days_since_visit,
                days_until_inactive,
                days_until_lost,
                visit_count,
                total_lifetime_value,
                total_revenue_6m,
                branch,
                last_doctor,
                last_service_group,
                days_since_visit_category
            FROM dk.vw_patient_risk
            WHERE 1=1
        """
        params = {}

        if risk_status:
            base_query += " AND risk_status = :risk_status"
            params["risk_status"] = risk_status

        if branch:
            base_query += " AND branch = :branch"
            params["branch"] = branch

        base_query += " ORDER BY total_lifetime_value DESC"

        return self.db.execute_query(base_query, params)

    def get_risk_distribution(self) -> pd.DataFrame:
        """
        Get summary of patient risk distribution.

        Returns:
            DataFrame with risk status counts and values
        """
        query = """
            SELECT 
                patient_status AS risk_status,
                COUNT(*) AS patient_count,
                ROUND(AVG(total_revenue)::NUMERIC, 2) AS avg_ltv,
                ROUND(SUM(total_revenue)::NUMERIC, 2) AS total_ltv,
                ROUND(AVG(days_since_last_visit)::NUMERIC, 1) AS avg_days_since_visit
            FROM dk.vw_patient_risk
            GROUP BY patient_status
            ORDER BY 
                CASE patient_status 
                    WHEN 'ACTIVE' THEN 1
                    WHEN 'AT RISK' THEN 2
                    WHEN 'HIGH RISK' THEN 3
                    WHEN 'LOST' THEN 4
                END
        """
        return self.db.execute_query(query)

    def get_rfm_segmentation(
        self, segment: Optional[str] = None, branch: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get RFM segmentation with NTILE scoring.

        Args:
            segment: Filter by segment name (e.g., 'Champions', 'At Risk')
            branch: Specific branch, or None for all

        Returns:
            DataFrame with RFM scores and segments
        """
        base_query = """
            SELECT 
                patient_id AS mrn,
                patient_id AS patient_name,
                recency_days,
                frequency,
                monetary,
                r_score,
                f_score,
                m_score,
                rfm_segment,
                rfm_cell AS rfm_value,
                recency_days AS days_since_visit,
                monetary AS total_lifetime_value,
                frequency AS visit_count,
                NULL AS branch,
                last_visit_date,
                CASE WHEN frequency > 0 THEN ROUND((monetary / frequency)::NUMERIC, 2) ELSE 0 END AS avg_transaction_value
            FROM dk.vw_patient_rfm_ntile
            WHERE 1=1
        """
        params = {}

        if segment:
            base_query += " AND rfm_segment = :segment"
            params["segment"] = segment

        if branch:
            base_query += " AND branch = :branch"
            params["branch"] = branch

        base_query += " ORDER BY rfm_value DESC, total_lifetime_value DESC"

        return self.db.execute_query(base_query, params)

    def get_rfm_summary(self) -> pd.DataFrame:
        """
        Get summary statistics by RFM segment.

        Returns:
            DataFrame with segment-level RFM metrics
        """
        query = """
            SELECT 
                rfm_segment,
                COUNT(*) AS patient_count,
                ROUND(AVG(monetary)::NUMERIC, 2) AS avg_ltv,
                ROUND(SUM(monetary)::NUMERIC, 2) AS total_ltv,
                ROUND(AVG(r_score)::NUMERIC, 1) AS avg_r_score,
                ROUND(AVG(f_score)::NUMERIC, 1) AS avg_f_score,
                ROUND(AVG(m_score)::NUMERIC, 1) AS avg_m_score,
                ROUND(AVG(recency_days)::NUMERIC, 1) AS avg_recency_days,
                ROUND(AVG(frequency)::NUMERIC, 1) AS avg_frequency,
                CASE WHEN SUM(frequency) > 0 THEN ROUND((SUM(monetary) / SUM(frequency))::NUMERIC, 2) ELSE 0 END AS avg_transaction_value
            FROM dk.vw_patient_rfm_ntile
            GROUP BY rfm_segment
            ORDER BY total_ltv DESC
        """
        return self.db.execute_query(query)

    def get_cohort_retention(
        self, cohort_month: Optional[str] = None, months_since: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get cohort retention analysis.

        Args:
            cohort_month: Filter by cohort month (YYYY-MM)
            months_since: Filter by specific months since signup

        Returns:
            DataFrame with cohort retention data
        """
        base_query = """
            SELECT 
                cohort_month,
                months_since_signup,
                cohort_size,
                active_patients,
                retention_rate_pct,
                churned_patients,
                churn_rate_pct,
                cumulative_revenue,
                avg_revenue_per_patient,
                ltv_estimate
            FROM dk.mvw_cohort_retention
            WHERE 1=1
        """
        params = {}

        if cohort_month:
            base_query += " AND cohort_month = :cohort_month"
            params["cohort_month"] = cohort_month

        if months_since is not None:
            base_query += " AND months_since_signup = :months_since"
            params["months_since"] = months_since

        base_query += " ORDER BY cohort_month DESC, months_since_signup"

        return self.db.execute_query(base_query, params)

    def get_cohort_summary(self) -> pd.DataFrame:
        """
        Get cohort-level summary statistics.

        Returns:
            DataFrame with cohort summary metrics
        """
        query = """
            SELECT 
                cohort_month,
                cohort_size,
                MAX(CASE WHEN months_since_signup = 0 THEN retention_rate_pct END) AS m0_retention,
                MAX(CASE WHEN months_since_signup = 3 THEN retention_rate_pct END) AS m3_retention,
                MAX(CASE WHEN months_since_signup = 6 THEN retention_rate_pct END) AS m6_retention,
                MAX(CASE WHEN months_since_signup = 12 THEN retention_rate_pct END) AS m12_retention,
                MAX(CASE WHEN months_since_signup = 24 THEN retention_rate_pct END) AS m24_retention,
                SUM(cumulative_revenue) AS total_revenue,
                MAX(lt_v_estimate) AS final_ltv
            FROM dk.mvw_cohort_retention
            GROUP BY cohort_month, cohort_size
            ORDER BY cohort_month DESC
        """
        return self.db.execute_query(query)

    def get_visit_frequency_distribution(
        self, branch: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get visit frequency distribution analysis.

        Args:
            branch: Specific branch, or None for all

        Returns:
            DataFrame with visit frequency distribution
        """
        if branch:
            query = """
                SELECT 
                    branch,
                    visit_frequency_segment,
                    patient_count,
                    pct_of_patients,
                    avg_lifetime_value,
                    avg_visits_per_year,
                    avg_days_between_visits,
                    total_lifetime_value,
                    pct_of_total_revenue
                FROM dk.vw_visit_frequency_summary
                WHERE branch = :branch
                ORDER BY avg_visits_per_year DESC
            """
            return self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    visit_frequency_segment,
                    SUM(patient_count) AS patient_count,
                    ROUND(AVG(pct_of_patients)::NUMERIC, 2) AS avg_pct_of_patients,
                    ROUND(AVG(avg_lifetime_value)::NUMERIC, 2) AS avg_ltv,
                    ROUND(AVG(avg_visits_per_year)::NUMERIC, 1) AS avg_visits_per_year,
                    SUM(total_lifetime_value) AS total_revenue
                FROM dk.vw_visit_frequency_summary
                GROUP BY visit_frequency_segment
                ORDER BY avg_visits_per_year DESC
            """
            return self.db.execute_query(query)

    def get_ltv_predictions(
        self,
        segment: Optional[str] = None,
        min_probability_alive: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Get CLTV predictions from the materialized view.

        Args:
            segment: Filter by LTV segment
            min_probability_alive: Minimum probability alive threshold

        Returns:
            DataFrame with CLTV predictions
        """
        base_query = """
            SELECT 
                mrn,
                frequency,
                recency,
                T,
                monetary_value,
                predicted_purchases_next_90d,
                predicted_avg_order_value,
                predicted_clv_12m,
                predicted_clv_24m,
                probability_alive,
                ltv_segment,
                model_version,
                calculated_at
            FROM dk.mvw_patient_ltv_predictions
            WHERE 1=1
        """
        params = {}

        if segment:
            base_query += " AND ltv_segment = :segment"
            params["segment"] = segment

        if min_probability_alive is not None:
            base_query += " AND probability_alive >= :min_prob"
            params["min_prob"] = min_probability_alive

        base_query += " ORDER BY predicted_clv_24m DESC"

        return self.db.execute_query(base_query, params)

    def get_ltv_summary(self) -> pd.DataFrame:
        """
        Get LTV segment summary.

        Returns:
            DataFrame with LTV segment statistics
        """
        query = """
            SELECT 
                ltv_segment,
                COUNT(*) AS patient_count,
                ROUND(AVG(frequency)::NUMERIC, 2) AS avg_frequency,
                ROUND(AVG(predicted_clv_12m)::NUMERIC, 2) AS avg_clv_12m,
                ROUND(AVG(predicted_clv_24m)::NUMERIC, 2) AS avg_clv_24m,
                ROUND(SUM(predicted_clv_24m)::NUMERIC, 2) AS total_predicted_clv,
                ROUND(AVG(probability_alive)::NUMERIC, 3) AS avg_prob_alive,
                ROUND(AVG(predicted_purchases_next_90d)::NUMERIC, 2) AS avg_purchases_90d
            FROM dk.mvw_patient_ltv_predictions
            GROUP BY ltv_segment
            ORDER BY avg_clv_24m DESC
        """
        return self.db.execute_query(query)

    def get_executive_dashboard(self) -> Dict[str, Any]:
        """
        Get executive patient dashboard summary.

        Returns:
            Dictionary with key patient intelligence KPIs
        """
        query = """
            SELECT 
                total_patients,
                active_patients,
                at_risk_patients,
                high_risk_patients,
                lost_patients,
                new_patients,
                total_revenue,
                avg_revenue_per_patient,
                avg_days_since_visit,
                active_pct,
                at_risk_pct,
                high_risk_pct,
                lost_pct,
                patient_base_health_score,
                generated_at
            FROM dk.vw_patient_dashboard
        """
        df = self.db.execute_query(query)

        if df.empty:
            return {}

        return {
            "total_patients": int(df.iloc[0]["total_patients"] or 0),
            "active_patients": int(df.iloc[0]["active_patients"] or 0),
            "at_risk_patients": int(df.iloc[0]["at_risk_patients"] or 0),
            "high_risk_patients": int(df.iloc[0]["high_risk_patients"] or 0),
            "lost_patients": int(df.iloc[0]["lost_patients"] or 0),
            "total_lifetime_value": float(df.iloc[0]["total_revenue"] or 0),
            "avg_lifetime_value": float(df.iloc[0]["avg_revenue_per_patient"] or 0),
            "avg_visit_frequency_days": float(df.iloc[0]["avg_days_since_visit"] or 0),
            "new_patients_this_month": int(df.iloc[0]["new_patients"] or 0),
            "returning_patients_this_month": int(df.iloc[0]["active_patients"] or 0),
            "churn_rate_pct": float(df.iloc[0]["lost_pct"] or 0),
            "avg_patient_satisfaction": float(
                df.iloc[0]["patient_base_health_score"] or 0
            ),
            "report_date": str(df.iloc[0]["generated_at"]),
        }

    def check_data_freshness(self) -> Dict[str, Any]:
        """
        Check freshness of patient intelligence data.

        Returns:
            Dictionary with freshness status
        """
        query = """
            SELECT 
                MAX(last_transaction_date) AS latest_date,
                CURRENT_DATE - MAX(last_transaction_date) AS days_behind,
                COUNT(*) AS total_patients
            FROM dk.vw_patient_risk
        """
        df = self.db.execute_query(query)

        if df.empty:
            return {"status": "ERROR", "message": "No data found"}

        latest_date = df.iloc[0]["latest_date"]
        days_behind = int(df.iloc[0]["days_behind"] or 0)

        status = (
            "OK" if days_behind <= 1 else "WARNING" if days_behind <= 3 else "CRITICAL"
        )

        return {
            "status": status,
            "latest_date": str(latest_date),
            "days_behind": days_behind,
            "total_patients": int(df.iloc[0]["total_patients"]),
        }

    def refresh_patient_intelligence(self) -> pd.DataFrame:
        """
        Refresh all patient intelligence materialized views.

        Returns:
            DataFrame with refresh status for each view
        """
        query = "SELECT * FROM dk.refresh_patient_intelligence_mvws()"
        return self.db.execute_query(query)


def generate_patient_report(
    report_type: str = "executive", output_format: str = "dataframe"
) -> Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]:
    """
    Generate a patient intelligence report.

    Args:
        report_type: Type of report ('executive', 'risk', 'rfm', 'ltv', 'cohort')
        output_format: 'dataframe' or 'dict'

    Returns:
        Report data
    """
    manager = PatientAnalyticsManager()

    if report_type == "executive":
        data = manager.get_executive_dashboard()
    elif report_type == "risk":
        data = manager.get_risk_distribution()
    elif report_type == "rfm":
        data = manager.get_rfm_summary()
    elif report_type == "ltv":
        data = manager.get_ltv_summary()
    elif report_type == "cohort":
        data = manager.get_cohort_summary()
    else:
        raise ValueError(f"Unknown report type: {report_type}")

    if output_format == "dict" and isinstance(data, pd.DataFrame):
        return data.to_dict(orient="records")  # type: ignore[return-value]
    return data


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    print("Patient Intelligence Report")
    print("=" * 60)

    manager = PatientAnalyticsManager()

    print("\n1. Executive Dashboard:")
    dashboard = manager.get_executive_dashboard()
    for key, value in dashboard.items():
        print(f"   {key}: {value}")

    print("\n2. Risk Distribution:")
    risk = manager.get_risk_distribution()
    print(risk.to_string(index=False))

    print("\n3. RFM Segmentation Summary:")
    rfm = manager.get_rfm_summary()
    print(rfm.to_string(index=False))

    print("\n4. Data Freshness:")
    freshness = manager.check_data_freshness()
    for key, value in freshness.items():
        print(f"   {key}: {value}")
