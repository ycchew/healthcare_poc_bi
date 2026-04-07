"""
ST-08: ECharts Dashboard — FastAPI Backend
Serves JSON data from PostgreSQL materialized views for ECharts frontend.
"""

import sys
import os
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add ST-01 to path for DatabaseManager
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "ST-01", "python")
)
from database import DatabaseManager

app = FastAPI(title="Healthcare Analytics Dashboard API", version="1.0.0")

# Default date range matching available data
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2024-12-31"

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def get_db() -> DatabaseManager:
    """Get DatabaseManager singleton."""
    return DatabaseManager.get_instance()


def safe_query(query: str, source: str) -> Dict[str, Any]:
    """Execute query and return standardized envelope."""
    try:
        db = get_db()
        df = db.execute_query(query)
        if df is None or df.empty:
            return {
                "data": [],
                "columns": [],
                "source": source,
                "count": 0,
                "error": None,
            }
        # Convert DataFrame to list of dicts, handle datetime serialization
        records = df.to_dict(orient="records")
        for record in records:
            for key, value in record.items():
                if isinstance(value, (datetime, date)):
                    record[key] = value.isoformat()
                elif hasattr(value, "item"):  # numpy types
                    record[key] = value.item()
                elif value is None or (
                    isinstance(value, float) and str(value) == "nan"
                ):
                    record[key] = None
        return {
            "data": records,
            "columns": list(df.columns),
            "source": source,
            "count": len(records),
            "error": None,
        }
    except Exception as e:
        return {
            "data": [],
            "columns": [],
            "source": source,
            "count": 0,
            "error": str(e),
        }


@app.get("/")
async def root():
    """Serve the dashboard frontend."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve empty response for favicon to prevent 404 errors."""
    from fastapi.responses import Response

    return Response(content="", media_type="image/x-icon")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        db = get_db()
        result = db.execute_query("SELECT 1 as ok")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}


# === KPI & REVENUE ENDPOINTS ===


@app.get("/api/kpi/executive")
async def kpi_executive(
    start_date: str = Query(default=DEFAULT_START),
    end_date: str = Query(default=DEFAULT_END),
):
    """Executive Overview KPI cards with date range filter."""
    try:
        db = get_db()

        revenue_df = db.execute_query(f"""
            SELECT COALESCE(SUM(total_collected), 0) as revenue_total,
                   COALESCE(SUM(unique_patients), 0) as patients_total,
                   COUNT(DISTINCT branch) as active_branches,
                   COALESCE(AVG(avg_transaction_value), 0) as avg_txn
            FROM dk.vw_daily_sales_summary
            WHERE transaction_date BETWEEN '{start_date}' AND '{end_date}'
        """)
        revenue_total = (
            float(revenue_df.iloc[0]["revenue_total"])
            if revenue_df is not None and not revenue_df.empty
            else 0
        )
        patients_total = (
            int(revenue_df.iloc[0]["patients_total"])
            if revenue_df is not None and not revenue_df.empty
            else 0
        )
        active_branches = (
            int(revenue_df.iloc[0]["active_branches"])
            if revenue_df is not None and not revenue_df.empty
            else 0
        )
        avg_txn = (
            float(revenue_df.iloc[0]["avg_txn"])
            if revenue_df is not None and not revenue_df.empty
            else 0
        )

        # MoM growth: last month in range vs prior month
        mom_df = db.execute_query(f"""
            SELECT month_start, mom_growth_pct
            FROM dk.vw_monthly_sales_trend
            WHERE month_start BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY month_start DESC
            LIMIT 1
        """)
        mom_growth = (
            float(mom_df.iloc[0]["mom_growth_pct"])
            if mom_df is not None
            and not mom_df.empty
            and "mom_growth_pct" in mom_df.columns
            else 0
        )

        # Patient growth: compare last month vs prior month in range
        patient_growth_df = db.execute_query(f"""
            SELECT month_start, total_patients
            FROM dk.vw_monthly_sales_trend
            WHERE month_start BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY month_start DESC
            LIMIT 2
        """)
        patient_growth_pct = 0
        if patient_growth_df is not None and len(patient_growth_df) >= 2:
            curr = int(patient_growth_df.iloc[0]["total_patients"])
            prior = int(patient_growth_df.iloc[1]["total_patients"])
            if prior > 0:
                patient_growth_pct = round((curr - prior) / prior * 100, 1)

        return {
            "data": [
                {
                    "revenue_mtd": revenue_total,
                    "mom_growth_pct": mom_growth,
                    "patients_mtd": patients_total,
                    "patient_growth_pct": patient_growth_pct,
                    "avg_transaction": avg_txn,
                    "active_branches": active_branches,
                }
            ],
            "columns": [
                "revenue_mtd",
                "mom_growth_pct",
                "patients_mtd",
                "patient_growth_pct",
                "avg_transaction",
                "active_branches",
            ],
            "source": "vw_daily_sales_summary + vw_monthly_sales_trend",
            "count": 1,
            "error": None,
        }
    except Exception as e:
        return {
            "data": [],
            "columns": [],
            "source": "kpi_executive",
            "count": 0,
            "error": str(e),
        }


@app.get("/api/revenue/trend")
async def revenue_trends(
    start_date: str = Query(default=DEFAULT_START),
    end_date: str = Query(default=DEFAULT_END),
):
    """Revenue trend within date range for line+column combo chart."""
    return safe_query(
        f"""
        SELECT month_start, total_revenue, total_transactions, total_patients,
               moving_avg_3m, mom_growth_pct
        FROM dk.vw_monthly_sales_trend
        WHERE month_start BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY month_start ASC
    """,
        "vw_monthly_sales_trend",
    )


@app.get("/api/revenue/forecast")
async def revenue_forecast(
    start_date: str = Query(default=DEFAULT_START),
    end_date: str = Query(default=DEFAULT_END),
):
    """Combined actuals + forecast data for trend chart with confidence band."""
    try:
        db = get_db()

        actuals_df = db.execute_query(f"""
            SELECT month_start, total_revenue
            FROM dk.vw_monthly_sales_trend
            WHERE month_start BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY month_start ASC
        """)

        forecast_df = db.execute_query("""
            SELECT DATE_TRUNC('month', forecast_date)::date AS month_start,
                   SUM(yhat) AS yhat
            FROM dk.sales_forecast
            WHERE forecast_date <= (SELECT MAX(forecast_date) FROM dk.sales_forecast WHERE forecast_date <= CURRENT_DATE + INTERVAL '90 days')
            GROUP BY DATE_TRUNC('month', forecast_date)::date
            ORDER BY month_start ASC
        """)

        records = []

        if actuals_df is not None and not actuals_df.empty:
            for _, row in actuals_df.iterrows():
                records.append(
                    {
                        "date": row["month_start"].isoformat()
                        if hasattr(row["month_start"], "isoformat")
                        else str(row["month_start"]),
                        "value": float(row["total_revenue"]),
                        "type": "actual",
                        "lower": None,
                        "upper": None,
                    }
                )

        if forecast_df is not None and not forecast_df.empty:
            for _, row in forecast_df.iterrows():
                yhat = float(row["yhat"])
                records.append(
                    {
                        "date": row["month_start"].isoformat()
                        if hasattr(row["month_start"], "isoformat")
                        else str(row["month_start"]),
                        "value": yhat,
                        "type": "forecast",
                        "lower": round(yhat * 0.85, 2),
                        "upper": round(yhat * 1.15, 2),
                    }
                )

        return {
            "data": records,
            "columns": ["date", "value", "type", "lower", "upper"],
            "source": "vw_monthly_sales_trend + sales_forecast",
            "count": len(records),
            "error": None,
        }
    except Exception as e:
        return {
            "data": [],
            "columns": [],
            "source": "revenue_forecast",
            "count": 0,
            "error": str(e),
        }


# === BRANCH ENDPOINTS ===


@app.get("/api/branches/performance")
async def branches_performance():
    """Branch performance data for bar chart and performance table."""
    return safe_query(
        """
        SELECT branch,
               SUM(monthly_revenue) as monthly_revenue,
               SUM(monthly_transactions) as monthly_transactions,
               SUM(monthly_patients) as monthly_patients,
               SUM(monthly_collected) as monthly_collected,
               SUM(monthly_discount) as monthly_discount,
               AVG(avg_txn_value) as avg_txn_value,
               MAX(performance_tier) as performance_tier,
               MAX(growth_status) as growth_status,
               AVG(mom_revenue_growth_pct) as mom_revenue_growth_pct,
               AVG(mom_transaction_growth_pct) as mom_transaction_growth_pct,
               AVG(mom_patient_growth_pct) as mom_patient_growth_pct,
               AVG(standalone_mix_pct) as standalone_mix_pct,
               AVG(package_mix_pct) as package_mix_pct,
               AVG(discount_rate_pct) as discount_rate_pct
        FROM dk.vw_branch_performance
        GROUP BY branch
        ORDER BY monthly_revenue DESC
    """,
        "vw_branch_performance",
    )


@app.get("/api/branches/tier-distribution")
async def branches_tier_distribution():
    """Branch tier counts and growth status distribution."""
    return safe_query(
        """
        SELECT performance_tier, growth_status,
               COUNT(*) as branch_count,
               SUM(monthly_revenue) as total_revenue
        FROM dk.vw_branch_performance
        GROUP BY performance_tier, growth_status
    """,
        "vw_branch_performance",
    )


# === PATIENT ENDPOINTS ===


@app.get("/api/patients/dashboard")
async def patients_dashboard():
    """Patient dashboard aggregates across all branches for KPI cards and status distribution."""
    return safe_query(
        """
        SELECT SUM(total_patients) as total_patients,
               SUM(active_patients) as active_patients,
               SUM(at_risk_patients) as at_risk_patients,
               SUM(high_risk_patients) as high_risk_patients,
               SUM(lost_patients) as lost_patients,
               SUM(new_patients) as new_patients,
               SUM(platinum_patients) as platinum_patients,
               SUM(gold_patients) as gold_patients,
               SUM(silver_patients) as silver_patients,
               SUM(bronze_patients) as bronze_patients,
               SUM(total_revenue) as total_revenue,
               SUM(revenue_at_risk) as revenue_at_risk
        FROM dk.vw_patient_dashboard
    """,
        "vw_patient_dashboard",
    )


@app.get("/api/patients/rfm")
async def patients_rfm():
    """RFM segmentation data for treemap and matrix heatmap."""
    return safe_query(
        """
        SELECT patient_id,
               segment AS rfm_segment,
               r_score, f_score, m_score,
               monetary, frequency, recency_days
        FROM dk.vw_patient_rfm
    """,
        "vw_patient_rfm",
    )


@app.get("/api/patients/ltv")
async def patients_ltv():
    """LTV distribution data."""
    return safe_query(
        """
        SELECT ltv_segment,
               COUNT(*) as patient_count,
               AVG(predicted_annual_ltv) as avg_predicted_ltv,
               AVG(observed_ltv) as avg_observed_ltv
        FROM dk.mvw_patient_ltv
        GROUP BY ltv_segment
    """,
        "mvw_patient_ltv",
    )


@app.get("/api/patients/risk")
async def patients_risk():
    """At-risk and high-risk patient list for alerts and action table."""
    return safe_query(
        """
        SELECT patient_id, patient_status, value_tier,
               days_since_last_visit, revenue_at_risk, risk_score,
               retention_action, preferred_branch
        FROM dk.vw_patient_risk
        WHERE patient_status IN ('AT RISK', 'HIGH RISK')
        ORDER BY revenue_at_risk DESC
        LIMIT 50
    """,
        "vw_patient_risk",
    )


# === PRODUCT & PAYMENT ENDPOINTS ===


@app.get("/api/products/category-mix")
async def products_category_mix():
    """Category mix percentages by month for stacked area chart."""
    return safe_query(
        """
        SELECT month, skincare_pct, supplements_pct, medications_pct,
               services_pct, consultations_pct, other_pct,
               total_revenue
        FROM dk.vw_category_mix
        ORDER BY month ASC
    """,
        "vw_category_mix",
    )


@app.get("/api/products/package-split")
async def products_package_split():
    """Package vs standalone revenue split."""
    return safe_query(
        """
        SELECT
            SUM(standalone_sales_total) as standalone_total,
            SUM(package_sales_total) as package_total
        FROM dk.vw_daily_sales_summary
    """,
        "vw_daily_sales_summary",
    )


@app.get("/api/products/category-revenue")
async def products_category_revenue():
    """Category revenue breakdown by branch."""
    # First aggregate by branch to combine monthly records for each branch
    return safe_query(
        """
        SELECT branch,
               SUM(consultations_revenue) as consultations_revenue,
               SUM(services_revenue) as services_revenue,
               SUM(medications_revenue) as medications_revenue,
               SUM(supplements_revenue) as supplements_revenue,
               SUM(skincare_revenue) as skincare_revenue,
               SUM(other_products_revenue) as other_products_revenue,
               SUM(total_revenue) as total_revenue,
               SUM(unique_patients) as unique_patients
        FROM dk.vw_product_performance  
        GROUP BY branch
        ORDER BY total_revenue DESC
    """,
        "vw_product_performance",
    )


@app.get("/api/payments/mode")
async def payments_mode():
    """Payment mode distribution."""
    return safe_query(
        """
        SELECT payment_mode,
               SUM(transaction_count) as transaction_count,
               SUM(total_amount) as total_amount,
               CASE WHEN SUM(transaction_count) > 0 
                    THEN SUM(total_amount) / SUM(transaction_count) 
                    ELSE 0 END as avg_amount
        FROM dk.vw_payment_mode_distribution
        GROUP BY payment_mode
        ORDER BY transaction_count DESC
    """,
        "vw_payment_mode_distribution",
    )


@app.get("/api/packages/composition")
async def packages_composition():
    """Package composition breakdown."""
    return safe_query(
        """
        SELECT branch, month, total_package_revenue,
               pkg_services_pct, pkg_skincare_pct, pkg_medications_pct,
               pkg_supplements_pct, pkg_other_pct
        FROM dk.vw_package_composition
        ORDER BY total_package_revenue DESC
    """,
        "vw_package_composition",
    )


# === ML ENDPOINTS ===


@app.get("/api/ml/predictions")
async def ml_predictions():
    """ML prediction data for churn distribution, risk levels, and model AUC."""
    try:
        db = get_db()

        preds_df = db.execute_query("""
            SELECT churn_risk_band,
                   COUNT(*) as patient_count,
                   AVG(churn_probability) as avg_churn_prob,
                   AVG(pkg_upsell_prob) as avg_upsell_prob,
                   COUNT(CASE WHEN pkg_upsell_prob > 0.5 THEN 1 END) as upsell_count
            FROM dk.ml_predictions
            GROUP BY churn_risk_band
        """)

        auc_df = db.execute_query("""
            SELECT model_name, auc_roc, train_date
            FROM dk.model_metadata
            ORDER BY train_date DESC
            LIMIT 1
        """)

        histogram_df = db.execute_query("""
            SELECT
                FLOOR(churn_probability * 10) / 10 as bin_start,
                COUNT(*) as patient_count
            FROM dk.ml_predictions
            GROUP BY FLOOR(churn_probability * 10) / 10
            ORDER BY bin_start
        """)

        records = {
            "risk_distribution": preds_df.to_dict(orient="records")
            if preds_df is not None and not preds_df.empty
            else [],
            "model_info": auc_df.to_dict(orient="records")
            if auc_df is not None and not auc_df.empty
            else [],
            "churn_histogram": histogram_df.to_dict(orient="records")
            if histogram_df is not None and not histogram_df.empty
            else [],
        }

        for key in records:
            for record in records[key]:
                for k, v in record.items():
                    if isinstance(v, (datetime, date)):
                        record[k] = v.isoformat()
                    elif hasattr(v, "item"):
                        record[k] = v.item()

        return {
            "data": records,
            "columns": ["risk_distribution", "model_info", "churn_histogram"],
            "source": "ml_predictions + model_metadata",
            "count": sum(len(v) for v in records.values()),
            "error": None,
        }
    except Exception as e:
        return {
            "data": [],
            "columns": [],
            "source": "ml_predictions",
            "count": 0,
            "error": str(e),
        }


@app.get("/api/ml/pricing")
async def ml_pricing():
    """Dynamic pricing offers and outreach list."""
    return safe_query(
        """
        SELECT mrn, offer_type, discount_pct, max_discount_rm,
               churn_probability, pkg_upsell_prob, promo_segment,
               value_tier, rfm_segment, recommended_action
        FROM dk.vw_dynamic_pricing
        ORDER BY churn_probability DESC
        LIMIT 100
    """,
        "vw_dynamic_pricing",
    )


# === GEOSPATIAL ENDPOINTS ===


@app.get("/api/geo/patients")
async def geo_patients(
    start_date: str = Query(default=DEFAULT_START),
    end_date: str = Query(default=DEFAULT_END),
):
    """Patient geospatial data for map scatter visualization."""
    # Include patient data with distance bands to enable the distance band distribution visual
    # Returns basic geo coordinates with distance band for each patient in active date range
    return safe_query(
        f"""
        SELECT 
            pg.mrn,
            pg.patient_lat,
            pg.patient_lng,
            pbd.distance_band as nearest_branch_dist_band
        FROM dk.patient_geocode pg
        INNER JOIN (
            SELECT DISTINCT mrn
            FROM dk.collection 
            WHERE date BETWEEN '{start_date}' AND '{end_date}'
              AND mrn IS NOT NULL
        ) active ON pg.mrn = active.mrn
        LEFT JOIN dk.patient_branch_distance pbd ON pg.mrn = pbd.mrn 
            AND pbd.is_nearest_branch = TRUE
        WHERE pg.patient_lat IS NOT NULL 
          AND pg.patient_lng IS NOT NULL
    """,
        "patient_geocode_distances",
    )


@app.get("/api/geo/branches")
async def geo_branches(
    start_date: str = Query(default=DEFAULT_START),
    end_date: str = Query(default=DEFAULT_END),
):
    """Branch location data for map circles."""
    return safe_query(
        f"""
        WITH branch_metrics AS (
            SELECT 
                branch as branch_code,
                SUM(amount_collected) AS total_revenue,
                COUNT(DISTINCT mrn) AS primary_patients
            FROM dk.collection 
            WHERE date BETWEEN '{start_date}' AND '{end_date}'
              AND branch IS NOT NULL
            GROUP BY branch
        )
        SELECT 
            bm.branch_code,
            bm.branch_code as branch_name,
            bm.branch_lat,
            bm.branch_lng,
            bm.catchment_radius_km,
            COALESCE(bm2.total_revenue, 0) AS total_revenue,
            COALESCE(bm2.primary_patients, 0) AS primary_patients
        FROM dk.branch_master bm
        LEFT JOIN branch_metrics bm2 ON bm.branch_code = bm2.branch_code
        WHERE bm.branch_lat IS NOT NULL  
          AND bm.branch_lng IS NOT NULL  
          AND bm.is_active = TRUE
    """,
        "branch_master",
    )


@app.get("/api/geo/catchment")
async def geo_catchment(
    start_date: str = Query(default=DEFAULT_START),
    end_date: str = Query(default=DEFAULT_END),
):
    """Branch catchment penetration data."""
    # First calculate patient transaction data within date range that relates to branch distances
    return safe_query(
        f"""
        WITH patient_trx_in_period AS (
            SELECT DISTINCT mrn
            FROM dk.collection_report
            WHERE csv_date BETWEEN '{start_date}' AND '{end_date}'
              AND mrn IS NOT NULL
        ),
        branch_catchment_with_dates AS (
            SELECT 
                bm.branch_code,
                bm.branch_name,
                COUNT(DISTINCT CASE WHEN pbd.is_nearest_branch AND ptrx.mrn IS NOT NULL THEN pbd.mrn END) AS total_patients_nearest,
                COUNT(DISTINCT CASE WHEN pbd.is_within_catchment AND pbd.is_nearest_branch AND ptrx.mrn IS NOT NULL THEN pbd.mrn END) AS patients_within_catchment,
                COUNT(DISTINCT CASE WHEN NOT pbd.is_within_catchment AND pbd.is_nearest_branch AND ptrx.mrn IS NOT NULL THEN pbd.mrn END) AS patients_outside_catchment,
                ROUND(AVG(CASE WHEN pbd.is_nearest_branch AND ptrx.mrn IS NOT NULL THEN pbd.distance_km END)::NUMERIC, 2) AS avg_distance_km
            FROM dk.branch_master bm
            LEFT JOIN dk.patient_branch_distance pbd ON bm.branch_code = pbd.branch_code
            LEFT JOIN patient_trx_in_period ptrx ON pbd.mrn = ptrx.mrn
            WHERE bm.is_active = TRUE
            GROUP BY bm.branch_code, bm.branch_name
        )
        SELECT branch_name,
               patients_within_catchment,
               patients_outside_catchment,
               CASE 
                   WHEN total_patients_nearest > 0 
                   THEN ROUND((patients_within_catchment * 100.0 / total_patients_nearest)::NUMERIC, 2)
                   ELSE 0 
               END AS catchment_penetration_pct,
               avg_distance_km,
               total_patients_nearest
        FROM branch_catchment_with_dates
        ORDER BY catchment_penetration_pct DESC
    """,
        "vw_branch_catchment_summary",
    )


@app.get("/api/geo/cannibalization")
async def geo_cannibalization():
    """Cannibalization risk matrix between branch pairs."""
    return safe_query(
        """
        SELECT branch_a, branch_a_name, branch_b, branch_b_name,
               branch_distance_km, shared_patient_count,
               cannibalization_index, cannibalization_severity, alert_status
        FROM dk.vw_cannibalization_summary
        ORDER BY cannibalization_index DESC
    """,
        "vw_cannibalization_summary",
    )


@app.get("/api/geo/whitespace")
async def geo_whitespace():
    """Whitespace expansion opportunities."""
    # Using base tables since views may not be generated yet
    return safe_query(
        """
        -- Identify dense patient clusters outside major catchment zones  
        -- Get geographically clustered patient groups far from branches
        WITH patient_clusters AS (
            SELECT
                ROUND(patient_lat::numeric, 1) AS lat_group,
                ROUND(patient_lng::numeric, 1) AS lng_group,
                COUNT(mrn) AS patient_count,
                AVG(patient_lat) AS center_lat,
                AVG(patient_lng) AS center_lng
            FROM dk.patient_geocode 
            WHERE patient_lat IS NOT NULL AND patient_lng IS NOT NULL
            GROUP BY ROUND(patient_lat::numeric, 1), ROUND(patient_lng::numeric, 1)
            HAVING COUNT(mrn) >= 5
        ),
        branch_distances AS (
            SELECT 
                pc.lat_group,
                pc.lng_group, 
                pc.center_lat,
                pc.center_lng,
                pc.patient_count,
                bm.branch_code,
                bm.branch_name,
                ST_Distance(
                    ST_Point(pc.center_lng, pc.center_lat)::GEOGRAPHY,
                    ST_Point(bm.branch_lng, bm.branch_lat)::GEOGRAPHY
                ) / 1000 AS distance_km
            FROM patient_clusters pc
            CROSS JOIN dk.branch_master bm
            WHERE bm.is_active = TRUE
              AND bm.branch_lat IS NOT NULL 
              AND bm.branch_lng IS NOT NULL
        ),
        ranked_clusters AS (
            SELECT
                *,
                ROW_NUMBER() OVER (PARTITION BY lat_group, lng_group ORDER BY distance_km ASC) AS nearest_rank
            FROM branch_distances
        )
        SELECT 
            'Area_' || lat_group || '_' || lng_group AS cluster_label,
            center_lat AS centroid_lat,
            center_lng AS centroid_lng,
            patient_count,
            branch_name AS nearest_branch_name,
            ROUND(distance_km::numeric, 2) AS distance_to_nearest_branch_km,
            patient_count * distance_km AS site_priority_score,
            CASE 
                WHEN distance_km > 25 THEN 'High'
                WHEN distance_km > 15 THEN 'Medium' 
                ELSE 'Low'
            END AS expansion_priority,
            patient_count * 1800 AS est_annual_market_rm
        FROM ranked_clusters
        WHERE nearest_rank = 1  -- Take only the nearest branch per cluster
          AND distance_km > 12  -- Only consider clusters far from closest branch
        ORDER BY site_priority_score DESC
        LIMIT 20
        """,
        "geospatial_whitespace_clusters",
    )


@app.get("/api/geo/whitespace/patients/{cluster_label}")
async def geo_whitespace_patients(cluster_label: str):
    """Get patient list for a specific whitespace opportunity area for outreach."""
    # Parse cluster label into coordinates (e.g., Area_6.0_116.1 -> lat ~ 6.0, lng ~ 116.1)
    # Cluster label format is "Area_lat_lng" where lat and lng are rounded values
    try:
        # Extract lat and lng from cluster label like "Area_6.0_116.1"
        parts = cluster_label.split("_")
        if len(parts) != 3:
            return {
                "error": f"Invalid cluster label format: {cluster_label}. Expected: Area_lat_lng"
            }

        lat_str, lng_str = parts[1], parts[2]
        lat = float(lat_str)
        lng = float(lng_str)
    except ValueError:
        return {"error": f"Invalid coordinates in cluster label: {cluster_label}"}

    # Query for patients within the same coordinate grouping using only known columns
    result = safe_query(
        f"""
        SELECT 
            pg.mrn,
            pg.patient_lat,
            pg.patient_lng,
            pg.city_name,
            pg.state_name,
            pg.zip as postcode
        FROM dk.patient_geocode pg
        WHERE ROUND(pg.patient_lat::numeric, 1) = {lat}
          AND ROUND(pg.patient_lng::numeric, 1) = {lng}
          AND pg.patient_lat IS NOT NULL
          AND pg.patient_lng IS NOT NULL
        LIMIT 100
        """,
        "cluster_patients",
    )
    return result
