"""
ST-01: Data Foundation & Infrastructure
Database Connection Module
"""

import os
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any, Union

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Load environment variables
load_dotenv()


def get_db_connection_string() -> str:
    """Build PostgreSQL connection string from environment variables."""
    return (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )


def get_engine() -> Engine:
    """Create SQLAlchemy engine with connection pooling."""
    return create_engine(
        get_db_connection_string(),
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


@contextmanager
def get_connection() -> Generator:
    """Context manager for database connections."""
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()
        engine.dispose()


@contextmanager
def get_transaction() -> Generator:
    """Context manager for database transactions."""
    engine = get_engine()
    conn = engine.begin()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        engine.dispose()


def execute_query(query: str, params: Optional[dict] = None) -> pd.DataFrame:
    """Execute SQL query and return DataFrame."""
    with get_connection() as conn:
        return pd.read_sql(text(query), conn, params=params)


def execute_sql(sql: str, params: Optional[dict] = None) -> None:
    """Execute SQL statement (INSERT, UPDATE, DELETE)."""
    with get_transaction() as conn:
        conn.execute(text(sql), params or {})


def refresh_materialized_view(view_name: str) -> None:
    """Refresh a specific materialized view."""
    sql = f"REFRESH MATERIALIZED VIEW CONCURRENTLY dk.{view_name}"
    execute_sql(sql)


def check_data_quality() -> pd.DataFrame:
    """Run data quality checks and return results."""
    return execute_query("SELECT * FROM dk.check_data_quality()")


def get_table_stats(table_name: str) -> pd.DataFrame:
    """Get statistics for a table or view."""
    query = f"""
    SELECT 
        schemaname,
        tablename,
        n_tup_ins,
        n_tup_upd,
        n_live_tup,
        n_dead_tup,
        last_vacuum,
        last_autovacuum,
        last_analyze,
        last_autoanalyze
    FROM pg_stat_user_tables
    WHERE schemaname = 'dk' AND tablename = '{table_name}'
    """
    return execute_query(query)


class DatabaseManager:
    """
    Database manager class for connection pooling and query execution.
    Provides a unified interface for database operations.
    """

    _instance: Optional["DatabaseManager"] = None

    def __init__(self, connection_string: Optional[str] = None):
        self._engine: Optional[Engine] = None
        self._connection_string = connection_string or get_db_connection_string()

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def connection_string(self) -> str:
        return self._connection_string

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(
                self._connection_string,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
        return self._engine

    @contextmanager
    def get_connection(self) -> Generator:
        conn = self.engine.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def get_transaction(self) -> Generator:
        with self.engine.begin() as conn:
            try:
                yield conn
            except Exception:
                raise

    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        return_df: bool = True,
    ) -> Union[pd.DataFrame, None]:
        if return_df:
            with self.get_connection() as conn:
                return pd.read_sql(text(query), conn, params=params)
        else:
            with self.get_transaction() as conn:
                conn.execute(text(query), params or {})

    def execute_query_raw(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        with self.get_connection() as conn:
            return conn.execute(text(query), params or {})

    def execute_sql_file(self, file_path: str) -> None:
        with open(file_path, "r", encoding="utf-8") as f:
            sql = f.read()
        self.execute_query(sql, return_df=False)

    def refresh_materialized_view(self, view_name: str) -> None:
        sql = f"REFRESH MATERIALIZED VIEW CONCURRENTLY dk.{view_name}"
        try:
            with self.get_transaction() as conn:
                conn.execute(text(sql))
        except Exception:
            sql = f"REFRESH MATERIALIZED VIEW dk.{view_name}"
            with self.get_transaction() as conn:
                conn.execute(text(sql))

    def refresh_all_materialized_views(self) -> pd.DataFrame:
        views = [
            "mvw_patient_enriched",
            "mvw_transaction_flat",
            "mvw_patient_transactions",
            "mvw_patient_rfm",
            "mvw_patient_ltv",
            "mvw_calendar_effects",
            "mvw_branch_performance",
            "mvw_product_performance",
            "mvw_d3_followup_list",
        ]
        results = []
        for view_name in views:
            try:
                start_time = pd.Timestamp.now()
                self.refresh_materialized_view(view_name)
                duration_ms = (pd.Timestamp.now() - start_time).total_seconds() * 1000
                results.append(
                    {
                        "mvw_name": view_name,
                        "status": "SUCCESS",
                        "duration_ms": duration_ms,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "mvw_name": view_name,
                        "status": f"FAILED: {str(e)}",
                        "duration_ms": 0.0,
                    }
                )
        return pd.DataFrame(results)

    def get_table_info(self, table_name: str) -> pd.DataFrame:
        query = f"""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'dk' AND table_name = '{table_name}'
        ORDER BY ordinal_position
        """
        return self.execute_query(query)

    def get_view_sample(
        self, view_name: str, limit: int = 10, where_clause: Optional[str] = None
    ) -> pd.DataFrame:
        where = f" WHERE {where_clause}" if where_clause else ""
        query = f"SELECT * FROM dk.{view_name}{where} LIMIT {limit}"
        return self.execute_query(query)

    def check_data_quality(self) -> Dict[str, Any]:
        try:
            patient_count = self.execute_query(
                "SELECT COUNT(*) as cnt FROM dk.patient"
            ).iloc[0]["cnt"]
            collection_count = self.execute_query(
                "SELECT COUNT(*) as cnt FROM dk.collection"
            ).iloc[0]["cnt"]
            report_count = self.execute_query(
                "SELECT COUNT(*) as cnt FROM dk.collection_report"
            ).iloc[0]["cnt"]
            date_range = self.execute_query(
                "SELECT MIN(date) as min_date, MAX(date) as max_date FROM dk.collection"
            ).iloc[0]

            return {
                "status": "OK",
                "patient_row_count": int(patient_count),
                "collection_row_count": int(collection_count),
                "collection_report_row_count": int(report_count),
                "transaction_date_range": f"{date_range['min_date']} to {date_range['max_date']}",
                "timestamp": pd.Timestamp.now().isoformat(),
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "timestamp": pd.Timestamp.now().isoformat(),
            }

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


def get_db_manager() -> DatabaseManager:
    return DatabaseManager.get_instance()
