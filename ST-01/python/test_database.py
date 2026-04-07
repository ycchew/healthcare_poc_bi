"""
ST-01: Data Foundation & Infrastructure
Test suite for database.py module using live database.

To run tests:
    pytest test_database.py -v

Requirements:
    pip install pytest pandas sqlalchemy psycopg2-binary python-dotenv
    Configure .env with DB_* credentials
"""

import os
import sys
from pathlib import Path
from typing import Generator

import pandas as pd
import pytest
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent))

from database import (
    DatabaseManager,
    get_db_manager,
    execute_query,
    get_db_connection_string,
)


@pytest.fixture(scope="module")
def db() -> Generator[DatabaseManager, None, None]:
    manager = DatabaseManager()
    yield manager
    manager.close()


@pytest.fixture(scope="module")
def db_env_configured() -> bool:
    return all(
        os.getenv(var)
        for var in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    )


class TestDatabaseConnection:
    def test_connection_string_format(self, db: DatabaseManager):
        assert "postgresql://" in db.connection_string
        assert "@" in db.connection_string
        assert "/" in db.connection_string

    def test_engine_creation(self, db: DatabaseManager):
        assert db.engine is not None

    def test_connection_works(self, db: DatabaseManager):
        result = db.execute_query("SELECT 1 as test")
        assert isinstance(result, pd.DataFrame)
        assert result.iloc[0]["test"] == 1


class TestDatabaseManagerQueries:
    def test_execute_query_dataframe(self, db: DatabaseManager):
        result = db.execute_query("SELECT 1 as id, 'test' as name")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert result.iloc[0]["id"] == 1
        assert result.iloc[0]["name"] == "test"

    def test_execute_query_with_params(self, db: DatabaseManager):
        result = db.execute_query("SELECT :val as param_value", params={"val": 42})
        assert result.iloc[0]["param_value"] == 42

    def test_execute_query_raw(self, db: DatabaseManager):
        result = db.execute_query_raw("SELECT 1 as test")
        assert result is not None
        row = result.fetchone()
        assert row[0] == 1


class TestSchemaExists:
    def test_dk_schema_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'dk'"
        )
        assert len(result) == 1

    def test_patient_table_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'dk' AND table_name = 'patient'"
        )
        assert len(result) == 1

    def test_collection_table_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'dk' AND table_name = 'collection'"
        )
        assert len(result) == 1

    def test_collection_report_table_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'dk' AND table_name = 'collection_report'"
        )
        assert len(result) == 1


class TestMaterializedViews:
    def test_mvw_patient_enriched_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT matviewname FROM pg_matviews WHERE schemaname = 'dk' AND matviewname = 'mvw_patient_enriched'"
        )
        assert len(result) == 1

    def test_mvw_patient_enriched_has_data(self, db: DatabaseManager):
        result = db.execute_query("SELECT COUNT(*) as cnt FROM dk.mvw_patient_enriched")
        assert result.iloc[0]["cnt"] > 0

    def test_mvw_transaction_flat_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT matviewname FROM pg_matviews WHERE schemaname = 'dk' AND matviewname = 'mvw_transaction_flat'"
        )
        assert len(result) == 1

    def test_mvw_patient_rfm_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT matviewname FROM pg_matviews WHERE schemaname = 'dk' AND matviewname = 'mvw_patient_rfm'"
        )
        assert len(result) == 1

    def test_mvw_patient_ltv_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT matviewname FROM pg_matviews WHERE schemaname = 'dk' AND matviewname = 'mvw_patient_ltv'"
        )
        assert len(result) == 1

    def test_mvw_branch_performance_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT matviewname FROM pg_matviews WHERE schemaname = 'dk' AND matviewname = 'mvw_branch_performance'"
        )
        assert len(result) == 1

    def test_mvw_calendar_effects_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT matviewname FROM pg_matviews WHERE schemaname = 'dk' AND matviewname = 'mvw_calendar_effects'"
        )
        assert len(result) == 1


class TestDataQuality:
    def test_check_data_quality(self, db: DatabaseManager):
        result = db.check_data_quality()
        assert isinstance(result, dict)
        assert result["status"] == "OK"
        assert "patient_row_count" in result
        assert "collection_row_count" in result
        assert "collection_report_row_count" in result

    def test_patient_mrn_coverage(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as total, COUNT(mrn) as with_mrn FROM dk.patient"
        )
        total = result.iloc[0]["total"]
        with_mrn = result.iloc[0]["with_mrn"]
        coverage_pct = (with_mrn / total * 100) if total > 0 else 0
        assert coverage_pct > 90

    def test_collection_has_dates(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as null_dates FROM dk.collection WHERE date IS NULL"
        )
        assert result.iloc[0]["null_dates"] == 0


class TestPatientData:
    def test_patient_count(self, db: DatabaseManager):
        result = db.execute_query("SELECT COUNT(*) as cnt FROM dk.patient")
        assert result.iloc[0]["cnt"] > 0

    def test_patient_has_mrn(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT mrn FROM dk.patient WHERE mrn IS NOT NULL LIMIT 1"
        )
        assert len(result) == 1

    def test_patient_columns(self, db: DatabaseManager):
        result = db.execute_query("SELECT * FROM dk.patient LIMIT 1")
        assert "mrn" in result.columns
        assert "gender" in result.columns
        assert "dob" in result.columns
        assert "city_name" in result.columns
        assert "state_name" in result.columns


class TestCollectionData:
    def test_collection_count(self, db: DatabaseManager):
        result = db.execute_query("SELECT COUNT(*) as cnt FROM dk.collection")
        assert result.iloc[0]["cnt"] > 0

    def test_collection_columns(self, db: DatabaseManager):
        result = db.execute_query("SELECT * FROM dk.collection LIMIT 1")
        assert "row_number" in result.columns
        assert "date" in result.columns
        assert "branch" in result.columns
        assert "mrn" in result.columns
        assert "amount_collected" in result.columns
        assert "sale_order_no" in result.columns

    def test_collection_date_range(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT MIN(date) as min_date, MAX(date) as max_date FROM dk.collection"
        )
        assert result.iloc[0]["min_date"] is not None
        assert result.iloc[0]["max_date"] is not None

    def test_collection_has_branches(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT DISTINCT branch FROM dk.collection WHERE branch IS NOT NULL"
        )
        assert len(result) > 0


class TestCollectionReportData:
    def test_collection_report_count(self, db: DatabaseManager):
        result = db.execute_query("SELECT COUNT(*) as cnt FROM dk.collection_report")
        assert result.iloc[0]["cnt"] > 0

    def test_collection_report_columns(self, db: DatabaseManager):
        result = db.execute_query("SELECT * FROM dk.collection_report LIMIT 1")
        assert "id" in result.columns
        assert "csv_date" in result.columns
        assert "branch" in result.columns
        assert "mrn" in result.columns


class TestMaterializedViewRefresh:
    def test_refresh_single_view(self, db: DatabaseManager):
        db.refresh_materialized_view("mvw_patient_enriched")
        result = db.execute_query("SELECT COUNT(*) as cnt FROM dk.mvw_patient_enriched")
        assert result.iloc[0]["cnt"] > 0

    def test_refresh_all_views(self, db: DatabaseManager):
        result = db.refresh_all_materialized_views()
        assert isinstance(result, pd.DataFrame)
        assert "mvw_name" in result.columns
        assert "status" in result.columns
        assert len(result) > 0


class TestUtilityMethods:
    def test_get_table_info(self, db: DatabaseManager):
        result = db.get_table_info("patient")
        assert isinstance(result, pd.DataFrame)
        assert "column_name" in result.columns
        assert "data_type" in result.columns
        assert len(result) > 0

    def test_get_view_sample(self, db: DatabaseManager):
        result = db.get_view_sample("mvw_patient_enriched", limit=5)
        assert isinstance(result, pd.DataFrame)
        assert len(result) <= 5

    def test_get_view_sample_with_where(self, db: DatabaseManager):
        result = db.get_view_sample(
            "mvw_patient_enriched", limit=5, where_clause="mrn IS NOT NULL"
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result) <= 5


class TestRFMData:
    def test_rfm_has_scores(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT r_score, f_score, m_score FROM dk.mvw_patient_rfm WHERE r_score IS NOT NULL LIMIT 5"
        )
        assert len(result) > 0
        assert all(col in result.columns for col in ["r_score", "f_score", "m_score"])

    def test_rfm_scores_in_range(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT MIN(r_score) as min_r, MAX(r_score) as max_r FROM dk.mvw_patient_rfm"
        )
        assert result.iloc[0]["min_r"] >= 1
        assert result.iloc[0]["max_r"] <= 5

    def test_rfm_segments(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT DISTINCT rfm_segment FROM dk.mvw_patient_rfm WHERE rfm_segment IS NOT NULL"
        )
        assert len(result) > 0


class TestBranchPerformance:
    def test_branch_count(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM dk.mvw_branch_performance"
        )
        assert result.iloc[0]["cnt"] > 0

    def test_branch_has_revenue(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT branch, net_revenue FROM dk.mvw_branch_performance WHERE net_revenue > 0 LIMIT 5"
        )
        assert len(result) > 0


class TestCalendarEffects:
    def test_calendar_effects_count(self, db: DatabaseManager):
        result = db.execute_query("SELECT COUNT(*) as cnt FROM dk.mvw_calendar_effects")
        assert result.iloc[0]["cnt"] > 0

    def test_malaysian_holidays_table(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'dk' AND table_name = 'malaysian_holidays'"
        )
        assert len(result) == 1


class TestConvenienceFunctions:
    def test_get_db_manager_singleton(self):
        m1 = get_db_manager()
        m2 = get_db_manager()
        assert m1 is m2
        m1.close()

    def test_execute_query_function(self):
        result = execute_query("SELECT 1 as test")
        assert isinstance(result, pd.DataFrame)
        assert result.iloc[0]["test"] == 1

    def test_get_db_connection_string(self):
        conn_str = get_db_connection_string()
        assert "postgresql://" in conn_str


class TestFunctions:
    def test_refresh_function_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT proname FROM pg_proc WHERE proname = 'refresh_all_mvws'"
        )
        assert len(result) == 1

    def test_check_data_quality_function_exists(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT proname FROM pg_proc WHERE proname = 'check_data_quality'"
        )
        assert len(result) == 1


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
