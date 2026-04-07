"""
ST-02: Sales & Revenue Analytics
Prophet-based sales forecasting module for 90-day predictions.
"""

import os
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np
from prophet import Prophet
from prophet.make_holidays import make_holidays_df

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ST-01" / "python"))
from database import DatabaseManager, get_db_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


MALAYSIAN_HOLIDAYS_2024_2026 = [
    {"holiday": "cny", "ds": "2024-02-10", "lower_window": -14, "upper_window": 7},
    {"holiday": "cny", "ds": "2025-01-29", "lower_window": -14, "upper_window": 7},
    {"holiday": "cny", "ds": "2026-02-17", "lower_window": -14, "upper_window": 7},
    {
        "holiday": "hari_raya",
        "ds": "2024-04-10",
        "lower_window": -14,
        "upper_window": 7,
    },
    {
        "holiday": "hari_raya",
        "ds": "2025-03-30",
        "lower_window": -14,
        "upper_window": 7,
    },
    {
        "holiday": "hari_raya",
        "ds": "2026-03-20",
        "lower_window": -14,
        "upper_window": 7,
    },
    {"holiday": "deepavali", "ds": "2024-10-31", "lower_window": -7, "upper_window": 7},
    {"holiday": "deepavali", "ds": "2025-10-20", "lower_window": -7, "upper_window": 7},
    {"holiday": "deepavali", "ds": "2026-11-08", "lower_window": -7, "upper_window": 7},
    {
        "holiday": "christmas",
        "ds": "2024-12-25",
        "lower_window": -14,
        "upper_window": 7,
    },
    {
        "holiday": "christmas",
        "ds": "2025-12-25",
        "lower_window": -14,
        "upper_window": 7,
    },
    {
        "holiday": "christmas",
        "ds": "2026-12-25",
        "lower_window": -14,
        "upper_window": 7,
    },
    {"holiday": "merdeka", "ds": "2024-08-31", "lower_window": -3, "upper_window": 1},
    {"holiday": "merdeka", "ds": "2025-08-31", "lower_window": -3, "upper_window": 1},
    {"holiday": "merdeka", "ds": "2026-08-31", "lower_window": -3, "upper_window": 1},
]


class SalesForecaster:
    """Prophet-based sales forecaster for 90-day predictions per branch."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        forecast_days: int = 90,
        model_version: Optional[str] = None,
    ):
        self.db = db_manager or get_db_manager()
        self.forecast_days = forecast_days
        self.model_version = model_version or datetime.now().strftime("%Y%m%d_%H%M")
        self._models: Dict[str, Prophet] = {}

    def _build_malaysian_holidays_df(self) -> pd.DataFrame:
        """Build Prophet holidays DataFrame for Malaysia."""
        holidays_df = pd.DataFrame(MALAYSIAN_HOLIDAYS_2024_2026)
        holidays_df["ds"] = pd.to_datetime(holidays_df["ds"])
        return holidays_df

    def load_daily_sales(self, branch: Optional[str] = None) -> pd.DataFrame:
        """
        Load daily sales data from materialized view.

        Args:
            branch: Specific branch to load, or None for all branches

        Returns:
            DataFrame with ds (date) and y (revenue) columns
        """
        if branch:
            query = """
                SELECT 
                    transaction_date AS ds,
                    SUM(total_revenue) AS y,
                    branch
                FROM dk.mvw_daily_sales_summary
                WHERE branch = :branch
                GROUP BY transaction_date, branch
                ORDER BY transaction_date
            """
            df = self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    transaction_date AS ds,
                    SUM(total_revenue) AS y,
                    branch
                FROM dk.mvw_daily_sales_summary
                GROUP BY transaction_date, branch
                ORDER BY transaction_date, branch
            """
            df = self.db.execute_query(query)

        if df.empty:
            logger.warning("No sales data found")
            return pd.DataFrame()

        df["ds"] = pd.to_datetime(df["ds"])
        df["y"] = df["y"].astype(float)

        logger.info(f"Loaded {len(df)} daily sales records")
        return df

    def train_branch_model(
        self,
        branch: str,
        sales_df: pd.DataFrame,
        seasonality_mode: str = "multiplicative",
        yearly_seasonality: int = 10,
        weekly_seasonality: bool = True,
        monthly_fourier_order: int = 5,
    ) -> Optional[Prophet]:
        """
        Train a Prophet model for a specific branch.

        Args:
            branch: Branch name
            sales_df: DataFrame with ds and y columns for this branch
            seasonality_mode: 'additive' or 'multiplicative'
            yearly_seasonality: Fourier order for yearly seasonality
            weekly_seasonality: Whether to include weekly seasonality
            monthly_fourier_order: Fourier order for monthly seasonality

        Returns:
            Trained Prophet model
        """
        branch_df = sales_df[sales_df["branch"] == branch][["ds", "y"]].copy()

        if len(branch_df) < 30:
            logger.warning(
                f"Insufficient data for branch {branch}: {len(branch_df)} days"
            )
            return None

        holidays_df = self._build_malaysian_holidays_df()

        model = Prophet(
            holidays=holidays_df,
            seasonality_mode=seasonality_mode,
            yearly_seasonality=yearly_seasonality,  # pyright: ignore[reportArgumentType]
            weekly_seasonality=weekly_seasonality,  # pyright: ignore[reportArgumentType]
            changepoint_prior_scale=0.05,
            interval_width=0.80,
        )

        model.add_seasonality(
            name="monthly", period=30.5, fourier_order=monthly_fourier_order
        )

        model.fit(branch_df)

        self._models[branch] = model
        logger.info(f"Trained model for branch: {branch}")

        return model

    def generate_forecast(
        self, branch: str, model: Optional[Prophet] = None
    ) -> pd.DataFrame:
        """
        Generate 90-day forecast for a branch.

        Args:
            branch: Branch name
            model: Pre-trained model, or None to use cached model

        Returns:
            DataFrame with forecast columns
        """
        model = model or self._models.get(branch)
        if model is None:
            logger.error(f"No model found for branch: {branch}")
            return pd.DataFrame()

        future = model.make_future_dataframe(periods=self.forecast_days)
        forecast = model.predict(future)

        forecast["branch"] = branch
        forecast = forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "branch"]].copy()
        forecast.columns = [
            "forecast_date",
            "yhat",
            "yhat_lower",
            "yhat_upper",
            "branch",
        ]

        today = datetime.now().date()
        forecast["forecast_date"] = pd.to_datetime(forecast["forecast_date"]).dt.date  # pyright: ignore[reportAttributeAccessIssue]

        # Get the last date from training data to determine forecast horizon
        last_training_date = forecast["forecast_date"].min()
        forecast = forecast[forecast["forecast_date"] > last_training_date].copy()
        forecast["forecast_horizon"] = forecast["forecast_date"].apply(  # pyright: ignore[reportAttributeAccessIssue]
            lambda x: (x - today).days
        )
        forecast["model_version"] = self.model_version

        forecast["yhat"] = forecast["yhat"].clip(lower=0.0).round(2)  # pyright: ignore[reportCallIssue]
        forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0.0).round(2)  # pyright: ignore[reportCallIssue]
        forecast["yhat_upper"] = forecast["yhat_upper"].round(2)

        return forecast  # type: ignore[return-value]

    def save_forecast(self, forecast_df: pd.DataFrame) -> int:
        """
        Save forecast to database table.

        Args:
            forecast_df: DataFrame with forecast data

        Returns:
            Number of rows saved
        """
        if forecast_df.empty:
            logger.warning("No forecast data to save")
            return 0

        forecast_df = forecast_df.copy()
        forecast_df["created_at"] = datetime.now()

        with self.db.get_connection() as conn:
            forecast_df.to_sql(
                "sales_forecast",
                conn,
                schema="dk",
                if_exists="append",
                index=False,
            )

        logger.info(f"Saved {len(forecast_df)} forecast records")
        return len(forecast_df)

    def generate_all_branch_forecasts(self) -> pd.DataFrame:
        """
        Generate forecasts for all branches.

        Returns:
            Combined DataFrame with all branch forecasts
        """
        sales_df = self.load_daily_sales()

        if sales_df.empty:
            logger.error("No sales data available for forecasting")
            return pd.DataFrame()

        branches = sales_df["branch"].unique()
        logger.info(f"Found {len(branches)} branches to forecast")

        all_forecasts = []

        for branch in branches:
            try:
                model = self.train_branch_model(branch, sales_df)
                if model is not None:
                    forecast = self.generate_forecast(branch, model)
                    all_forecasts.append(forecast)
            except Exception as e:
                logger.error(f"Failed to forecast branch {branch}: {e}")
                continue

        if not all_forecasts:
            return pd.DataFrame()

        combined = pd.concat(all_forecasts, ignore_index=True)
        logger.info(f"Generated {len(combined)} total forecast records")

        return combined

    def get_forecast_summary(self, days_ahead: int = 30) -> pd.DataFrame:
        """
        Get forecast summary for the next N days.

        Args:
            days_ahead: Number of days to summarize

        Returns:
            DataFrame with forecast summary by branch
        """
        query = """
            SELECT 
                branch,
                COUNT(*) AS forecast_days,
                SUM(yhat) AS total_predicted_revenue,
                AVG(yhat) AS avg_daily_predicted,
                MIN(yhat) AS min_predicted,
                MAX(yhat) AS max_predicted,
                AVG(yhat_upper - yhat_lower) AS avg_uncertainty_range
            FROM dk.sales_forecast
            WHERE forecast_horizon <= :days_ahead
            GROUP BY branch
            ORDER BY total_predicted_revenue DESC
        """
        return self.db.execute_query(query, {"days_ahead": days_ahead})

    def evaluate_forecast_accuracy(self, days_back: int = 30) -> pd.DataFrame:
        """
        Evaluate forecast accuracy against actuals.

        Args:
            days_back: Number of days to evaluate

        Returns:
            DataFrame with accuracy metrics
        """
        query = """
            WITH actuals AS (
                SELECT 
                    transaction_date,
                    branch,
                    SUM(total_revenue) AS actual_revenue
                FROM dk.mvw_daily_sales_summary
                WHERE transaction_date >= CURRENT_DATE - :days_back
                GROUP BY transaction_date, branch
            ),
            predictions AS (
                SELECT 
                    forecast_date,
                    branch,
                    yhat AS predicted_revenue
                FROM dk.sales_forecast
                WHERE forecast_date >= CURRENT_DATE - :days_back
            )
            SELECT 
                a.branch,
                COUNT(*) AS evaluation_days,
                SUM(a.actual_revenue) AS total_actual,
                SUM(p.predicted_revenue) AS total_predicted,
                ROUND(
                    AVG(ABS(p.predicted_revenue - a.actual_revenue) / 
                        NULLIF(a.actual_revenue, 0) * 100)::NUMERIC, 2
                ) AS mape_pct,
                ROUND(
                    SQRT(AVG(POWER(p.predicted_revenue - a.actual_revenue, 2)))::NUMERIC, 2
                ) AS rmse
            FROM actuals a
            JOIN predictions p ON a.transaction_date = p.forecast_date 
                AND a.branch = p.branch
            GROUP BY a.branch
            ORDER BY mape_pct
        """
        return self.db.execute_query(query, {"days_back": days_back})


def run_daily_forecast(forecast_days: int = 90) -> Dict[str, Any]:
    """
    Run daily forecast generation (for scheduling).

    Args:
        forecast_days: Number of days to forecast

    Returns:
        Summary of forecast run
    """
    start_time = datetime.now()

    forecaster = SalesForecaster(forecast_days=forecast_days)

    forecast_df = forecaster.generate_all_branch_forecasts()

    if not forecast_df.empty:
        rows_saved = forecaster.save_forecast(forecast_df)
    else:
        rows_saved = 0

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    result = {
        "status": "SUCCESS" if rows_saved > 0 else "NO_DATA",
        "branches_forecasted": forecast_df["branch"].nunique()
        if not forecast_df.empty
        else 0,
        "total_forecast_days": len(forecast_df),
        "rows_saved": rows_saved,
        "model_version": forecaster.model_version,
        "duration_seconds": round(duration, 2),
        "timestamp": start_time.isoformat(),
    }

    logger.info(f"Forecast run completed: {result}")
    return result


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    print("Running Sales Forecast...")
    print("=" * 50)

    result = run_daily_forecast(forecast_days=90)

    print("\nForecast Run Summary:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    if result["status"] == "SUCCESS":
        print("\n" + "=" * 50)
        print("30-Day Forecast Summary by Branch:")

        forecaster = SalesForecaster()
        summary = forecaster.get_forecast_summary(days_ahead=30)
        print(summary.to_string(index=False))
