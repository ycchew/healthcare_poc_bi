"""
ST-04: Product & Package Performance Analytics
Test suite for product_analytics.py module.

To run tests:
    # Run all unit tests (no database required)
    pytest test_product_analytics.py -v

    # Run specific test classes
    pytest test_product_analytics.py::TestProductPerformance -v
    pytest test_product_analytics.py::TestPackageAnalytics -v
    pytest test_product_analytics.py::TestPaymentBehavior -v

    # Run integration tests (requires database connection)
    pytest test_product_analytics.py::TestIntegration -v -m integration
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
from product_analytics import (
    ProductAnalyticsManager,
    run_product_report,
)


@pytest.fixture
def mock_env_vars():
    env_vars = {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "test_db",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        yield env_vars


@pytest.fixture
def mock_db_manager():
    manager = Mock()
    manager.execute_query = Mock(return_value=pd.DataFrame())
    manager.get_connection = MagicMock()
    return manager


@pytest.fixture
def sample_skincare_df():
    return pd.DataFrame(
        {
            "branch": ["Branch_A", "Branch_A", "Branch_B"],
            "sales_channel": ["Walk-in", "Online", "Walk-in"],
            "month": [
                datetime(2024, 1, 1),
                datetime(2024, 2, 1),
                datetime(2024, 1, 1),
            ],
            "standalone_skincare": [10000.0, 12000.0, 8000.0],
            "package_skincare": [5000.0, 6000.0, 4000.0],
            "total_skincare": [15000.0, 18000.0, 12000.0],
            "skincare_units": [100, 120, 80],
            "avg_unit_price": [150.0, 150.0, 150.0],
            "discount_rate": [5.0, 5.5, 4.8],
            "transaction_count": [50, 60, 40],
        }
    )


@pytest.fixture
def sample_package_df():
    return pd.DataFrame(
        {
            "branch": ["Branch_A", "Branch_A", "Branch_B"],
            "month": [
                datetime(2024, 1, 1),
                datetime(2024, 2, 1),
                datetime(2024, 1, 1),
            ],
            "total_package_revenue": [50000.0, 55000.0, 45000.0],
            "pkg_services_amount": [25000.0, 28000.0, 22000.0],
            "pkg_services_pct": [50.0, 50.9, 48.9],
            "pkg_skincare_amount": [15000.0, 16000.0, 13000.0],
            "pkg_skincare_pct": [30.0, 29.1, 28.9],
            "pkg_medications_amount": [5000.0, 5500.0, 5000.0],
            "pkg_medications_pct": [10.0, 10.0, 11.1],
            "pkg_supplements_amount": [3000.0, 3500.0, 3000.0],
            "pkg_supplements_pct": [6.0, 6.4, 6.7],
            "pkg_other_amount": [2000.0, 2000.0, 2000.0],
            "pkg_other_pct": [4.0, 3.6, 4.4],
        }
    )


@pytest.fixture
def sample_stressed_buyers_df():
    return pd.DataFrame(
        {
            "mrn": ["MRN001", "MRN002", "MRN003"],
            "patient_name": ["John Doe", "Jane Smith", "Bob Lee"],
            "branch": ["Branch_A", "Branch_A", "Branch_B"],
            "outstanding_amount": [5000.0, 4500.0, 4000.0],
            "stress_level": ["HIGH", "HIGH", "MEDIUM"],
            "recent_spend_30d": [500.0, 300.0, 200.0],
            "recent_spend_90d": [1500.0, 1000.0, 800.0],
            "days_since_visit": [5, 10, 15],
            "risk_flag": ["HIGH", "HIGH", "MEDIUM"],
        }
    )


# ============================================================================
# Test Product Performance Methods
# ============================================================================


class TestProductPerformance:
    """Test product performance query methods."""

    def test_get_skincare_performance_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {"branch": ["Branch_A"], "total_skincare": [15000.0]}
        )
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_skincare_performance()
        assert isinstance(result, pd.DataFrame)
        mock_db_manager.execute_query.assert_called_once()

    def test_get_skincare_performance_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_skincare_performance(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)
        call_args = mock_db_manager.execute_query.call_args
        assert "Branch_A" in str(call_args)

    def test_get_skincare_performance_custom_months(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_skincare_performance(months=6)
        call_args = mock_db_manager.execute_query.call_args
        assert "months" in str(call_args)

    def test_get_supplements_breakdown_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_supplements_breakdown()
        assert isinstance(result, pd.DataFrame)

    def test_get_supplements_breakdown_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_supplements_breakdown(branch="Branch_B")
        assert isinstance(result, pd.DataFrame)

    def test_get_medications_performance_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_medications_performance()
        assert isinstance(result, pd.DataFrame)

    def test_get_medications_performance_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_medications_performance(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)

    def test_get_services_performance_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_services_performance()
        assert isinstance(result, pd.DataFrame)

    def test_get_services_performance_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_services_performance(branch="Branch_C")
        assert isinstance(result, pd.DataFrame)

    def test_get_category_mix_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_category_mix()
        assert isinstance(result, pd.DataFrame)

    def test_get_category_mix_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_category_mix(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)


# ============================================================================
# Test Package Analytics Methods
# ============================================================================


class TestPackageAnalytics:
    """Test package analytics query methods."""

    def test_get_package_composition_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_package_composition()
        assert isinstance(result, pd.DataFrame)

    def test_get_package_composition_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_package_composition(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)

    def test_get_redemption_rates_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_redemption_rates()
        assert isinstance(result, pd.DataFrame)

    def test_get_redemption_rates_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_redemption_rates(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)

    def test_get_redemption_rates_with_status(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_redemption_rates(status="HIGH")
        assert isinstance(result, pd.DataFrame)

    def test_get_addon_analysis_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_addon_analysis()
        assert isinstance(result, pd.DataFrame)

    def test_get_addon_analysis_with_mrn(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_addon_analysis(mrn="MRN001")
        assert isinstance(result, pd.DataFrame)

    def test_get_addon_analysis_custom_limit(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_addon_analysis(limit=50)
        assert isinstance(result, pd.DataFrame)

    def test_get_package_conversion_demographics(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_package_conversion_demographics()
        assert isinstance(result, pd.DataFrame)


# ============================================================================
# Test Payment Behavior Methods
# ============================================================================


class TestPaymentBehavior:
    """Test payment behavior query methods."""

    def test_get_payment_mode_distribution(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_payment_mode_distribution()
        assert isinstance(result, pd.DataFrame)

    def test_get_affordability_stress_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_affordability_stress()
        assert isinstance(result, pd.DataFrame)

    def test_get_affordability_stress_with_level(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_affordability_stress(stress_level="HIGH")
        assert isinstance(result, pd.DataFrame)

    def test_get_payment_preference_by_stress(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_payment_preference_by_stress()
        assert isinstance(result, pd.DataFrame)

    def test_get_stressed_buyers_default(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_stressed_buyers()
        assert isinstance(result, pd.DataFrame)

    def test_get_stressed_buyers_custom_limit(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_stressed_buyers(limit=50)
        assert isinstance(result, pd.DataFrame)


# ============================================================================
# Test Utility Methods
# ============================================================================


class TestUtilityMethods:
    """Test utility and report generation methods."""

    def test_refresh_product_mvws_success(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {"mvw_name": ["mvw_skincare_monthly"], "refresh_status": ["REFRESHED"]}
        )
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.refresh_product_mvws()
        assert result["status"] == "success"
        assert "views_refreshed" in result

    def test_refresh_product_mvws_error(self, mock_db_manager):
        mock_db_manager.execute_query.side_effect = Exception("DB error")
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.refresh_product_mvws()
        assert result["status"] == "error"
        assert "message" in result

    def test_check_data_freshness(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "view_name": ["skincare_monthly"],
                "latest_month": [datetime(2024, 1, 1)],
                "row_count": [100],
            }
        )
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "success"
        assert "freshness" in result

    def test_generate_product_report_executive(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.generate_product_report(report_type="executive")
        assert "skincare_summary" in result
        assert "category_mix" in result
        assert "package_composition" in result

    def test_generate_product_report_product(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.generate_product_report(report_type="product")
        assert "skincare" in result
        assert "supplements" in result
        assert "medications" in result
        assert "services" in result

    def test_generate_product_report_package(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.generate_product_report(report_type="package")
        assert "composition" in result
        assert "redemption" in result
        assert "conversion" in result

    def test_generate_product_report_payment(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.generate_product_report(report_type="payment")
        assert "payment_modes" in result
        assert "stress_analysis" in result
        assert "stressed_buyers" in result

    def test_generate_product_report_unknown_type(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = ProductAnalyticsManager(db_manager=mock_db_manager)
        result = manager.generate_product_report(report_type="unknown")
        assert "error" in result

    def test_run_product_report_convenience_function(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        result = run_product_report("executive", db_manager=mock_db_manager)
        assert isinstance(result, dict)


# ============================================================================
# Test Integration (requires database)
# ============================================================================


@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring database connection."""

    @pytest.mark.skipif(
        not DB_ENV_CONFIGURED,
        reason="Database environment variables not configured",
    )
    def test_manager_initialization(self):
        manager = ProductAnalyticsManager()
        assert manager.db is not None

    @pytest.mark.skipif(
        not DB_ENV_CONFIGURED,
        reason="Database environment variables not configured",
    )
    def test_skincare_view_access(self):
        manager = ProductAnalyticsManager()
        result = manager.get_skincare_performance(months=1)
        assert isinstance(result, pd.DataFrame)

    @pytest.mark.skipif(
        not DB_ENV_CONFIGURED,
        reason="Database environment variables not configured",
    )
    def test_package_composition_view_access(self):
        manager = ProductAnalyticsManager()
        result = manager.get_package_composition()
        assert isinstance(result, pd.DataFrame)

    @pytest.mark.skipif(
        not DB_ENV_CONFIGURED,
        reason="Database environment variables not configured",
    )
    def test_stressed_buyers_view_access(self):
        manager = ProductAnalyticsManager()
        result = manager.get_stressed_buyers(limit=5)
        assert isinstance(result, pd.DataFrame)

    @pytest.mark.skipif(
        not DB_ENV_CONFIGURED,
        reason="Database environment variables not configured",
    )
    def test_data_freshness_check(self):
        manager = ProductAnalyticsManager()
        result = manager.check_data_freshness()
        assert result["status"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
