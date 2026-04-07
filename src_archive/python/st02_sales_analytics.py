"""
ST-02: Sales & Revenue Analytics
Python module for advanced sales analytics and reporting
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from database import execute_query


def get_revenue_trends(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> pd.DataFrame:
    """Get revenue trends with growth calculations."""
    query = """
    SELECT * FROM dk.vw_revenue_trends
    WHERE 1=1
    """
    if start_date:
        query += f" AND transaction_year_month >= '{start_date}'"
    if end_date:
        query += f" AND transaction_year_month <= '{end_date}'"
    query += " ORDER BY transaction_year_month"
    return execute_query(query)


def get_branch_ranking(year_month: Optional[str] = None) -> pd.DataFrame:
    """Get branch performance ranking."""
    query = """
    SELECT * FROM dk.vw_branch_ranking
    WHERE 1=1
    """
    if year_month:
        query += f" AND transaction_year_month = '{year_month}'"
    else:
        query += """ AND transaction_year_month = (
            SELECT MAX(transaction_year_month) FROM dk.vw_branch_ranking
        )"""
    query += " ORDER BY revenue_rank"
    return execute_query(query)


def get_calendar_effects() -> pd.DataFrame:
    """Get calendar effects analysis."""
    return execute_query(
        "SELECT * FROM dk.vw_calendar_analysis ORDER BY analysis_type, dimension"
    )


def get_discount_analysis(year_month: Optional[str] = None) -> pd.DataFrame:
    """Get discount impact analysis."""
    query = """
    SELECT * FROM dk.vw_discount_analysis
    WHERE 1=1
    """
    if year_month:
        query += f" AND transaction_year_month = '{year_month}'"
    query += " ORDER BY transaction_year_month"
    return execute_query(query)


def get_executive_kpis() -> Dict:
    """Get executive KPIs as dictionary."""
    df = execute_query("SELECT * FROM dk.vw_executive_kpis")
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


def analyze_revenue_growth(months: int = 12) -> pd.DataFrame:
    """Analyze revenue growth trends over specified months."""
    query = f"""
    SELECT 
        transaction_year_month,
        net_revenue,
        mom_growth_pct,
        yoy_growth_pct,
        trend_status
    FROM dk.vw_revenue_trends
    WHERE transaction_date >= CURRENT_DATE - INTERVAL '{months} months'
    ORDER BY transaction_year_month
    """
    return execute_query(query)


def identify_top_performers(
    metric: str = "net_revenue", top_n: int = 5
) -> pd.DataFrame:
    """Identify top performing branches by metric."""
    query = f"""
    SELECT 
        branch_name,
        transaction_year_month,
        {metric},
        revenue_rank,
        performance_tier
    FROM dk.vw_branch_ranking
    WHERE transaction_year_month = (
        SELECT MAX(transaction_year_month) FROM dk.vw_branch_ranking
    )
    ORDER BY {metric} DESC
    LIMIT {top_n}
    """
    return execute_query(query)


def generate_sales_report(output_path: str = "./docs/output/sales_report.xlsx") -> str:
    """Generate comprehensive sales report in Excel format."""
    trends = get_revenue_trends()
    branches = get_branch_ranking()
    calendar = get_calendar_effects()
    discounts = get_discount_analysis()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        trends.to_excel(writer, sheet_name="Revenue Trends", index=False)
        branches.to_excel(writer, sheet_name="Branch Ranking", index=False)
        calendar.to_excel(writer, sheet_name="Calendar Effects", index=False)
        discounts.to_excel(writer, sheet_name="Discount Analysis", index=False)

    return output_path


def detect_seasonality() -> pd.DataFrame:
    """Detect seasonal patterns in revenue."""
    query = """
    SELECT 
        transaction_month,
        transaction_quarter,
        AVG(net_revenue) AS avg_revenue,
        AVG(unique_patients) AS avg_patients,
        AVG(avg_transaction_value) AS avg_atv,
        COUNT(DISTINCT transaction_year) AS years_of_data
    FROM dk.mvw_calendar_effects
    GROUP BY transaction_month, transaction_quarter
    ORDER BY transaction_month
    """
    return execute_query(query)


def forecast_revenue_simple(months_ahead: int = 3) -> pd.DataFrame:
    """Simple revenue forecasting using moving averages."""
    historical = get_revenue_trends()
    if historical.empty or len(historical) < 3:
        return pd.DataFrame()

    last_values = historical.tail(3)
    avg_growth = last_values["mom_growth_pct"].mean() / 100
    last_revenue = historical["net_revenue"].iloc[-1]

    forecasts = []
    for i in range(1, months_ahead + 1):
        forecast_revenue = last_revenue * ((1 + avg_growth) ** i)
        forecasts.append(
            {
                "forecast_month": i,
                "predicted_revenue": round(forecast_revenue, 2),
                "growth_assumption": round(avg_growth * 100, 2),
            }
        )

    return pd.DataFrame(forecasts)


if __name__ == "__main__":
    print("ST-02 Sales Analytics Module")
    print("=" * 50)

    kpis = get_executive_kpis()
    if kpis:
        print(f"Current Month Revenue: ${kpis.get('current_month_revenue', 0):,.2f}")
        print(f"MoM Growth: {kpis.get('mom_revenue_growth_pct', 0):.1f}%")
        print(f"YoY Growth: {kpis.get('yoy_revenue_growth_pct', 0):.1f}%")
