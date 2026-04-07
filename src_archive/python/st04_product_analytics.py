"""
ST-04: Product & Package Performance
Python module for product analytics and recommendations
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict
from database import execute_query


def get_product_performance(
    category: Optional[str] = None, year_month: Optional[str] = None
) -> pd.DataFrame:
    """Get product performance metrics."""
    query = "SELECT * FROM dk.vw_product_performance_analysis WHERE 1=1"
    if category:
        query += f" AND category = '{category}'"
    if year_month:
        query += f" AND transaction_year_month = '{year_month}'"
    query += " ORDER BY net_revenue DESC"
    return execute_query(query)


def get_category_performance(year_month: Optional[str] = None) -> pd.DataFrame:
    """Get category performance with rankings."""
    query = "SELECT * FROM dk.vw_category_performance WHERE 1=1"
    if year_month:
        query += f" AND transaction_year_month = '{year_month}'"
    query += " ORDER BY category_revenue DESC"
    return execute_query(query)


def get_package_performance(year_month: Optional[str] = None) -> pd.DataFrame:
    """Get package performance analysis."""
    query = "SELECT * FROM dk.vw_package_performance WHERE 1=1"
    if year_month:
        query += f" AND transaction_year_month = '{year_month}'"
    query += " ORDER BY package_revenue DESC"
    return execute_query(query)


def get_cross_sell_patterns(min_affinity: float = 0.1) -> pd.DataFrame:
    """Get cross-sell patterns between categories."""
    query = f"""
    SELECT * FROM dk.vw_cross_sell_patterns
    WHERE affinity_score >= {min_affinity}
    ORDER BY co_occurrence_count DESC
    """
    return execute_query(query)


def get_product_associations(min_confidence: float = 0.1) -> pd.DataFrame:
    """Get product association rules."""
    query = f"""
    SELECT * FROM dk.vw_product_associations
    WHERE confidence_a_to_b >= {min_confidence}
       OR confidence_b_to_a >= {min_confidence}
    ORDER BY pair_count DESC
    """
    return execute_query(query)


def analyze_package_completion() -> pd.DataFrame:
    """Analyze package completion rates."""
    query = """
    SELECT 
        package_name,
        SUM(packages_sold) AS total_sold,
        AVG(avg_completion_rate) AS avg_completion,
        SUM(package_revenue) AS total_revenue,
        AVG(avg_package_value) AS avg_value
    FROM dk.vw_package_performance
    GROUP BY package_name
    ORDER BY total_revenue DESC
    """
    return execute_query(query)


def recommend_products_for_patient(mrn: str, top_n: int = 5) -> pd.DataFrame:
    """Recommend products for a patient based on purchase history."""
    query = f"""
    WITH patient_categories AS (
        SELECT DISTINCT category
        FROM dk.mvw_transaction_flat
        WHERE mrn = '{mrn}'
    ),
    cross_sell_recs AS (
        SELECT 
            category_b AS recommended_category,
            affinity_score
        FROM dk.vw_cross_sell_patterns csp
        JOIN patient_categories pc ON csp.category_a = pc.category
        ORDER BY affinity_score DESC
        LIMIT {top_n}
    )
    SELECT 
        product_code,
        product_name,
        category,
        net_revenue,
        total_units_sold,
        avg_selling_price,
        category_rank
    FROM dk.mvw_product_intelligence
    WHERE category IN (SELECT recommended_category FROM cross_sell_recs)
    ORDER BY net_revenue DESC
    LIMIT {top_n}
    """
    return execute_query(query)


def identify_star_products(year_month: Optional[str] = None) -> pd.DataFrame:
    """Identify star products (high revenue, high growth)."""
    query = """
    SELECT 
        product_code,
        product_name,
        category,
        net_revenue,
        total_units_sold,
        product_tier
    FROM dk.mvw_product_intelligence
    WHERE product_tier = 'Star'
    """
    if year_month:
        query += f" AND transaction_year_month = '{year_month}'"
    query += " ORDER BY net_revenue DESC"
    return execute_query(query)


def export_product_analysis(
    output_path: str = "./docs/output/product_analysis.xlsx",
) -> str:
    """Export product analysis to Excel."""
    products = get_product_performance()
    categories = get_category_performance()
    packages = get_package_performance()
    cross_sell = get_cross_sell_patterns()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="Product Performance", index=False)
        categories.to_excel(writer, sheet_name="Category Performance", index=False)
        packages.to_excel(writer, sheet_name="Package Performance", index=False)
        cross_sell.to_excel(writer, sheet_name="Cross-sell Patterns", index=False)

    return output_path


if __name__ == "__main__":
    print("ST-04 Product & Package Analytics")
    print("=" * 50)

    stars = identify_star_products()
    print(f"\nStar Products: {len(stars)}")
    if not stars.empty:
        print(stars[["product_name", "category", "net_revenue"]].head())
