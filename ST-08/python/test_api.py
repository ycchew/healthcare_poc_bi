"""Tests for ST-08 FastAPI backend endpoints."""

import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest
import pandas as pd

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "ST-01", "python")
)

from api import app, safe_query


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def mock_db():
    with patch("api.get_db") as mock:
        db = MagicMock()
        mock.return_value = db
        yield db


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_root_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200


class TestSafeQuery:
    def test_safe_query_returns_envelope(self, mock_db):
        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        mock_db.execute_query.return_value = df

        result = safe_query("SELECT 1", "test_source")

        assert result["source"] == "test_source"
        assert result["count"] == 2
        assert result["error"] is None
        assert len(result["data"]) == 2
        assert result["columns"] == ["col1", "col2"]

    def test_safe_query_handles_empty_result(self, mock_db):
        mock_db.execute_query.return_value = pd.DataFrame()

        result = safe_query("SELECT 1", "test_source")

        assert result["count"] == 0
        assert result["data"] == []
        assert result["error"] is None

    def test_safe_query_handles_error(self, mock_db):
        mock_db.execute_query.side_effect = Exception("Connection failed")

        result = safe_query("SELECT 1", "test_source")

        assert result["count"] == 0
        assert result["error"] == "Connection failed"

    def test_safe_query_serializes_datetime(self, mock_db):
        df = pd.DataFrame({"date_col": [datetime(2026, 1, 1)], "value": [100]})
        mock_db.execute_query.return_value = df

        result = safe_query("SELECT 1", "test_source")

        assert isinstance(result["data"][0]["date_col"], str)


class TestKPIEndpoint:
    def test_kpi_executive_structure(self, mock_db, client):
        mock_db.execute_query.side_effect = [
            pd.DataFrame(
                {
                    "revenue_total": [31513664.74],
                    "patients_total": [23897],
                    "active_branches": [4],
                    "avg_txn": [1195.13],
                }
            ),
            pd.DataFrame({"month_start": ["2024-12-01"], "mom_growth_pct": [-15.93]}),
            pd.DataFrame(
                {
                    "month_start": ["2024-12-01", "2024-11-01"],
                    "total_patients": [1850, 1905],
                }
            ),
        ]

        response = client.get("/api/kpi/executive")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert len(data["data"]) == 1
        kpi = data["data"][0]
        assert "revenue_mtd" in kpi
        assert "mom_growth_pct" in kpi
        assert "patients_mtd" in kpi
        assert "patient_growth_pct" in kpi
        assert "avg_transaction" in kpi
        assert "active_branches" in kpi


class TestRevenueEndpoints:
    def test_revenue_trend(self, mock_db, client):
        df = pd.DataFrame(
            {
                "month_start": ["2025-01-01", "2025-02-01"],
                "total_revenue": [45000, 48000],
                "total_transactions": [200, 210],
            }
        )
        mock_db.execute_query.return_value = df

        response = client.get("/api/revenue/trend")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["count"] == 2

    def test_revenue_forecast_structure(self, mock_db, client):
        actuals = pd.DataFrame(
            {
                "month_start": pd.to_datetime(["2025-01-01"]),
                "total_revenue": [45000],
            }
        )
        forecast = pd.DataFrame(
            {
                "month_start": pd.to_datetime(["2025-06-01"]),
                "yhat": [47000],
            }
        )
        mock_db.execute_query.side_effect = [actuals, forecast]

        response = client.get("/api/revenue/forecast")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        types = [r["type"] for r in data["data"]]
        assert "actual" in types
        assert "forecast" in types


class TestBranchEndpoints:
    def test_branches_performance(self, mock_db, client):
        df = pd.DataFrame(
            {
                "branch": ["KL CC", "Ampang"],
                "monthly_revenue": [50000, 40000],
                "performance_tier": ["Tier 1", "Tier 2"],
                "growth_status": ["Growing", "Stable"],
            }
        )
        mock_db.execute_query.return_value = df

        response = client.get("/api/branches/performance")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["count"] == 2

    def test_branches_tier_distribution(self, mock_db, client):
        df = pd.DataFrame(
            {
                "performance_tier": ["Tier 1", "Tier 2"],
                "growth_status": ["Growing", "Stable"],
                "branch_count": [3, 5],
            }
        )
        mock_db.execute_query.return_value = df

        response = client.get("/api/branches/tier-distribution")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None


class TestPatientEndpoints:
    def test_patients_dashboard(self, mock_db, client):
        df = pd.DataFrame(
            {
                "total_patients": [2689],
                "active_patients": [1500],
                "at_risk_patients": [400],
                "lost_patients": [200],
            }
        )
        mock_db.execute_query.return_value = df

        response = client.get("/api/patients/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None

    def test_patients_rfm(self, mock_db, client):
        df = pd.DataFrame(
            {
                "mrn": ["M001"],
                "rfm_segment": ["Champions"],
                "r_score": [5],
                "f_score": [5],
            }
        )
        mock_db.execute_query.return_value = df

        response = client.get("/api/patients/rfm")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None

    def test_patients_ltv(self, mock_db, client):
        df = pd.DataFrame(
            {
                "ltv_segment": ["High Value"],
                "patient_count": [50],
            }
        )
        mock_db.execute_query.return_value = df

        response = client.get("/api/patients/ltv")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None

    def test_patients_risk(self, mock_db, client):
        df = pd.DataFrame(
            {
                "patient_id": ["P001"],
                "patient_status": ["AT RISK"],
                "revenue_at_risk": [5000],
            }
        )
        mock_db.execute_query.return_value = df

        response = client.get("/api/patients/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None


class TestProductEndpoints:
    def test_category_mix(self, mock_db, client):
        df = pd.DataFrame({"month": ["2025-01"], "skincare_pct": [15.5]})
        mock_db.execute_query.return_value = df
        response = client.get("/api/products/category-mix")
        assert response.status_code == 200

    def test_package_split(self, mock_db, client):
        df = pd.DataFrame({"standalone_total": [100000], "package_total": [50000]})
        mock_db.execute_query.return_value = df
        response = client.get("/api/products/package-split")
        assert response.status_code == 200

    def test_category_revenue(self, mock_db, client):
        df = pd.DataFrame({"branch": ["KL CC"], "total_revenue": [50000]})
        mock_db.execute_query.return_value = df
        response = client.get("/api/products/category-revenue")
        assert response.status_code == 200

    def test_payments_mode(self, mock_db, client):
        df = pd.DataFrame(
            {"payment_mode": ["DIRECT_PAYMENT"], "transaction_count": [500]}
        )
        mock_db.execute_query.return_value = df
        response = client.get("/api/payments/mode")
        assert response.status_code == 200

    def test_packages_composition(self, mock_db, client):
        df = pd.DataFrame({"branch": ["KL CC"], "total_package_revenue": [30000]})
        mock_db.execute_query.return_value = df
        response = client.get("/api/packages/composition")
        assert response.status_code == 200


class TestMLEndpoints:
    def test_ml_predictions(self, mock_db, client):
        preds = pd.DataFrame({"churn_risk_band": ["Low"], "patient_count": [2000]})
        auc = pd.DataFrame({"model_name": ["churn"], "auc_roc": [0.866]})
        hist = pd.DataFrame({"bin_start": [0.0], "patient_count": [500]})
        mock_db.execute_query.side_effect = [preds, auc, hist]

        response = client.get("/api/ml/predictions")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert "risk_distribution" in data["data"]
        assert "model_info" in data["data"]
        assert "churn_histogram" in data["data"]

    def test_ml_pricing(self, mock_db, client):
        df = pd.DataFrame(
            {"mrn": ["M001"], "offer_type": ["discount"], "churn_probability": [0.75]}
        )
        mock_db.execute_query.return_value = df
        response = client.get("/api/ml/pricing")
        assert response.status_code == 200


class TestGeoEndpoints:
    def test_geo_patients(self, mock_db, client):
        df = pd.DataFrame(
            {"mrn": ["M001"], "patient_lat": [3.1390], "patient_lng": [101.6869]}
        )
        mock_db.execute_query.return_value = df
        response = client.get("/api/geo/patients")
        assert response.status_code == 200

    def test_geo_branches(self, mock_db, client):
        df = pd.DataFrame(
            {"branch_code": ["KLCC"], "branch_lat": [3.1580], "branch_lng": [101.7120]}
        )
        mock_db.execute_query.return_value = df
        response = client.get("/api/geo/branches")
        assert response.status_code == 200

    def test_geo_catchment(self, mock_db, client):
        df = pd.DataFrame(
            {"branch_name": ["KL CC"], "catchment_penetration_pct": [65.5]}
        )
        mock_db.execute_query.return_value = df
        response = client.get("/api/geo/catchment")
        assert response.status_code == 200

    def test_geo_cannibalization(self, mock_db, client):
        df = pd.DataFrame(
            {
                "branch_a": ["KLCC"],
                "branch_b": ["Ampang"],
                "cannibalization_index": [0.35],
            }
        )
        mock_db.execute_query.return_value = df
        response = client.get("/api/geo/cannibalization")
        assert response.status_code == 200

    def test_geo_whitespace(self, mock_db, client):
        df = pd.DataFrame({"cluster_label": ["Area A"], "site_priority_score": [85]})
        mock_db.execute_query.return_value = df
        response = client.get("/api/geo/whitespace")
        assert response.status_code == 200
