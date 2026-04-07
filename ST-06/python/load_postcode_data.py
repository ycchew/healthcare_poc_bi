"""
Malaysia Postcode Reference Data Loader
Downloads postcode data from public GitHub source and populates dk.my_postcode_ref table.

Usage:
    python ST-06/python/load_postcode_data.py
"""

import os
import sys
import logging

import pandas as pd
import psycopg2
import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def get_db_connection():
    """Create database connection using environment variables."""
    # Required - no defaults for sensitive credentials
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        raise ValueError("DB_PASSWORD environment variable is required")

    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=db_password,
    )


def get_postcode_data(url: str) -> pd.DataFrame:
    logger.info(f"Downloading postcode data from: {url}")

    response = requests.get(url, timeout=120)
    response.raise_for_status()

    from io import BytesIO
    import zipfile

    if url.endswith(".zip"):
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                # GeoNames allCountries.zip is tab-separated, no header
                df = pd.read_csv(
                    f,
                    sep="\t",
                    header=None,
                    dtype=str,
                    comment="#",
                )
        df.columns = [
            "country_code",
            "postcode",
            "place_name",
            "state",
            "state_code",
            "admin_name2",
            "admin_code2",
            "admin_name3",
            "admin_code3",
            "lat",
            "lng",
            "accuracy",
        ]
        # Filter for Malaysia only
        df = df[df["country_code"] == "MY"].copy()
        logger.info(f"Filtered to {len(df)} Malaysia records")
    else:
        from io import StringIO

        df = pd.read_csv(StringIO(response.text))

    logger.info(f"Downloaded {len(df)} records")
    return df


def validate_coordinates(lat: float, lng: float) -> bool:
    """Validate coordinate ranges for Malaysia (lat: 1-7, lng: 99-120)."""
    if pd.isna(lat) or pd.isna(lng):
        return False
    if not (1 <= lat <= 7):
        return False
    if not (99 <= lng <= 120):
        return False
    return True


def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Transforming postcode data...")

    df.columns = df.columns.str.strip().str.lower()

    column_mapping = {
        "place_name": "city",
        "admin_name1": "state",
        "postal_code": "postcode",
        "latitude": "lat",
        "longitude": "lng",
    }

    for old_col, new_col in column_mapping.items():
        if old_col in df.columns:
            df.rename(columns={old_col: new_col}, inplace=True)

    required_cols = ["postcode", "state", "city", "lat", "lng"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Convert postcode to string
    df["postcode"] = df["postcode"].astype(str).str.strip()

    # Convert lat/lng to numeric
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"] = pd.to_numeric(df["lng"], errors="coerce")

    # Strip whitespace from string columns
    df["state"] = df["state"].astype(str).str.strip()
    df["city"] = df["city"].astype(str).str.strip()

    # Replace 'nan' strings with actual NaN
    df["state"] = df["state"].replace("nan", None)
    df["city"] = df["city"].replace("nan", None)

    # Filter out NULL/invalid records
    initial_count = len(df)
    df = df.dropna(subset=["postcode", "lat", "lng"])
    df = df[df["postcode"].str.len() > 0]

    # Validate coordinates
    df = df[df.apply(lambda row: validate_coordinates(row["lat"], row["lng"]), axis=1)]

    final_count = len(df)
    logger.info(
        f"Filtered {initial_count - final_count} invalid records, {final_count} valid records remain"
    )

    # Remove duplicates (keep first)
    df = df.drop_duplicates(subset=["postcode"], keep="first")
    logger.info(f"After dedup: {len(df)} unique postcodes")

    return df


def load_to_database(df: pd.DataFrame) -> int:
    """Load transformed data into dk.my_postcode_ref table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("TRUNCATE TABLE dk.my_postcode_ref RESTART IDENTITY CASCADE")
    logger.info("Cleared existing postcode data")

    # Insert records
    insert_sql = """
        INSERT INTO dk.my_postcode_ref (postcode, state, city, lat, lng)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (postcode) DO NOTHING
    """

    records_inserted = 0
    for _, row in df.iterrows():
        try:
            cursor.execute(
                insert_sql,
                (
                    row["postcode"],
                    row["state"]
                    if pd.notna(row["state"]) and row["state"] != "None"
                    else None,
                    row["city"]
                    if pd.notna(row["city"]) and row["city"] != "None"
                    else None,
                    row["lat"],
                    row["lng"],
                ),
            )
            records_inserted += 1
        except Exception as e:
            logger.warning(f"Failed to insert postcode {row['postcode']}: {e}")

    conn.commit()
    cursor.close()
    conn.close()

    logger.info(f"Inserted {records_inserted} records into dk.my_postcode_ref")
    return records_inserted


def verify_data() -> dict:
    """Verify loaded data."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get count
    cursor.execute("SELECT COUNT(*) FROM dk.my_postcode_ref")
    count = cursor.fetchone()[0]

    # Get coordinate range
    cursor.execute("""
        SELECT MIN(lat), MAX(lat), MIN(lng), MAX(lng)
        FROM dk.my_postcode_ref
    """)
    lat_min, lat_max, lng_min, lng_max = cursor.fetchone()

    # Get unique states
    cursor.execute("SELECT COUNT(DISTINCT state) FROM dk.my_postcode_ref")
    state_count = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return {
        "total_records": count,
        "lat_range": (lat_min, lat_max),
        "lng_range": (lng_min, lng_max),
        "unique_states": state_count,
    }


def main():
    """Main entry point."""
    logger.info("Starting Malaysia postcode data loader...")

    # Get download URL from environment variable
    postcode_url = os.getenv("MALAYSIA_POSTCODE_URL")
    if not postcode_url:
        postcode_url = "https://download.geonames.org/export/zip/allCountries.zip"
        logger.info(f"Using fallback URL: {postcode_url}")

    try:
        # Download data
        df = get_postcode_data(postcode_url)

        # Transform data
        df = transform_data(df)

        # Load to database
        records_loaded = load_to_database(df)

        # Verify
        stats = verify_data()
        logger.info(f"Verification: {stats['total_records']} records loaded")
        logger.info(f"  Lat range: {stats['lat_range']}")
        logger.info(f"  Lng range: {stats['lng_range']}")
        logger.info(f"  Unique states: {stats['unique_states']}")

        if stats["total_records"] >= 2700:
            logger.info("SUCCESS: Loaded approximately 2,800 records")
            return 0
        else:
            logger.warning(
                f"WARNING: Expected ~2800 records, got {stats['total_records']}"
            )
            return 1

    except Exception as e:
        logger.error(f"Failed to load postcode data: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
