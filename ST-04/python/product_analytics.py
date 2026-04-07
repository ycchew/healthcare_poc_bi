"""
ST-04: Product & Package Performance Analytics

Database utilities and analytics functions for product performance,
package analytics, and payment behavior analysis.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

import pandas as pd

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import importlib.util

db_path = project_root / "ST-01" / "python" / "database.py"
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


class ProductAnalyticsManager:
    """Product & Package performance analytics manager.

    Provides programmatic access to product performance, package analytics,
    and payment behavior analysis views.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """Initialize the ProductAnalyticsManager.

        Args:
            db_manager: Optional DatabaseManager instance. If not provided,
                       uses the default from get_db_manager().
        """
        self.db = db_manager or get_db_manager()

    # ==================== Product Performance Methods ====================

    def get_skincare_performance(
        self, branch: Optional[str] = None, months: int = 12
    ) -> pd.DataFrame:
        """Get skincare performance metrics by branch and month.

        Args:
            branch: Optional branch name to filter by
            months: Number of months to look back (default: 12)

        Returns:
            DataFrame with skincare performance metrics including
            standalone and package sales, units, average unit price,
            discount rate, and transaction count.
        """
        if branch:
            query = """
                SELECT 
                    branch,
                    sales_channel,
                    month,
                    standalone_skincare,
                    package_skincare,
                    total_skincare,
                    skincare_units,
                    avg_unit_price,
                    discount_rate,
                    transaction_count
                FROM dk.mvw_skincare_monthly
                WHERE month >= CURRENT_DATE - INTERVAL '1 month' * :months
                  AND branch = :branch
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query, {"months": months, "branch": branch})
        else:
            query = """
                SELECT 
                    branch,
                    sales_channel,
                    month,
                    standalone_skincare,
                    package_skincare,
                    total_skincare,
                    skincare_units,
                    avg_unit_price,
                    discount_rate,
                    transaction_count
                FROM dk.mvw_skincare_monthly
                WHERE month >= CURRENT_DATE - INTERVAL '1 month' * :months
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query, {"months": months})

    def get_supplements_breakdown(self, branch: Optional[str] = None) -> pd.DataFrame:
        """Get supplements breakdown by RM5 vs NA types.

        Args:
            branch: Optional branch name to filter by

        Returns:
            DataFrame with supplements breakdown showing standalone and
            package sales for both RM5 and NA supplement types.
        """
        if branch:
            query = """
                SELECT 
                    branch,
                    month,
                    supplements_rm5_standalone,
                    supplements_rm5_package,
                    supplements_na_standalone,
                    supplements_na_package,
                    total_supplements,
                    supplements_units
                FROM dk.vw_supplements_monthly
                WHERE branch = :branch
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    branch,
                    month,
                    supplements_rm5_standalone,
                    supplements_rm5_package,
                    supplements_na_standalone,
                    supplements_na_package,
                    total_supplements,
                    supplements_units
                FROM dk.vw_supplements_monthly
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query)

    def get_medications_performance(self, branch: Optional[str] = None) -> pd.DataFrame:
        """Get medications standalone vs package split.

        Args:
            branch: Optional branch name to filter by

        Returns:
            DataFrame with medications breakdown showing standalone
            and package sales with percentages.
        """
        if branch:
            query = """
                SELECT 
                    branch,
                    month,
                    standalone_medications,
                    package_medications,
                    total_medications,
                    standalone_pct,
                    package_pct
                FROM dk.vw_medications_monthly
                WHERE branch = :branch
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    branch,
                    month,
                    standalone_medications,
                    package_medications,
                    total_medications,
                    standalone_pct,
                    package_pct
                FROM dk.vw_medications_monthly
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query)

    def get_services_performance(self, branch: Optional[str] = None) -> pd.DataFrame:
        """Get services and consultations performance by branch.

        Args:
            branch: Optional branch name to filter by

        Returns:
            DataFrame with services and consultations revenue.
        """
        if branch:
            query = """
                SELECT 
                    branch,
                    month,
                    consultations,
                    services,
                    total_services
                FROM dk.vw_services_monthly
                WHERE branch = :branch
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    branch,
                    month,
                    consultations,
                    services,
                    total_services
                FROM dk.vw_services_monthly
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query)

    def get_category_mix(self, branch: Optional[str] = None) -> pd.DataFrame:
        """Get category revenue share per branch and month.

        Args:
            branch: Optional branch name to filter by

        Returns:
            DataFrame showing revenue breakdown by category
            (skincare, supplements, medications, services, consultations, other)
            with both absolute amounts and percentages.
        """
        if branch:
            query = """
                SELECT 
                    branch,
                    month,
                    total_revenue,
                    skincare_amount,
                    skincare_pct,
                    supplements_amount,
                    supplements_pct,
                    medications_amount,
                    medications_pct,
                    services_amount,
                    services_pct,
                    consultations_amount,
                    consultations_pct,
                    other_amount,
                    other_pct
                FROM dk.mvw_product_category_mix
                WHERE branch = :branch
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    branch,
                    month,
                    total_revenue,
                    skincare_amount,
                    skincare_pct,
                    supplements_amount,
                    supplements_pct,
                    medications_amount,
                    medications_pct,
                    services_amount,
                    services_pct,
                    consultations_amount,
                    consultations_pct,
                    other_amount,
                    other_pct
                FROM dk.mvw_product_category_mix
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query)

    # ==================== Package Analytics Methods ====================

    def get_package_composition(self, branch: Optional[str] = None) -> pd.DataFrame:
        """Get package breakdown by category.

        Args:
            branch: Optional branch name to filter by

        Returns:
            DataFrame showing package revenue composition across
            services, skincare, medications, supplements, and other categories.
        """
        if branch:
            query = """
                SELECT 
                    branch,
                    month,
                    total_package_revenue,
                    pkg_services_amount,
                    pkg_services_pct,
                    pkg_skincare_amount,
                    pkg_skincare_pct,
                    pkg_medications_amount,
                    pkg_medications_pct,
                    pkg_supplements_amount,
                    pkg_supplements_pct,
                    pkg_other_amount,
                    pkg_other_pct
                FROM dk.mvw_package_composition
                WHERE branch = :branch
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query, {"branch": branch})
        else:
            query = """
                SELECT 
                    branch,
                    month,
                    total_package_revenue,
                    pkg_services_amount,
                    pkg_services_pct,
                    pkg_skincare_amount,
                    pkg_skincare_pct,
                    pkg_medications_amount,
                    pkg_medications_pct,
                    pkg_supplements_amount,
                    pkg_supplements_pct,
                    pkg_other_amount,
                    pkg_other_pct
                FROM dk.mvw_package_composition
                ORDER BY branch, month DESC
            """
            return self.db.execute_query(query)

    def get_redemption_rates(
        self,
        branch: Optional[str] = None,
        status: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get package redemption rates per patient.

        Args:
            branch: Optional branch name to filter by
            status: Optional redemption status (LOW/MEDIUM/HIGH/FULL)

        Returns:
            DataFrame with patient-level package redemption metrics
            including total purchased, redeemed, remaining balance,
            redemption rate, and status.
        """
        filters = []
        params = {}

        if branch:
            filters.append("branch = :branch")
            params["branch"] = branch
        if status:
            filters.append("redemption_status = :status")
            params["status"] = status

        where_clause = "WHERE " + " AND ".join(filters) if filters else ""

        query = f"""
            SELECT 
                mrn,
                branch,
                total_package_purchased,
                total_package_redeemed,
                remaining_balance,
                redemption_rate,
                redemption_status,
                last_redemption_date
            FROM dk.vw_package_redemption
            {where_clause}
            ORDER BY remaining_balance DESC
        """
        return self.db.execute_query(query, params)

    def get_addon_analysis(
        self, mrn: Optional[str] = None, limit: int = 100
    ) -> pd.DataFrame:
        """Get standalone spend during package redemption visits.

        Args:
            mrn: Optional patient MRN to filter by
            limit: Maximum number of records to return (default: 100)

        Returns:
            DataFrame showing standalone spend during visits where
            package offsets were applied.
        """
        if mrn:
            query = """
                SELECT 
                    mrn,
                    visit_date,
                    branch,
                    has_package_offset,
                    standalone_spend,
                    package_spend,
                    total_spend
                FROM dk.vw_package_addon
                WHERE mrn = :mrn
                ORDER BY visit_date DESC
                LIMIT :limit
            """
            return self.db.execute_query(query, {"mrn": mrn, "limit": limit})
        else:
            query = """
                SELECT 
                    mrn,
                    visit_date,
                    branch,
                    has_package_offset,
                    standalone_spend,
                    package_spend,
                    total_spend
                FROM dk.vw_package_addon
                ORDER BY visit_date DESC
                LIMIT :limit
            """
            return self.db.execute_query(query, {"limit": limit})

    def get_package_conversion_demographics(self) -> pd.DataFrame:
        """Get package buyer demographics analysis.

        Returns:
            DataFrame showing package conversion rates by
            demographic segments (race, age band, gender).
        """
        query = """
            SELECT 
                race,
                age_band,
                gender,
                total_patients,
                package_buyers,
                conversion_rate,
                avg_package_value
            FROM dk.mvw_package_conversion_demo
            ORDER BY conversion_rate DESC
        """
        return self.db.execute_query(query)

    # ==================== Payment Behavior Methods ====================

    def get_payment_mode_distribution(self) -> pd.DataFrame:
        """Get payment mode distribution by demographics.

        Returns:
            DataFrame showing payment mode breakdown (DIRECT_PAYMENT,
            PACKAGE_REDEMPTION, LOYALTY_DEPOSIT, ON_BEHALF, OPEN_DEPOSIT)
            by demographic segments.
        """
        query = """
            SELECT 
                race,
                age_band,
                gender,
                payment_mode,
                transaction_count,
                total_amount,
                avg_amount
            FROM dk.mvw_payment_mode_dist
            ORDER BY race, age_band, payment_mode
        """
        return self.db.execute_query(query)

    def get_affordability_stress(
        self, stress_level: Optional[str] = None
    ) -> pd.DataFrame:
        """Get affordability stress analysis per patient.

        Args:
            stress_level: Optional stress level to filter (LOW/MEDIUM/HIGH/CRITICAL)

        Returns:
            DataFrame with patient financial stress metrics including
            outstanding balance ratio and stress classification.
        """
        if stress_level:
            query = """
                SELECT 
                    mrn,
                    avg_monthly_spend,
                    avg_outstanding,
                    stress_ratio,
                    stress_level,
                    total_visits,
                    last_visit_date
                FROM dk.mvw_affordability_stress
                WHERE stress_level = :stress_level
                ORDER BY stress_ratio DESC
            """
            return self.db.execute_query(query, {"stress_level": stress_level})
        else:
            query = """
                SELECT 
                    mrn,
                    avg_monthly_spend,
                    avg_outstanding,
                    stress_ratio,
                    stress_level,
                    total_visits,
                    last_visit_date
                FROM dk.mvw_affordability_stress
                ORDER BY stress_ratio DESC
            """
            return self.db.execute_query(query)

    def get_payment_preference_by_stress(self) -> pd.DataFrame:
        """Get package vs standalone preference by financial stress level.

        Returns:
            DataFrame showing payment preference patterns
            grouped by financial stress level.
        """
        query = """
            SELECT 
                stress_level,
                total_patients,
                prefers_package_count,
                prefers_standalone_count,
                prefers_package_pct,
                prefers_standalone_pct,
                avg_outstanding
            FROM dk.vw_payment_preference_by_stress
            ORDER BY stress_level
        """
        return self.db.execute_query(query)

    def get_stressed_buyers(self, limit: int = 20) -> pd.DataFrame:
        """Get high outstanding patients who are still actively purchasing.

        Args:
            limit: Maximum number of records to return (default: 20)

        Returns:
            DataFrame showing patients with high outstanding balances
            who continue to make purchases, with risk flags.
        """
        query = """
            SELECT 
                mrn,
                patient_name,
                branch,
                outstanding_amount,
                stress_level,
                recent_spend_30d,
                recent_spend_90d,
                days_since_visit,
                risk_flag
            FROM dk.mvw_stressed_buyers
            WHERE risk_flag IN ('HIGH', 'MEDIUM')
            ORDER BY outstanding_amount DESC
            LIMIT :limit
        """
        return self.db.execute_query(query, {"limit": limit})

    # ==================== Utility Methods ====================

    def refresh_product_mvws(self) -> Dict[str, Any]:
        """Refresh all product-related materialized views.

        Returns:
            Dictionary with refresh status, number of views refreshed,
            and detailed results.
        """
        try:
            query = "SELECT * FROM dk.refresh_product_mvws()"
            result = self.db.execute_query(query)
            return {
                "status": "success",
                "views_refreshed": len(result),
                "details": result.to_dict(orient="records"),  # pyright: ignore[reportReturnType]
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def check_data_freshness(self) -> Dict[str, Any]:
        """Check freshness of product data.

        Returns:
            Dictionary with status and freshness information
            for all product-related materialized views.
        """
        query = """
            SELECT 
                'skincare_monthly' AS view_name,
                MAX(month) AS latest_month,
                COUNT(*) AS row_count
            FROM dk.mvw_skincare_monthly
            UNION ALL
            SELECT 
                'package_composition' AS view_name,
                MAX(month) AS latest_month,
                COUNT(*) AS row_count
            FROM dk.mvw_package_composition
            UNION ALL
            SELECT 
                'product_category_mix' AS view_name,
                MAX(month) AS latest_month,
                COUNT(*) AS row_count
            FROM dk.mvw_product_category_mix
        """
        result = self.db.execute_query(query)
        return {
            "status": "success",
            "freshness": result.to_dict(orient="records"),  # pyright: ignore[reportReturnType]
        }

    def generate_product_report(self, report_type: str = "executive") -> Dict[str, Any]:
        """Generate product analytics report.

        Args:
            report_type: Type of report to generate:
                        'executive', 'product', 'package', or 'payment'

        Returns:
            Dictionary containing the requested report data.
        """
        if report_type == "executive":
            return {
                "skincare_summary": self.get_skincare_performance(months=3).to_dict(  # pyright: ignore[reportReturnType]
                    orient="records"
                ),
                "category_mix": self.get_category_mix().to_dict(orient="records"),  # pyright: ignore[reportReturnType]
                "package_composition": self.get_package_composition().to_dict(  # pyright: ignore[reportReturnType]
                    orient="records"
                ),
                "stressed_buyers": self.get_stressed_buyers(limit=10).to_dict(  # pyright: ignore[reportReturnType]
                    orient="records"
                ),
            }
        elif report_type == "product":
            return {
                "skincare": self.get_skincare_performance().to_dict(orient="records"),  # pyright: ignore[reportReturnType]
                "supplements": self.get_supplements_breakdown().to_dict(
                    orient="records"
                ),  # pyright: ignore[reportReturnType]
                "medications": self.get_medications_performance().to_dict(
                    orient="records"
                ),  # pyright: ignore[reportReturnType]
                "services": self.get_services_performance().to_dict(orient="records"),  # pyright: ignore[reportReturnType]
            }
        elif report_type == "package":
            return {
                "composition": self.get_package_composition().to_dict(orient="records"),  # pyright: ignore[reportReturnType]
                "redemption": self.get_redemption_rates().to_dict(orient="records"),  # pyright: ignore[reportReturnType]
                "conversion": self.get_package_conversion_demographics().to_dict(
                    orient="records"
                ),  # pyright: ignore[reportReturnType]
            }
        elif report_type == "payment":
            return {
                "payment_modes": self.get_payment_mode_distribution().to_dict(
                    orient="records"
                ),  # pyright: ignore[reportReturnType]
                "stress_analysis": self.get_affordability_stress().to_dict(
                    orient="records"
                ),  # pyright: ignore[reportReturnType]
                "stressed_buyers": self.get_stressed_buyers().to_dict(orient="records"),  # pyright: ignore[reportReturnType]
            }
        else:
            return {"error": f"Unknown report type: {report_type}"}


def run_product_report(
    report_type: str = "executive", db_manager: Optional[DatabaseManager] = None
) -> Dict[str, Any]:
    manager = ProductAnalyticsManager(db_manager=db_manager)
    return manager.generate_product_report(report_type)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    print("Product Analytics Report")
    print("=" * 60)

    manager = ProductAnalyticsManager()

    print("\n1. Skincare Performance (Last 3 months):")
    skincare = manager.get_skincare_performance(months=3)
    print(f"   Records: {len(skincare)}")
    if not skincare.empty:
        print(skincare.head())

    print("\n2. Category Mix:")
    category_mix = manager.get_category_mix()
    print(f"   Records: {len(category_mix)}")

    print("\n3. Package Composition:")
    package_comp = manager.get_package_composition()
    print(f"   Records: {len(package_comp)}")

    print("\n4. Stressed Buyers (Top 10):")
    stressed = manager.get_stressed_buyers(limit=10)
    print(f"   Records: {len(stressed)}")

    print("\n5. Data Freshness:")
    freshness = manager.check_data_freshness()
    for key, value in freshness.items():
        print(f"   {key}: {value}")
