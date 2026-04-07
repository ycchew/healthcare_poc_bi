"""
ST-03: Patient Intelligence
Test suite for patient_analytics.py module.

To run tests:
    # Run all unit tests (no database required)
    pytest test_patient_analytics.py -v

    # Run specific test classes
    pytest test_patient_analytics.py::TestPatientAnalyticsManager -v
    pytest test_patient_analytics.py::TestGeneratePatientReport -v

    # Run integration tests (requires database connection)
    pytest test_patient_analytics.py::TestIntegration -v -m integration
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv

    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

DB_ENV_VARS = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
DB_ENV_CONFIGURED = all(os.getenv(var) for var in DB_ENV_VARS)

sys.path.insert(0, str(Path(__file__).parent))
from patient_analytics import (
    PatientAnalyticsManager,
    generate_patient_report,
)


@pytest.fixture
def mock_db_manager():
    manager = Mock()
    manager.execute_query = Mock(return_value=pd.DataFrame())
    manager.get_connection = MagicMock()
    return manager


@pytest.fixture
def sample_patient_risk_df():
    return pd.DataFrame(
        {
            "mrn": ["P001", "P002", "P003", "P004"],
            "patient_name": ["Patient A", "Patient B", "Patient C", "Patient D"],
            "risk_status": ["ACTIVE", "AT RISK", "HIGH RISK", "LOST"],
            "last_visit_date": [
                datetime.now() - timedelta(days=5),
                datetime.now() - timedelta(days=25),
                datetime.now() - timedelta(days=55),
                datetime.now() - timedelta(days=100),
            ],
            "days_since_visit": [5, 25, 55, 100],
            "total_lifetime_value": [5000.0, 3000.0, 2000.0, 1000.0],
            "branch": ["Branch_A", "Branch_A", "Branch_B", "Branch_B"],
        }
    )


@pytest.fixture
def sample_rfm_df():
    return pd.DataFrame(
        {
            "mrn": ["P001", "P002", "P003"],
            "patient_name": ["Patient A", "Patient B", "Patient C"],
            "recency_days": [5, 30, 60],
            "frequency": [12, 8, 4],
            "monetary": [6000.0, 4000.0, 2000.0],
            "r_score": [5, 4, 2],
            "f_score": [5, 3, 2],
            "m_score": [5, 4, 2],
            "rfm_segment": ["Champions", "Loyal Customers", "At Risk"],
            "rfm_value": [15, 11, 6],
            "total_lifetime_value": [6000.0, 4000.0, 2000.0],
            "branch": ["Branch_A", "Branch_A", "Branch_B"],
        }
    )


@pytest.fixture
def sample_cohort_df():
    return pd.DataFrame(
        {
            "cohort_month": ["2024-01", "2024-01", "2024-01", "2024-02"],
            "months_since_signup": [0, 1, 3, 0],
            "cohort_size": [100, 100, 100, 80],
            "active_patients": [100, 95, 85, 80],
            "retention_rate_pct": [100.0, 95.0, 85.0, 100.0],
            "cumulative_revenue": [50000.0, 95000.0, 170000.0, 40000.0],
        }
    )


@pytest.fixture
def sample_ltv_df():
    return pd.DataFrame(
        {
            "mrn": ["P001", "P002", "P003"],
            "frequency": [12.0, 8.0, 4.0],
            "recency": [30, 60, 120],
            "T": [365, 300, 200],
            "monetary_value": [500.0, 500.0, 500.0],
            "predicted_purchases_next_90d": [3.0, 2.0, 1.0],
            "predicted_avg_order_value": [500.0, 500.0, 500.0],
            "predicted_clv_12m": [6000.0, 4000.0, 2000.0],
            "predicted_clv_24m": [12000.0, 8000.0, 4000.0],
            "probability_alive": [0.95, 0.85, 0.70],
            "ltv_segment": ["High", "Medium", "Low"],
        }
    )


@pytest.fixture
def sample_dashboard_dict():
    return {
        "total_patients": 1000,
        "active_patients": 800,
        "at_risk_patients": 100,
        "high_risk_patients": 50,
        "lost_patients": 50,
        "new_patients": 50,
        "total_revenue": 500000.0,
        "avg_revenue_per_patient": 500.0,
        "avg_days_since_visit": 45.0,
        "active_pct": 80.0,
        "at_risk_pct": 10.0,
        "high_risk_pct": 5.0,
        "lost_pct": 5.0,
        "patient_base_health_score": 75,
        "generated_at": "2024-01-15",
    }


# ============================================================================
# Test PatientAnalyticsManager
# ============================================================================


class TestPatientAnalyticsManager:
    """Test PatientAnalyticsManager class."""

    def test_initialization_default(self, mock_db_manager):
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        assert manager.db is not None

    def test_get_followup_d3_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "patient_name": ["Patient A"],
                "mrn": ["P001"],
                "followup_status": ["DUE FOR CALLBACK"],
                "last_visit_date": [datetime.now() - timedelta(days=3)],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_followup_d3(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)
        assert "followup_status" in result.columns

    def test_get_followup_d3_all_branches(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "patient_name": ["Patient A", "Patient B"],
                "mrn": ["P001", "P002"],
                "followup_status": ["DUE FOR CALLBACK", "DUE FOR CALLBACK"],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_followup_d3()
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2

    def test_get_patient_risk_summary_with_filter(
        self, mock_db_manager, sample_patient_risk_df
    ):
        mock_db_manager.execute_query.return_value = sample_patient_risk_df[
            sample_patient_risk_df["risk_status"] == "ACTIVE"
        ]
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_patient_risk_summary(risk_status="ACTIVE")
        assert isinstance(result, pd.DataFrame)
        assert all(result["risk_status"] == "ACTIVE")

    def test_get_patient_risk_summary_with_branch(
        self, mock_db_manager, sample_patient_risk_df
    ):
        mock_db_manager.execute_query.return_value = sample_patient_risk_df[
            sample_patient_risk_df["branch"] == "Branch_A"
        ]
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_patient_risk_summary(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)
        assert all(result["branch"] == "Branch_A")

    def test_get_risk_distribution(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "risk_status": ["ACTIVE", "AT RISK", "HIGH RISK", "LOST"],
                "patient_count": [800, 100, 50, 50],
                "avg_ltv": [5000.0, 3000.0, 2000.0, 1000.0],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_risk_distribution()
        assert isinstance(result, pd.DataFrame)
        assert "risk_status" in result.columns
        assert len(result) == 4

    def test_get_rfm_segmentation_with_segment(self, mock_db_manager, sample_rfm_df):
        mock_db_manager.execute_query.return_value = sample_rfm_df[
            sample_rfm_df["rfm_segment"] == "Champions"
        ]
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_rfm_segmentation(segment="Champions")
        assert isinstance(result, pd.DataFrame)
        assert all(result["rfm_segment"] == "Champions")

    def test_get_rfm_segmentation_with_branch(self, mock_db_manager, sample_rfm_df):
        mock_db_manager.execute_query.return_value = sample_rfm_df[
            sample_rfm_df["branch"] == "Branch_A"
        ]
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_rfm_segmentation(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)
        assert all(result["branch"] == "Branch_A")

    def test_get_rfm_summary(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "rfm_segment": ["Champions", "Loyal Customers", "At Risk"],
                "patient_count": [100, 200, 150],
                "avg_ltv": [8000.0, 5000.0, 2500.0],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_rfm_summary()
        assert isinstance(result, pd.DataFrame)
        assert "rfm_segment" in result.columns

    def test_get_cohort_retention_with_cohort_month(
        self, mock_db_manager, sample_cohort_df
    ):
        mock_db_manager.execute_query.return_value = sample_cohort_df[
            sample_cohort_df["cohort_month"] == "2024-01"
        ]
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_cohort_retention(cohort_month="2024-01")
        assert isinstance(result, pd.DataFrame)
        assert all(result["cohort_month"] == "2024-01")

    def test_get_cohort_retention_with_months_since(
        self, mock_db_manager, sample_cohort_df
    ):
        mock_db_manager.execute_query.return_value = sample_cohort_df[
            sample_cohort_df["months_since_signup"] == 0
        ]
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_cohort_retention(months_since=0)
        assert isinstance(result, pd.DataFrame)
        assert all(result["months_since_signup"] == 0)

    def test_get_cohort_summary(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "cohort_month": ["2024-01", "2024-02"],
                "cohort_size": [100, 80],
                "m0_retention": [100.0, 100.0],
                "m3_retention": [85.0, None],
                "total_revenue": [170000.0, 40000.0],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_cohort_summary()
        assert isinstance(result, pd.DataFrame)
        assert "cohort_month" in result.columns

    def test_get_visit_frequency_distribution_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "visit_frequency_segment": ["Frequent", "Regular", "Occasional"],
                "patient_count": [100, 200, 300],
                "avg_lifetime_value": [8000.0, 5000.0, 2000.0],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_visit_frequency_distribution(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)

    def test_get_visit_frequency_distribution_all(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "visit_frequency_segment": ["Frequent", "Regular", "Occasional"],
                "patient_count": [300, 500, 700],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_visit_frequency_distribution()
        assert isinstance(result, pd.DataFrame)

    def test_get_ltv_predictions_with_segment(self, mock_db_manager, sample_ltv_df):
        mock_db_manager.execute_query.return_value = sample_ltv_df[
            sample_ltv_df["ltv_segment"] == "High"
        ]
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_ltv_predictions(segment="High")
        assert isinstance(result, pd.DataFrame)
        assert all(result["ltv_segment"] == "High")

    def test_get_ltv_predictions_with_min_probability(
        self, mock_db_manager, sample_ltv_df
    ):
        mock_db_manager.execute_query.return_value = sample_ltv_df[
            sample_ltv_df["probability_alive"] >= 0.90
        ]
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_ltv_predictions(min_probability_alive=0.90)
        assert isinstance(result, pd.DataFrame)
        assert all(result["probability_alive"] >= 0.90)

    def test_get_ltv_summary(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "ltv_segment": ["High", "Medium", "Low"],
                "patient_count": [100, 300, 600],
                "avg_clv_24m": [12000.0, 7000.0, 3000.0],
                "avg_prob_alive": [0.95, 0.85, 0.70],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_ltv_summary()
        assert isinstance(result, pd.DataFrame)
        assert "ltv_segment" in result.columns

    def test_get_executive_dashboard(self, mock_db_manager, sample_dashboard_dict):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            [sample_dashboard_dict]
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_executive_dashboard()
        assert isinstance(result, dict)
        assert "total_patients" in result
        assert "churn_rate_pct" in result
        assert result["active_patients"] == 800

    def test_get_executive_dashboard_empty(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_executive_dashboard()
        assert result == {}

    def test_check_data_freshness_ok(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "latest_date": [datetime.now().date()],
                "days_behind": [0],
                "total_patients": [1000],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "OK"
        assert result["days_behind"] == 0

    def test_check_data_freshness_warning(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "latest_date": [datetime.now().date() - timedelta(days=2)],
                "days_behind": [2],
                "total_patients": [1000],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "WARNING"
        assert result["days_behind"] == 2

    def test_check_data_freshness_critical(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "latest_date": [datetime.now().date() - timedelta(days=5)],
                "days_behind": [5],
                "total_patients": [1000],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "CRITICAL"
        assert result["days_behind"] == 5

    def test_check_data_freshness_empty(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "ERROR"
        assert "message" in result

    def test_refresh_patient_intelligence(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "view_name": ["mvw_patient_risk", "mvw_patient_rfm"],
                "status": ["SUCCESS", "SUCCESS"],
            }
        )
        manager = PatientAnalyticsManager(db_manager=mock_db_manager)
        result = manager.refresh_patient_intelligence()
        assert isinstance(result, pd.DataFrame)
        assert "view_name" in result.columns


# ============================================================================
# Test Convenience Functions
# ============================================================================


class TestGeneratePatientReport:
    """Test module-level convenience functions."""

    def test_generate_patient_report_executive(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "total_patients": [1000],
                "active_patients": [800],
                "at_risk_patients": [100],
                "high_risk_patients": [50],
                "lost_patients": [50],
                "total_revenue": [500000.00],
                "avg_revenue_per_patient": [500.00],
                "avg_days_since_visit": [25.0],
                "new_patients": [100],
                "active_patients": [800],
                "lost_pct": [5.0],
                "patient_base_health_score": [75],
                "generated_at": [datetime.now()],
            }
        )
        with patch("patient_analytics.get_db_manager", return_value=mock_db_manager):
            result = generate_patient_report(report_type="executive")
            assert isinstance(result, dict)
            assert "total_patients" in result

    def test_generate_patient_report_risk(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "risk_status": ["ACTIVE", "AT RISK"],
                "patient_count": [800, 100],
            }
        )
        with patch("patient_analytics.get_db_manager", return_value=mock_db_manager):
            result = generate_patient_report(report_type="risk")
            assert isinstance(result, pd.DataFrame)
            assert "risk_status" in result.columns

    def test_generate_patient_report_rfm(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "rfm_segment": ["Champions"],
                "patient_count": [100],
            }
        )
        with patch("patient_analytics.get_db_manager", return_value=mock_db_manager):
            result = generate_patient_report(report_type="rfm")
            assert isinstance(result, pd.DataFrame)
            assert "rfm_segment" in result.columns

    def test_generate_patient_report_ltv(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "ltv_segment": ["High"],
                "avg_clv_24m": [12000.0],
            }
        )
        with patch("patient_analytics.get_db_manager", return_value=mock_db_manager):
            result = generate_patient_report(report_type="ltv")
            assert isinstance(result, pd.DataFrame)
            assert "ltv_segment" in result.columns

    def test_generate_patient_report_cohort(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "cohort_month": ["2024-01"],
                "m3_retention": [85.0],
            }
        )
        with patch("patient_analytics.get_db_manager", return_value=mock_db_manager):
            result = generate_patient_report(report_type="cohort")
            assert isinstance(result, pd.DataFrame)
            assert "cohort_month" in result.columns

    def test_generate_patient_report_invalid_type(self, mock_db_manager):
        with patch("patient_analytics.get_db_manager", return_value=mock_db_manager):
            with pytest.raises(ValueError):
                generate_patient_report(report_type="invalid")


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.skipif(
    not DB_ENV_CONFIGURED,
    reason="Database environment variables not configured",
)
class TestIntegration:
    """Integration tests requiring live database connection."""

    def test_real_patient_analytics_manager(self):
        """Test real PatientAnalyticsManager with live database."""
        manager = PatientAnalyticsManager()
        freshness = manager.check_data_freshness()
        assert "status" in freshness
        assert freshness["status"] in ["OK", "WARNING", "CRITICAL", "ERROR"]

    def test_real_executive_dashboard(self):
        """Test real executive dashboard query."""
        manager = PatientAnalyticsManager()
        dashboard = manager.get_executive_dashboard()
        assert isinstance(dashboard, dict)
        assert "total_patients" in dashboard

    def test_real_risk_distribution(self):
        """Test real risk distribution query."""
        manager = PatientAnalyticsManager()
        risk = manager.get_risk_distribution()
        assert isinstance(risk, pd.DataFrame)

    def test_real_rfm_summary(self):
        """Test real RFM summary query."""
        manager = PatientAnalyticsManager()
        rfm = manager.get_rfm_summary()
        assert isinstance(rfm, pd.DataFrame)

    def test_real_ltv_summary(self):
        """Test real LTV summary query."""
        manager = PatientAnalyticsManager()
        ltv = manager.get_ltv_summary()
        assert isinstance(ltv, pd.DataFrame)


if __name__ == "__main__":
    try:
        import pytest

        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        print("pytest not installed. Install with: pip install pytest pytest-mock")
        print("Running basic smoke tests...")

        # Basic smoke tests
        print("\nTesting PatientAnalyticsManager initialization...")
        mock_db = Mock()
        manager = PatientAnalyticsManager(db_manager=mock_db)
        print("  PatientAnalyticsManager initialized successfully")

        print("\nAll smoke tests passed!")
