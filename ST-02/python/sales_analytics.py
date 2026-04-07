"""
ST-02: Sales & Revenue Analytics
Database utilities and analytics functions for sales data.
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


class SalesAnalyticsManager:
    """Manager for sales analytics queries and reports."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or get_db_manager()

    def get_executive_summary(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get executive sales summary for dashboard.

        Args:
            start_date: Start date (YYYY-MM-DD), defaults to month start
            end_date: End date (YYYY-MM-DD), defaults to today

        Returns:
            Dictionary with KPI metrics
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")

        query = """
            SELECT 
                SUM(total_revenue) AS total_revenue,
                SUM(total_transactions) AS total_transactions,
                SUM(unique_patients) AS total_patients,
                COUNT(DISTINCT branch) AS active_branches,
                ROUND(AVG(avg_transaction_value)::NUMERIC, 2) AS avg_transaction_value,
                ROUND(AVG(discount_rate_pct)::NUMERIC, 2) AS avg_discount_rate
            FROM dk.mvw_daily_sales_summary
            WHERE transaction_date BETWEEN :start_date AND :end_date
        """
        df = self.db.execute_query(
            query, {"start_date": start_date, "end_date": end_date}
        )

        if df.empty:
            return {}

        return {
            "total_revenue": float(df.iloc[0]["total_revenue"] or 0),
            "total_transactions": int(df.iloc[0]["total_transactions"] or 0),
            "total_patients": int(df.iloc[0]["total_patients"] or 0),
            "active_branches": int(df.iloc[0]["active_branches"] or 0),
            "avg_transaction_value": float(df.iloc[0]["avg_transaction_value"] or 0),
            "avg_discount_rate": float(df.iloc[0]["avg_discount_rate"] or 0),
            "period_start": start_date,
            "period_end": end_date,
        }

    def get_branch_ranking(self, limit: int = 10) -> pd.DataFrame:
        """
        Get current month branch ranking.

        Args:
            limit: Number of branches to return

        Returns:
            DataFrame with branch ranking
        """
        query = """
            SELECT 
                branch,
                monthly_revenue,
                monthly_transactions,
                monthly_patients,
                mom_revenue_growth_pct,
                revenue_rank,
                performance_tier,
                growth_status
            FROM dk.mvw_branch_performance
            WHERE year_month = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
            ORDER BY monthly_revenue DESC
            LIMIT :limit
        """
        return self.db.execute_query(query, {"limit": limit})

    def get_monthly_trend(self, months: int = 12) -> pd.DataFrame:
        """
        Get monthly sales trend.

        Args:
            months: Number of months to return

        Returns:
            DataFrame with monthly trend
        """
        query = """
            SELECT 
                month_start,
                year_month,
                total_revenue,
                total_transactions,
                total_patients,
                mom_growth_pct,
                yoy_growth_pct,
                standalone_pct,
                package_pct,
                moving_avg_3m,
                trend_status
            FROM dk.mvw_monthly_sales_trend
            ORDER BY month_start DESC
            LIMIT :months
        """
        return self.db.execute_query(query, {"months": months})

    def get_category_performance(self, month: Optional[str] = None) -> pd.DataFrame:
        """
        Get product category performance.

        Args:
            month: Month in YYYY-MM format, defaults to current month

        Returns:
            DataFrame with category performance
        """
        if month is None:
            month = datetime.now().strftime("%Y-%m")

        query = """
            SELECT 
                branch,
                services_revenue,
                medications_revenue,
                supplements_revenue,
                skincare_revenue,
                other_products_revenue,
                total_revenue,
                services_pct,
                skincare_pct,
                supplements_pct,
                top_category
            FROM dk.mvw_product_performance
            WHERE year_month = :month
            ORDER BY total_revenue DESC
        """
        return self.db.execute_query(query, {"month": month})

    def get_festival_impact(self, year: Optional[int] = None) -> pd.DataFrame:
        """
        Get festival impact analysis.

        Args:
            year: Year to analyze, defaults to current year

        Returns:
            DataFrame with festival impact
        """
        if year is None:
            year = datetime.now().year

        query = """
            SELECT 
                festival_group,
                holiday_name,
                period_type,
                total_days,
                total_revenue,
                avg_daily_revenue,
                avg_lift_pct,
                positive_lift_pct
            FROM dk.vw_festival_performance
            WHERE EXTRACT(YEAR FROM holiday_date) = :year
            ORDER BY holiday_date, period_type
        """
        return self.db.execute_query(query, {"year": year})

    def get_promotion_effectiveness(
        self, branch: Optional[str] = None, days: int = 30
    ) -> pd.DataFrame:
        """
        Get promotion effectiveness analysis.

        Args:
            branch: Specific branch, or None for all
            days: Number of days to analyze

        Returns:
            DataFrame with promotion effectiveness
        """
        if branch:
            query = """
                SELECT 
                    transaction_date,
                    total_revenue,
                    discount_rate_pct,
                    is_promotional,
                    discount_tier,
                    lift_vs_baseline_pct,
                    promotion_effectiveness,
                    revenue_impact
                FROM dk.mvw_promotion_impact
                WHERE branch = :branch
                  AND transaction_date >= CURRENT_DATE - :days
                ORDER BY transaction_date DESC
            """
            return self.db.execute_query(query, {"branch": branch, "days": days})
        else:
            query = """
                SELECT 
                    discount_tier,
                    COUNT(*) AS transaction_days,
                    SUM(total_revenue) AS total_revenue,
                    ROUND(AVG(lift_vs_baseline_pct)::NUMERIC, 2) AS avg_lift_pct,
                    SUM(CASE WHEN promotion_effectiveness = 'Effective' THEN 1 ELSE 0 END) AS effective_days,
                    SUM(CASE WHEN promotion_effectiveness = 'Ineffective' THEN 1 ELSE 0 END) AS ineffective_days
                FROM dk.mvw_promotion_impact
                WHERE transaction_date >= CURRENT_DATE - :days
                GROUP BY discount_tier
                ORDER BY total_revenue DESC
            """
            return self.db.execute_query(query, {"days": days})

    def get_dow_heatmap(self, branch: Optional[str] = None) -> pd.DataFrame:
        """
        Get day-of-week heatmap data.

        Args:
            branch: Specific branch, or None for all

        Returns:
            DataFrame with DOW heatmap
        """
        if branch:
            query = """
                SELECT *
                FROM dk.mvw_dow_heatmap
                WHERE branch = :branch
                ORDER BY day_of_week
            """
            return self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    day_of_week,
                    day_name,
                    ROUND(SUM(total_revenue)::NUMERIC, 2) AS total_revenue,
                    ROUND(AVG(avg_revenue)::NUMERIC, 2) AS avg_revenue,
                    COUNT(DISTINCT branch) AS branch_count
                FROM dk.mvw_dow_heatmap
                GROUP BY day_of_week, day_name
                ORDER BY day_of_week
            """
            return self.db.execute_query(query)

    def get_sales_channel_mix(self, month: Optional[str] = None) -> pd.DataFrame:
        """
        Get sales channel mix analysis.

        Args:
            month: Month in YYYY-MM format

        Returns:
            DataFrame with channel mix
        """
        if month is None:
            month = datetime.now().strftime("%Y-%m")

        query = """
            SELECT 
                sales_channel,
                SUM(monthly_revenue) AS total_revenue,
                SUM(monthly_transactions) AS total_transactions,
                ROUND(AVG(avg_transaction_value)::NUMERIC, 2) AS avg_transaction_value,
                ROUND(AVG(standalone_pct)::NUMERIC, 2) AS avg_standalone_pct,
                ROUND(AVG(package_pct)::NUMERIC, 2) AS avg_package_pct
            FROM dk.mvw_sales_channel_performance
            WHERE year_month = :month
            GROUP BY sales_channel
            ORDER BY total_revenue DESC
        """
        return self.db.execute_query(query, {"month": month})

    def check_data_freshness(self) -> Dict[str, Any]:
        """
        Check freshness of sales data.

        Returns:
            Dictionary with freshness status
        """
        query = """
            SELECT 
                MAX(transaction_date) AS latest_date,
                CURRENT_DATE - MAX(transaction_date) AS days_behind,
                COUNT(*) AS total_records
            FROM dk.mvw_daily_sales_summary
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
            "total_records": int(df.iloc[0]["total_records"]),
        }


def generate_sales_report(
    report_type: str = "executive", output_format: str = "dataframe"
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Generate a sales report.

    Args:
        report_type: Type of report ('executive', 'branch', 'category', 'trend')
        output_format: 'dataframe' or 'dict'

    Returns:
        Report data
    """
    manager = SalesAnalyticsManager()

    if report_type == "executive":
        data = manager.get_executive_summary()
    elif report_type == "branch":
        data = manager.get_branch_ranking()
    elif report_type == "category":
        data = manager.get_category_performance()
    elif report_type == "trend":
        data = manager.get_monthly_trend()
    else:
        raise ValueError(f"Unknown report type: {report_type}")

    if output_format == "dict" and isinstance(data, pd.DataFrame):
        return data.to_dict(orient="records")  # pyright: ignore[reportReturnType]
    return data


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    print("Sales Analytics Report")
    print("=" * 60)

    manager = SalesAnalyticsManager()

    print("\n1. Executive Summary (MTD):")
    summary = manager.get_executive_summary()
    for key, value in summary.items():
        print(f"   {key}: {value}")

    print("\n2. Branch Ranking (Top 10):")
    ranking = manager.get_branch_ranking(limit=10)
    print(
        ranking[
            ["branch", "monthly_revenue", "mom_revenue_growth_pct", "performance_tier"]
        ].to_string(index=False)
    )

    print("\n3. Data Freshness:")
    freshness = manager.check_data_freshness()
    for key, value in freshness.items():
        print(f"   {key}: {value}")
