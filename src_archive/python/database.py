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
        conn = self.engine.begin()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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

    def refresh_materialized_view(self, view_name: str) -> None:
        sql = f"REFRESH MATERIALIZED VIEW CONCURRENTLY dk.{view_name}"
        self.execute_query(sql, return_df=False)


def get_db_manager() -> DatabaseManager:
    return DatabaseManager.get_instance()
