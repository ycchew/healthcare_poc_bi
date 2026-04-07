"""
ST-02: Sales & Revenue Analytics
Test suite for sales_forecast.py and sales_analytics.py modules.

To run tests:
    # Run all unit tests (no database required)
    pytest test_sales_analytics.py -v

    # Run specific test classes
    pytest test_sales_analytics.py::TestSalesForecaster -v
    pytest test_sales_analytics.py::TestSalesAnalyticsManager -v

    # Run integration tests (requires database connection)
    pytest test_sales_analytics.py::TestIntegration -v -m integration
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
from sales_forecast import (
    SalesForecaster,
    run_daily_forecast,
    MALAYSIAN_HOLIDAYS_2024_2026,
)
from sales_analytics import SalesAnalyticsManager, generate_sales_report


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
def sample_daily_sales_df():
    dates = pd.date_range(start="2024-01-01", periods=90, freq="D")
    return pd.DataFrame(
        {
            "ds": dates,
            "y": np.random.uniform(10000, 50000, 90),
            "branch": ["Branch_A"] * 45 + ["Branch_B"] * 45,
        }
    )


@pytest.fixture
def sample_forecast_df():
    dates = pd.date_range(start=datetime.now(), periods=90, freq="D")
    return pd.DataFrame(
        {
            "forecast_date": dates.date,  # pyright: ignore[reportAttributeAccessIssue]
            "yhat": np.random.uniform(30000, 50000, 90),
            "yhat_lower": np.random.uniform(25000, 35000, 90),
            "yhat_upper": np.random.uniform(45000, 60000, 90),
            "branch": ["Branch_A"] * 90,
            "forecast_horizon": range(1, 91),
            "model_version": ["20240101_1200"] * 90,
        }
    )


# ============================================================================
# Test Malaysian Holidays Configuration
# ============================================================================


class TestMalaysianHolidays:
    """Test Malaysian holidays configuration."""

    def test_holidays_list_not_empty(self):
        assert len(MALAYSIAN_HOLIDAYS_2024_2026) > 0

    def test_holidays_have_required_fields(self):
        required_fields = {"holiday", "ds", "lower_window", "upper_window"}
        for holiday in MALAYSIAN_HOLIDAYS_2024_2026:
            assert required_fields.issubset(holiday.keys())

    def test_cny_window_range(self):
        cny_holidays = [
            h for h in MALAYSIAN_HOLIDAYS_2024_2026 if h["holiday"] == "cny"
        ]
        assert len(cny_holidays) >= 3  # 2024, 2025, 2026
        for h in cny_holidays:
            assert h["lower_window"] == -14  # 14 days before
            assert h["upper_window"] == 7  # 7 days after

    def test_hari_raya_window_range(self):
        hr_holidays = [
            h for h in MALAYSIAN_HOLIDAYS_2024_2026 if h["holiday"] == "hari_raya"
        ]
        for h in hr_holidays:
            assert h["lower_window"] == -14
            assert h["upper_window"] == 7

    def test_christmas_window_range(self):
        xmas_holidays = [
            h for h in MALAYSIAN_HOLIDAYS_2024_2026 if h["holiday"] == "christmas"
        ]
        for h in xmas_holidays:
            assert h["lower_window"] == -14
            assert h["upper_window"] == 7


# ============================================================================
# Test SalesForecaster
# ============================================================================


class TestSalesForecaster:
    """Test SalesForecaster class."""

    def test_initialization_default(self, mock_db_manager):
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        assert forecaster.forecast_days == 90
        assert forecaster.model_version is not None
        assert forecaster._models == {}

    def test_initialization_custom_params(self, mock_db_manager):
        forecaster = SalesForecaster(
            db_manager=mock_db_manager, forecast_days=60, model_version="custom_v1"
        )
        assert forecaster.forecast_days == 60
        assert forecaster.model_version == "custom_v1"

    def test_build_malaysian_holidays_df(self, mock_db_manager):
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        holidays_df = forecaster._build_malaysian_holidays_df()
        assert isinstance(holidays_df, pd.DataFrame)
        assert "holiday" in holidays_df.columns
        assert "ds" in holidays_df.columns
        assert len(holidays_df) == len(MALAYSIAN_HOLIDAYS_2024_2026)

    def test_load_daily_sales_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {"ds": [datetime(2024, 1, 1)], "y": [10000.0], "branch": ["Branch_A"]}
        )
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        result = forecaster.load_daily_sales(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)
        assert "ds" in result.columns
        assert "y" in result.columns

    def test_load_daily_sales_empty_result(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        result = forecaster.load_daily_sales()
        assert result.empty

    @patch("sales_forecast.Prophet")
    def test_train_branch_model_insufficient_data(self, mock_prophet, mock_db_manager):
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        small_df = pd.DataFrame(
            {
                "ds": pd.date_range(start="2024-01-01", periods=10, freq="D"),
                "y": range(10),
                "branch": ["Branch_A"] * 10,
            }
        )
        result = forecaster.train_branch_model("Branch_A", small_df)
        assert result is None

    @patch("sales_forecast.Prophet")
    def test_train_branch_model_success(
        self, mock_prophet, mock_db_manager, sample_daily_sales_df
    ):
        mock_model = Mock()
        mock_prophet.return_value = mock_model
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        result = forecaster.train_branch_model("Branch_A", sample_daily_sales_df)
        assert result is not None
        mock_prophet.assert_called_once()
        mock_model.fit.assert_called_once()

    @patch("sales_forecast.Prophet")
    def test_generate_forecast(
        self, mock_prophet, mock_db_manager, sample_daily_sales_df
    ):
        mock_model = Mock()
        mock_model.make_future_dataframe.return_value = pd.DataFrame(
            {"ds": pd.date_range(start="2024-01-01", periods=180, freq="D")}
        )
        mock_model.predict.return_value = pd.DataFrame(
            {
                "ds": pd.date_range(start="2024-01-01", periods=180, freq="D"),
                "yhat": np.random.uniform(10000, 50000, 180),
                "yhat_lower": np.random.uniform(8000, 40000, 180),
                "yhat_upper": np.random.uniform(12000, 60000, 180),
            }
        )
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        forecaster._models["Branch_A"] = mock_model
        result = forecaster.generate_forecast("Branch_A")
        assert isinstance(result, pd.DataFrame)
        assert "forecast_date" in result.columns
        assert "yhat" in result.columns

    def test_generate_forecast_no_model(self, mock_db_manager):
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        result = forecaster.generate_forecast("Branch_A")
        assert result.empty

    def test_save_forecast_empty(self, mock_db_manager):
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        result = forecaster.save_forecast(pd.DataFrame())
        assert result == 0

    def test_generate_all_branch_forecasts_empty_data(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        result = forecaster.generate_all_branch_forecasts()
        assert result.empty

    def test_get_forecast_summary(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "branch": ["Branch_A", "Branch_B"],
                "total_predicted_revenue": [1000000, 800000],
            }
        )
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        result = forecaster.get_forecast_summary(days_ahead=30)
        assert isinstance(result, pd.DataFrame)
        mock_db_manager.execute_query.assert_called_once()

    def test_evaluate_forecast_accuracy(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "branch": ["Branch_A"],
                "mape_pct": [5.5],
                "rmse": [1500.0],
            }
        )
        forecaster = SalesForecaster(db_manager=mock_db_manager)
        result = forecaster.evaluate_forecast_accuracy(days_back=30)
        assert isinstance(result, pd.DataFrame)


# ============================================================================
# Test SalesAnalyticsManager
# ============================================================================


class TestSalesAnalyticsManager:
    """Test SalesAnalyticsManager class."""

    def test_initialization_default(self, mock_db_manager):
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        assert manager.db is not None

    def test_get_executive_summary(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "total_revenue": [1500000.0],
                "total_transactions": [5000],
                "total_patients": [3000],
                "active_branches": [5],
                "avg_transaction_value": [300.0],
                "avg_discount_rate": [8.5],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_executive_summary()
        assert isinstance(result, dict)
        assert "total_revenue" in result
        assert "total_transactions" in result

    def test_get_executive_summary_empty(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_executive_summary()
        assert result == {}

    def test_get_branch_ranking(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "branch": ["Branch_A", "Branch_B"],
                "monthly_revenue": [500000, 400000],
                "performance_tier": ["Top", "High"],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_branch_ranking(limit=10)
        assert isinstance(result, pd.DataFrame)
        assert "branch" in result.columns

    def test_get_monthly_trend(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "year_month": ["2024-01", "2024-02"],
                "total_revenue": [1000000, 1100000],
                "mom_growth_pct": [5.0, 10.0],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_monthly_trend(months=12)
        assert isinstance(result, pd.DataFrame)
        assert "year_month" in result.columns

    def test_get_category_performance(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "branch": ["Branch_A"],
                "services_revenue": [200000],
                "skincare_revenue": [100000],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_category_performance(month="2024-01")
        assert isinstance(result, pd.DataFrame)

    def test_get_festival_impact(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "festival_group": ["CNY", "Hari Raya"],
                "avg_lift_pct": [25.0, 18.0],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_festival_impact(year=2024)
        assert isinstance(result, pd.DataFrame)
        assert "festival_group" in result.columns

    def test_get_promotion_effectiveness_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "transaction_date": [datetime(2024, 1, 1)],
                "discount_tier": ["High"],
                "lift_vs_baseline_pct": [15.0],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_promotion_effectiveness(branch="Branch_A", days=30)
        assert isinstance(result, pd.DataFrame)

    def test_get_promotion_effectiveness_all_branches(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "discount_tier": ["High", "Medium"],
                "avg_lift_pct": [12.0, 8.0],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_promotion_effectiveness(days=30)
        assert isinstance(result, pd.DataFrame)

    def test_get_dow_heatmap_with_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "day_of_week": range(7),
                "day_name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                "avg_revenue": [30000] * 7,
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_dow_heatmap(branch="Branch_A")
        assert isinstance(result, pd.DataFrame)

    def test_get_dow_heatmap_all(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "day_of_week": range(7),
                "total_revenue": [200000] * 7,
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_dow_heatmap()
        assert isinstance(result, pd.DataFrame)

    def test_get_sales_channel_mix(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "sales_channel": ["Walk-in", "Online"],
                "total_revenue": [800000, 200000],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.get_sales_channel_mix(month="2024-01")
        assert isinstance(result, pd.DataFrame)
        assert "sales_channel" in result.columns

    def test_check_data_freshness_ok(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "latest_date": [datetime.now().date()],
                "days_behind": [0],
                "total_records": [10000],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "OK"
        assert result["days_behind"] == 0

    def test_check_data_freshness_warning(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "latest_date": [datetime.now().date() - timedelta(days=2)],
                "days_behind": [2],
                "total_records": [10000],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "WARNING"
        assert result["days_behind"] == 2

    def test_check_data_freshness_critical(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "latest_date": [datetime.now().date() - timedelta(days=5)],
                "days_behind": [5],
                "total_records": [10000],
            }
        )
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "CRITICAL"

    def test_check_data_freshness_empty(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame()
        manager = SalesAnalyticsManager(db_manager=mock_db_manager)
        result = manager.check_data_freshness()
        assert result["status"] == "ERROR"


# ============================================================================
# Test Convenience Functions
# ============================================================================


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    @patch("sales_forecast.SalesForecaster")
    def test_run_daily_forecast_success(self, mock_forecaster_class, mock_db_manager):
        mock_instance = Mock()
        mock_instance.generate_all_branch_forecasts.return_value = pd.DataFrame(
            {
                "branch": ["Branch_A"] * 90,
                "yhat": [10000] * 90,
            }
        )
        mock_instance.save_forecast.return_value = 90
        mock_instance.model_version = "20240101_1200"
        mock_forecaster_class.return_value = mock_instance

        with patch("sales_forecast.get_db_manager", return_value=mock_db_manager):
            result = run_daily_forecast(forecast_days=90)
            assert result["status"] == "SUCCESS"
            assert result["rows_saved"] == 90

    def test_generate_sales_report_executive(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "total_revenue": [1000000.0],
                "total_transactions": [5000],
                "total_patients": [3000],
                "active_branches": [5],
                "avg_transaction_value": [200.0],
                "avg_discount_rate": [8.5],
            }
        )
        with patch("sales_analytics.get_db_manager", return_value=mock_db_manager):
            result = generate_sales_report(report_type="executive")
            assert isinstance(result, dict)

    def test_generate_sales_report_branch(self, mock_db_manager):
        mock_db_manager.execute_query.return_value = pd.DataFrame(
            {
                "branch": ["Branch_A"],
            }
        )
        with patch("sales_analytics.get_db_manager", return_value=mock_db_manager):
            result = generate_sales_report(report_type="branch")
            assert isinstance(result, pd.DataFrame)

    def test_generate_sales_report_invalid_type(self, mock_db_manager):
        with patch("sales_analytics.get_db_manager", return_value=mock_db_manager):
            with pytest.raises(ValueError):
                generate_sales_report(report_type="invalid")


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

    def test_real_sales_analytics_manager(self):
        """Test real SalesAnalyticsManager with live database."""
        manager = SalesAnalyticsManager()
        freshness = manager.check_data_freshness()
        assert "status" in freshness
        assert freshness["status"] in ["OK", "WARNING", "CRITICAL", "ERROR"]

    def test_real_executive_summary(self):
        """Test real executive summary query."""
        manager = SalesAnalyticsManager()
        summary = manager.get_executive_summary()
        assert isinstance(summary, dict)
        assert "total_revenue" in summary

    def test_real_branch_ranking(self):
        """Test real branch ranking query."""
        manager = SalesAnalyticsManager()
        ranking = manager.get_branch_ranking(limit=5)
        assert isinstance(ranking, pd.DataFrame)

    def test_real_monthly_trend(self):
        """Test real monthly trend query."""
        manager = SalesAnalyticsManager()
        trend = manager.get_monthly_trend(months=6)
        assert isinstance(trend, pd.DataFrame)

    def test_real_dow_heatmap(self):
        """Test real DOW heatmap query."""
        manager = SalesAnalyticsManager()
        heatmap = manager.get_dow_heatmap()
        assert isinstance(heatmap, pd.DataFrame)


if __name__ == "__main__":
    try:
        import pytest

        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        print("pytest not installed. Install with: pip install pytest pytest-mock")
        print("Running basic smoke tests...")

        print("\nTesting Malaysian Holidays...")
        assert len(MALAYSIAN_HOLIDAYS_2024_2026) > 0
        print(f"  Found {len(MALAYSIAN_HOLIDAYS_2024_2026)} holiday entries")

        print("\nAll smoke tests passed!")
