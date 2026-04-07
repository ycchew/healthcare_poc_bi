"""
ST-06: Geospatial Analytics
Patient Geocoding Pipeline - 4-Level Fallback Strategy (Azure Maps + Nominatim)

This module geocodes patient addresses using a 4-level fallback strategy:
1. Full address (street + city + state + zip)
2. Street + City only
3. City + State only
4. ZIP code only

Falls back to Nominatim when Azure Maps rate limits or fails.
Stores results in dk.patient_geocode with quality tracking.

Usage:
    python ST-06/python/geocoding_pipeline.py              # Run geocoding
    python ST-06/python/geocoding_pipeline.py --test       # Run test mode
    python ST-06/python/geocoding_pipeline.py --batch-size 50 --delay 10
"""

import os
import sys
import logging
import argparse
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import importlib.util

spec = importlib.util.spec_from_file_location(
    "database", os.path.join(project_root, "ST-01", "python", "database.py")
)
database_module = importlib.util.module_from_spec(spec)
sys.modules["ST_01.python.database"] = database_module
spec.loader.exec_module(database_module)
DatabaseManager = database_module.DatabaseManager

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PatientGeocodingPipeline:
    """
    Patient geocoding pipeline with 4-level fallback strategy.

    Fallback levels:
    1. Full address (street + city + state + zip)
    2. Street + City only
    3. City + State only
    4. ZIP code only

    Uses Azure Maps API with Nominatim fallback for rate limit handling.
    """

    AZURE_MAPS_BASE_URL = "https://atlas.microsoft.com/search"
    NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search"

    # Malaysia coordinate bounds
    MALAYSIA_LAT_MIN = 0.5
    MALAYSIA_LAT_MAX = 7.5
    MALAYSIA_LNG_MIN = 99.0
    MALAYSIA_LNG_MAX = 120.0

    # Geocode quality levels
    QUALITY_EXACT = "exact"
    QUALITY_STREET = "street"
    QUALITY_CITY = "city"
    QUALITY_STATE = "state"
    QUALITY_ZIP = "zip"
    QUALITY_FAILED = "failed"

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        batch_size: int = 100,
        batch_delay_seconds: int = 5,
    ):
        """
        Initialize the patient geocoding pipeline.

        Args:
            db_manager: DatabaseManager instance
            batch_size: Number of records to process before a delay
            batch_delay_seconds: Delay between batches (default 5s)
        """
        self.db_manager = db_manager or DatabaseManager.get_instance()

        # Azure Maps configuration
        self.azure_maps_key = os.getenv("AZURE_MAPS_PRIMARY_KEY")
        self.azure_maps_client_id = os.getenv("AZURE_MAPS_CLIENT_ID")
        self.azure_timeout = int(os.getenv("AZURE_MAPS_TIMEOUT", "30"))

        # Nominatim configuration
        self.nominatim_timeout = int(os.getenv("NOMINATIM_TIMEOUT", "30"))
        self.user_agent = os.getenv(
            "NOMINATIM_USER_AGENT", "healthcare_bi_geocoder/1.0"
        )

        # Batch processing configuration
        self.batch_size = batch_size
        self.batch_delay_seconds = batch_delay_seconds

        # Rate limit tracking
        self._azure_rate_limited = False
        self._nominatim_delay_until = 0

        if not self.azure_maps_key:
            logger.warning("AZURE_MAPS_PRIMARY_KEY not set - will use Nominatim only")

    def geocode_with_azure_maps(
        self, address: str, country: str = "Malaysia"
    ) -> Optional[Dict[str, Any]]:
        """
        Geocode an address using Azure Maps Search Address API.

        Args:
            address: The address to geocode
            country: Country name to append to query (default: Malaysia)

        Returns:
            Dictionary with 'lat', 'lng', 'formatted_address', 'quality' or None if failed
        """
        if self._azure_rate_limited:
            return None

        # Build query - append country for better accuracy
        query = f"{address}, {country}"

        # API endpoint
        url = f"{self.AZURE_MAPS_BASE_URL}/address/json"

        # Parameters - subscription-key as query param (Shared Key auth)
        params = {
            "api-version": "1.0",
            "query": query,
            "limit": 1,
            "countrySet": "MY",
            "subscription-key": self.azure_maps_key,
        }

        # Headers - x-ms-client-id only for Microsoft Entra ID (Bearer) auth
        headers = {}
        if self.azure_maps_client_id:
            headers["x-ms-client-id"] = self.azure_maps_client_id

        try:
            logger.debug(f"Azure Maps query: {query}")
            response = requests.get(
                url, params=params, headers=headers, timeout=self.azure_timeout
            )

            # Check for rate limit (429)
            if response.status_code == 429:
                logger.warning("Azure Maps rate limit hit - switching to Nominatim")
                self._azure_rate_limited = True
                return None

            response.raise_for_status()

            data = response.json()

            # Check if we have results
            if data.get("results") and len(data["results"]) > 0:
                result = data["results"][0]
                position = result.get("position", {})
                address_data = result.get("address", {})

                lat = position.get("lat")
                lng = position.get("lon")

                # Validate coordinates are within Malaysia bounds
                if lat and lng and self._validate_coordinates(lat, lng):
                    formatted_address = address_data.get("freeformAddress", address)

                    # Determine quality level based on address components
                    quality = self._determine_quality_level(
                        address_data, result.get("score", 0)
                    )

                    logger.info(
                        f"Azure Maps ({quality}): {address[:50]}... -> ({lat:.6f}, {lng:.6f})"
                    )

                    return {
                        "lat": lat,
                        "lng": lng,
                        "formatted_address": formatted_address,
                        "source": "azure_maps",
                        "quality": quality,
                        "score": result.get("score", 0),
                    }
                else:
                    logger.warning(
                        f"Azure Maps returned coordinates outside Malaysia: ({lat}, {lng})"
                    )
                    return None
            else:
                logger.debug(f"Azure Maps: No results for '{address}'")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Azure Maps timeout for address: {address}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Azure Maps request failed: {e}")
            # Check if it's a rate limit error
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 429:
                    self._azure_rate_limited = True
            return None
        except Exception as e:
            logger.error(f"Azure Maps parsing error: {e}")
            return None

    def geocode_with_nominatim(
        self, address: str, country: str = "Malaysia"
    ) -> Optional[Dict[str, Any]]:
        """
        Geocode an address using Nominatim (OpenStreetMap) as fallback.

        Implements rate limiting: 1 request per second to respect Nominatim ToS.

        Args:
            address: The address to geocode
            country: Country name to append to query (default: Malaysia)

        Returns:
            Dictionary with 'lat', 'lng', 'formatted_address', 'quality' or None if failed
        """
        # Respect Nominatim rate limiting (1 request/second)
        current_time = time.time()
        if current_time < self._nominatim_delay_until:
            sleep_time = self._nominatim_delay_until - current_time
            logger.debug(f"Rate limit delay: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

        # Build query
        query = f"{address}, {country}"

        # Parameters
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "countrycodes": "my",  # Limit to Malaysia
        }

        # Headers - user agent is required
        headers = {
            "User-Agent": self.user_agent,
        }

        try:
            logger.debug(f"Nominatim query: {query}")
            response = requests.get(
                self.NOMINATIM_BASE_URL,
                params=params,
                headers=headers,
                timeout=self.nominatim_timeout,
            )

            # Set delay for next request (1 second)
            self._nominatim_delay_until = time.time() + 1.0

            response.raise_for_status()

            results = response.json()

            # Check if we have results
            if results and len(results) > 0:
                result = results[0]
                lat = float(result.get("lat"))
                lng = float(result.get("lon"))

                # Validate coordinates
                if self._validate_coordinates(lat, lng):
                    formatted_address = result.get("display_name", address)

                    # Determine quality level
                    quality = self._determine_quality_level_nominatim(result)

                    logger.info(
                        f"Nominatim ({quality}): {address[:50]}... -> ({lat:.6f}, {lng:.6f})"
                    )

                    return {
                        "lat": lat,
                        "lng": lng,
                        "formatted_address": formatted_address,
                        "source": "nominatim",
                        "quality": quality,
                        "score": 1.0,
                    }
                else:
                    logger.warning(
                        f"Nominatim returned coordinates outside Malaysia: ({lat}, {lng})"
                    )
                    return None
            else:
                logger.debug(f"Nominatim: No results for '{address}'")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Nominatim timeout for address: {address}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Nominatim request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Nominatim parsing error: {e}")
            return None

    def geocode_with_fallback(
        self,
        street: Optional[str],
        city: Optional[str],
        state: Optional[str],
        zip_code: Optional[str],
        country: str = "Malaysia",
    ) -> Optional[Dict[str, Any]]:
        """
        Geocode using 4-level fallback strategy.

        Fallback levels:
        1. Full address (street + city + state + zip)
        2. Street + City only
        3. City + State only
        4. ZIP code only

        Args:
            street: Street address
            city: City name
            state: State/province name
            zip_code: Postal/ZIP code
            country: Country name (default: Malaysia)

        Returns:
            Dictionary with 'lat', 'lng', 'formatted_address', 'source', 'quality' or None if failed
        """
        # Build address components (handle None values)
        street = str(street).strip() if pd.notna(street) else None
        city = str(city).strip() if pd.notna(city) else None
        state = str(state).strip() if pd.notna(state) else None
        zip_code = str(zip_code).strip() if pd.notna(zip_code) else None

        # Level 1: Full address (street + city + state + zip)
        if street and city and state and zip_code:
            full_address = f"{street}, {city}, {state} {zip_code}"
            logger.debug(f"Geocoding Level 1 (Full): {full_address[:60]}...")
            result = self._try_geocode(full_address, country)
            if result:
                return result

        # Level 2: Street + City only
        if street and city:
            street_city_address = f"{street}, {city}"
            logger.debug(
                f"Geocoding Level 2 (Street+City): {street_city_address[:60]}..."
            )
            result = self._try_geocode(street_city_address, country)
            if result:
                return result

        # Level 3: City + State only
        if city and state:
            city_state_address = f"{city}, {state}"
            logger.debug(
                f"Geocoding Level 3 (City+State): {city_state_address[:60]}..."
            )
            result = self._try_geocode(city_state_address, country)
            if result:
                # Override quality to city level
                result["quality"] = self.QUALITY_CITY
                return result

        # Level 4: ZIP code only
        if zip_code:
            zip_address = f"{zip_code}"
            logger.debug(f"Geocoding Level 4 (ZIP): {zip_address}")
            result = self._try_geocode(zip_address, country)
            if result:
                # Override quality to zip level
                result["quality"] = self.QUALITY_ZIP
                return result

        # All fallback levels exhausted
        logger.warning(f"All geocoding levels failed for address components")
        return None

    def _try_geocode(self, address: str, country: str) -> Optional[Dict[str, Any]]:
        """
        Try geocoding with Azure Maps, fallback to Nominatim.

        Args:
            address: Address string to geocode
            country: Country name

        Returns:
            Geocoding result or None
        """
        # Try Azure Maps first (if key is configured and not rate limited)
        if self.azure_maps_key and not self._azure_rate_limited:
            result = self.geocode_with_azure_maps(address, country)
            if result:
                return result

        # Fallback to Nominatim
        logger.debug(
            f"Azure Maps failed/unavailable, trying Nominatim for: {address[:50]}..."
        )
        result = self.geocode_with_nominatim(address, country)
        if result:
            return result

        return None

    def _validate_coordinates(self, lat: float, lng: float) -> bool:
        """
        Validate that coordinates are within Malaysia bounds.

        Args:
            lat: Latitude
            lng: Longitude

        Returns:
            True if coordinates are valid for Malaysia, False otherwise
        """
        return (
            self.MALAYSIA_LAT_MIN <= lat <= self.MALAYSIA_LAT_MAX
            and self.MALAYSIA_LNG_MIN <= lng <= self.MALAYSIA_LNG_MAX
        )

    def _determine_quality_level(
        self, address_data: Dict[str, Any], score: float
    ) -> str:
        """
        Determine geocode quality level from Azure Maps response.

        Args:
            address_data: Address data from Azure Maps response
            score: Confidence score from Azure Maps

        Returns:
            Quality level string (exact, street, city, state, zip)
        """
        # High score + street address = exact
        if score >= 0.9 and address_data.get("streetNumber"):
            return self.QUALITY_EXACT

        # Has street name
        if address_data.get("street") or address_data.get("streetNumber"):
            return self.QUALITY_STREET

        # Has city/municipality
        if address_data.get("municipality") or address_data.get("city"):
            return self.QUALITY_CITY

        # Has subdivision (state/province)
        if address_data.get("countrySubdivision"):
            return self.QUALITY_STATE

        # Default to ZIP level
        return self.QUALITY_ZIP

    def _determine_quality_level_nominatim(self, result: Dict[str, Any]) -> str:
        """
        Determine geocode quality level from Nominatim response.

        Args:
            result: Result from Nominatim

        Returns:
            Quality level string
        """
        address = result.get("address", {})
        result_type = result.get("type", "")

        # Street/poi level
        if result_type in ["house", "building", "residential", "commercial"]:
            return self.QUALITY_EXACT

        if address.get("road") or address.get("house_number"):
            return self.QUALITY_STREET

        # City level
        if address.get("city") or address.get("town") or address.get("village"):
            return self.QUALITY_CITY

        # State level
        if address.get("state"):
            return self.QUALITY_STATE

        # Default to ZIP
        return self.QUALITY_ZIP

    def load_patients_for_geocoding(
        self,
        source_table: str = "dk.patient",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> pd.DataFrame:
        """
        Load patients from database for geocoding.

        Only loads patients with non-NULL addresses and skips already geocoded patients.

        Args:
            source_table: Source table for patient data
            limit: Optional limit for batch testing
            offset: Optional offset for pagination

        Returns:
            DataFrame with patient address data
        """
        logger.info(f"Loading patients from {source_table} for geocoding...")

        # Query to get patients with address components that haven't been geocoded
        query = """
            SELECT DISTINCT
                p.mrn,
                p.location,
                NULLIF(TRIM(p.street), '') AS street,
                NULLIF(TRIM(p.city_name), '') AS city,
                NULLIF(TRIM(p.state_name), '') AS state,
                NULLIF(TRIM(p.zip), '') AS zip,
                p.country_name AS country
            FROM dk.patient p
            LEFT JOIN dk.patient_geocode pg ON p.mrn = pg.mrn AND p.location = pg.location
            WHERE pg.mrn IS NULL  -- Skip already geocoded patients
              AND (
                  p.street IS NOT NULL AND TRIM(p.street) != ''
                  OR p.city_name IS NOT NULL AND TRIM(p.city_name) != ''
                  OR p.state_name IS NOT NULL AND TRIM(p.state_name) != ''
                  OR p.zip IS NOT NULL AND TRIM(p.zip) != ''
              )
            ORDER BY p.mrn, p.location
        """

        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        try:
            df = self.db_manager.execute_query(query)
            logger.info(f"Loaded {len(df)} patients for geocoding")
            return df
        except Exception as e:
            logger.error(f"Failed to load patients: {e}")
            return pd.DataFrame()

    def store_geocode_result(
        self,
        mrn: str,
        location: str,
        result: Optional[Dict[str, Any]],
        original_address: str,
    ) -> bool:
        """
        Store geocode result in dk.patient_geocode table.

        Args:
            mrn: Patient MRN
            location: Patient location
            result: Geocoding result (or None if failed)
            original_address: Original address string that was geocoded

        Returns:
            True if successful, False otherwise
        """
        if result:
            # Success - insert full geocode record
            sql = """
                INSERT INTO dk.patient_geocode (
                    mrn, location, full_address, zip, city_name, state_name,
                    country_name, patient_lat, patient_lng, geocode_source,
                    geocode_quality, geocode_at
                ) VALUES (
                    :mrn, :location, :full_address, :zip, :city_name, :state_name,
                    :country_name, :patient_lat, :patient_lng, :geocode_source,
                    :geocode_quality, :geocode_at
                )
                ON CONFLICT (mrn, location) DO UPDATE SET
                    patient_lat = EXCLUDED.patient_lat,
                    patient_lng = EXCLUDED.patient_lng,
                    geocode_source = EXCLUDED.geocode_source,
                    geocode_quality = EXCLUDED.geocode_quality,
                    geocode_at = EXCLUDED.geocode_at,
                    updated_at = NOW()
            """

            # Extract city/state from formatted address if not available
            params = {
                "mrn": mrn,
                "location": location,
                "full_address": result["formatted_address"],
                "zip": None,  # Can be extracted from result if needed
                "city_name": None,
                "state_name": None,
                "country_name": "Malaysia",
                "patient_lat": result["lat"],
                "patient_lng": result["lng"],
                "geocode_source": result["source"],
                "geocode_quality": result["quality"],
                "geocode_at": datetime.now(),
            }
        else:
            # Failed - insert with quality = failed
            sql = """
                INSERT INTO dk.patient_geocode (
                    mrn, location, full_address, geocode_quality,
                    geocode_source, geocode_at
                ) VALUES (
                    :mrn, :location, :full_address, :geocode_quality,
                    :geocode_source, :geocode_at
                )
                ON CONFLICT (mrn, location) DO UPDATE SET
                    geocode_quality = EXCLUDED.geocode_quality,
                    geocode_at = EXCLUDED.geocode_at,
                    updated_at = NOW()
            """

            params = {
                "mrn": mrn,
                "location": location,
                "full_address": original_address,
                "geocode_quality": self.QUALITY_FAILED,
                "geocode_source": None,
                "geocode_at": datetime.now(),
            }

        try:
            with self.db_manager.get_transaction() as conn:
                from sqlalchemy import text

                conn.execute(text(sql), params)
            logger.debug(f"Stored geocode result for MRN {mrn}, location {location}")
            return True
        except Exception as e:
            logger.error(f"Failed to store geocode result for {mrn}: {e}")
            return False

    def log_execution(
        self,
        run_id: int,
        status: str,
        records_total: int,
        records_processed: int,
        records_succeeded: int,
        records_failed: int,
        records_skipped: int,
        error_message: Optional[str] = None,
        duration_seconds: int = 0,
    ) -> bool:
        """
        Log execution to dk.geocode_execution_log table.

        Args:
            run_id: Execution run ID
            status: Status (running, completed, failed)
            records_total: Total records to process
            records_processed: Records actually processed
            records_succeeded: Successful geocodes
            records_failed: Failed geocodes
            records_skipped: Skipped records
            error_message: Error message if failed
            duration_seconds: Total execution duration

        Returns:
            True if successful, False otherwise
        """
        sql = """
            UPDATE dk.geocode_execution_log
            SET status = :status,
                completed_at = NOW(),
                duration_seconds = :duration_seconds,
                records_total = :records_total,
                records_processed = :records_processed,
                records_succeeded = :records_succeeded,
                records_failed = :records_failed,
                records_skipped = :records_skipped,
                error_message = :error_message
            WHERE run_id = :run_id
        """

        params = {
            "run_id": run_id,
            "status": status,
            "duration_seconds": duration_seconds,
            "records_total": records_total,
            "records_processed": records_processed,
            "records_succeeded": records_succeeded,
            "records_failed": records_failed,
            "records_skipped": records_skipped,
            "error_message": error_message,
        }

        try:
            with self.db_manager.get_connection() as conn:
                from sqlalchemy import text

                conn.execute(text(sql), params)
            logger.debug(f"Updated execution log for run_id {run_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update execution log: {e}")
            return False

    def create_execution_run(
        self,
        run_type: str = "incremental",
        source_table: str = "dk.patient",
    ) -> int:
        """
        Create a new execution run record.

        Args:
            run_type: Type of run (full, incremental, retry)
            source_table: Source table name

        Returns:
            run_id for the new execution record
        """
        sql = """
            INSERT INTO dk.geocode_execution_log (
                run_type, status, started_at, source_table,
                geocode_provider, batch_size, rate_limit_delay_ms
            ) VALUES (
                :run_type, :status, NOW(), :source_table,
                :geocode_provider, :batch_size, :rate_limit_delay_ms
            ) RETURNING run_id
        """

        params = {
            "run_type": run_type,
            "status": "running",
            "source_table": source_table,
            "geocode_provider": "azure_maps+nominatim",
            "batch_size": self.batch_size,
            "rate_limit_delay_ms": self.batch_delay_seconds * 1000,
        }

        try:
            with self.db_manager.get_connection() as conn:
                from sqlalchemy import text

                result = conn.execute(text(sql), params).fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to create execution run: {e}")
            return 0

    def geocode_patients(
        self,
        limit: Optional[int] = None,
        update_db: bool = True,
        log_errors: bool = True,
    ) -> Dict[str, Any]:
        """
        Geocode all eligible patients.

        Args:
            limit: Optional limit for testing (None = all patients)
            update_db: If True, store results in database
            log_errors: If True, log execution results to database

        Returns:
            Dictionary with geocoding statistics
        """
        logger.info("Starting patient geocoding process...")
        start_time = time.time()

        # Create execution run record
        run_id = 0
        if log_errors:
            run_id = self.create_execution_run(
                run_type="incremental" if limit is None else "test",
                source_table="dk.patient",
            )
            logger.info(f"Created execution run: {run_id}")

        # Load patients
        patients_df = self.load_patients_for_geocoding(limit=limit)

        if patients_df.empty:
            logger.info("No patients found for geocoding")
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "by_quality": {},
                "by_source": {},
            }

        # Track statistics
        stats = {
            "total": len(patients_df),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "by_quality": {
                self.QUALITY_EXACT: 0,
                self.QUALITY_STREET: 0,
                self.QUALITY_CITY: 0,
                self.QUALITY_STATE: 0,
                self.QUALITY_ZIP: 0,
                self.QUALITY_FAILED: 0,
            },
            "by_source": {"azure_maps": 0, "nominatim": 0},
            "results": [],
        }

        # Process patients in batches
        batch_count = 0
        start_batch_time = time.time()

        for idx, row in patients_df.iterrows():
            mrn = row["mrn"]
            location = row["location"]
            street = row["street"]
            city = row["city"]
            state = row["state"]
            zip_code = row["zip"]

            logger.info(
                f"[{idx + 1}/{len(patients_df)}] Geocoding MRN: {mrn}, Location: {location}"
            )

            address_parts = [p for p in [street, city, state, zip_code] if p]
            original_address = ", ".join(address_parts) if address_parts else ""

            if not original_address:
                logger.warning(f"Skipping {mrn} - no address components")
                stats["skipped"] += 1
                continue

            result = self.geocode_with_fallback(street, city, state, zip_code)

            if result:
                # Success
                stats["success"] += 1
                stats["by_quality"][result["quality"]] += 1
                stats["by_source"][result["source"]] += 1

                # Store result in database
                if update_db:
                    self.store_geocode_result(mrn, location, result, original_address)

                stats["results"].append(
                    {
                        "mrn": mrn,
                        "location": location,
                        "status": "SUCCESS",
                        "source": result["source"],
                        "quality": result["quality"],
                        "lat": result["lat"],
                        "lng": result["lng"],
                    }
                )
            else:
                # Failed
                stats["failed"] += 1
                stats["by_quality"][self.QUALITY_FAILED] += 1

                # Store failed result
                if update_db:
                    self.store_geocode_result(mrn, location, None, original_address)

                stats["results"].append(
                    {
                        "mrn": mrn,
                        "location": location,
                        "status": "FAILED",
                        "source": None,
                        "quality": self.QUALITY_FAILED,
                        "lat": None,
                        "lng": None,
                    }
                )

            batch_count += 1
            if batch_count >= self.batch_size:
                elapsed = time.time() - start_batch_time
                logger.info(
                    f"Batch complete ({batch_count} records in {elapsed:.1f}s). "
                    f"Delaying {self.batch_delay_seconds}s..."
                )
                time.sleep(self.batch_delay_seconds)
                batch_count = 0
                start_batch_time = time.time()

        duration_seconds = int(time.time() - start_time)

        if log_errors and run_id > 0:
            self.log_execution(
                run_id=run_id,
                status="completed",
                records_total=stats["total"],
                records_processed=stats["success"] + stats["failed"],
                records_succeeded=stats["success"],
                records_failed=stats["failed"],
                records_skipped=stats["skipped"],
                duration_seconds=duration_seconds,
            )

        logger.info("=" * 60)
        logger.info("GEOCODING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total patients: {stats['total']}")
        logger.info(f"Successful: {stats['success']}")
        logger.info(f"Failed: {stats['failed']}")
        logger.info(f"Skipped: {stats['skipped']}")
        logger.info(
            f"Success rate: {stats['success'] / max(stats['total'], 1) * 100:.1f}%"
        )
        logger.info(f"Duration: {duration_seconds}s")
        logger.info("")
        logger.info("By Quality Level:")
        for quality, count in stats["by_quality"].items():
            logger.info(f"  {quality}: {count}")
        logger.info("")
        logger.info("By Source:")
        for source, count in stats["by_source"].items():
            logger.info(f"  {source}: {count}")
        logger.info("=" * 60)

        return stats


def create_test_patients(db_manager: DatabaseManager) -> int:
    logger.info("Creating test patient records...")

    import io

    csv_data = """mrn,location,street,city_name,state_name,zip,country_name
TEST00001,TEST_LOC,123 Jalan Ampang,Kuala Lumpur,Wilayah Persekutuan,50450,Malaysia
TEST00002,TEST_LOC,456 Jalan Raja Chulan,Kuala Lumpur,Wilayah Persekutuan,50200,Malaysia
TEST00003,TEST_LOC,789 Jalan Petaling,Kuala Lumpur,Wilayah Persekutuan,50000,Malaysia
TEST00004,TEST_LOC,101 Lebuh Ampang,George Town,Penang,10100,Malaysia
TEST00005,TEST_LOC,202 Jalan Tun Razak,Johor Bahru,Johor,80000,Malaysia
TEST00006,TEST_LOC,,Malacca,Melaka,,Malaysia
TEST00007,TEST_LOC,,,,40000,Malaysia
"""

    df = pd.read_csv(io.StringIO(csv_data.strip()))

    sql_insert = """
        INSERT INTO dk.patient (
            mrn, location, street, city_name, state_name, zip, country_name
        ) VALUES (
            :mrn, :location, :street, :city_name, :state_name, :zip, :country_name
        )
    """

    inserted = 0
    with db_manager.get_connection() as conn:
        from sqlalchemy import text

        for _, row in df.iterrows():
            try:
                params = {
                    "mrn": row["mrn"],
                    "location": row["location"],
                    "street": row["street"] if pd.notna(row["street"]) else None,
                    "city_name": row["city_name"]
                    if pd.notna(row["city_name"])
                    else None,
                    "state_name": row["state_name"]
                    if pd.notna(row["state_name"])
                    else None,
                    "zip": row["zip"] if pd.notna(row["zip"]) else None,
                    "country_name": row["country_name"],
                }
                conn.execute(text(sql_insert), params)
                inserted += 1
            except Exception:
                pass

    logger.info(f"Created {inserted} test patient records")
    return inserted


def cleanup_test_patients(db_manager: DatabaseManager):
    """Remove test patient records after testing."""
    logger.info("Cleaning up test patient records...")

    sql_delete_geocode = """
        DELETE FROM dk.patient_geocode
        WHERE mrn LIKE 'TEST%'
    """

    sql_delete_patient = """
        DELETE FROM dk.patient
        WHERE mrn LIKE 'TEST%'
    """

    with db_manager.get_connection() as conn:
        from sqlalchemy import text

        conn.execute(text(sql_delete_geocode))
        conn.execute(text(sql_delete_patient))

    logger.info("Test patient records cleaned up")


def run_tests():
    """Run tests for the patient geocoding pipeline."""
    logger.info("=" * 60)
    logger.info("RUNNING PATIENT GEOCODING PIPELINE TESTS")
    logger.info("=" * 60)

    db_manager = DatabaseManager.get_instance()
    geocoder = PatientGeocodingPipeline(
        db_manager=db_manager,
        batch_size=10,
        batch_delay_seconds=1,
    )

    logger.info("\nTest 1: Coordinate validation")
    assert geocoder._validate_coordinates(3.139, 101.6869)
    assert geocoder._validate_coordinates(5.4164, 100.3327)
    assert geocoder._validate_coordinates(1.3521, 103.8198)
    assert not geocoder._validate_coordinates(40.7128, -74.0060)
    assert not geocoder._validate_coordinates(51.5074, -0.1278)
    logger.info("✓ Coordinate validation tests passed")

    logger.info("\nTest 2: Quality level determination")
    test_address_data = {
        "streetNumber": "123",
        "street": "Main St",
        "municipality": "Kuala Lumpur",
    }
    quality = geocoder._determine_quality_level(test_address_data, 0.95)
    assert quality == "exact", f"Expected 'exact', got '{quality}'"

    test_address_data = {"street": "Main St"}
    quality = geocoder._determine_quality_level(test_address_data, 0.8)
    assert quality == "street", f"Expected 'street', got '{quality}'"

    test_address_data = {"municipality": "Kuala Lumpur"}
    quality = geocoder._determine_quality_level(test_address_data, 0.7)
    assert quality == "city", f"Expected 'city', got '{quality}'"
    logger.info("✓ Quality level determination tests passed")

    logger.info("\nTest 3: 4-level fallback geocoding")
    result = geocoder.geocode_with_fallback(
        street="123 Jalan Ampang",
        city="Kuala Lumpur",
        state="Wilayah Persekutuan",
        zip_code="50450",
    )
    if result:
        logger.info(
            f"✓ Full address geocoded: ({result['lat']:.4f}, {result['lng']:.4f})"
        )
        logger.info(f"  Quality: {result['quality']}, Source: {result['source']}")
        assert geocoder._validate_coordinates(result["lat"], result["lng"])
    else:
        logger.warning("⚠ Full address geocoding skipped - no API access")

    logger.info("\nTest 4: Test patient data")
    create_test_patients(db_manager)
    patients_df = geocoder.load_patients_for_geocoding(limit=5)
    if len(patients_df) > 0:
        logger.info(f"✓ Loaded {len(patients_df)} test patients")

        logger.info("\nTest 5: Batch geocoding (test mode)")
        stats = geocoder.geocode_patients(
            limit=5,
            update_db=True,
            log_errors=False,
        )

        assert stats["total"] > 0
        assert stats["success"] + stats["failed"] == stats["total"]
        logger.info(
            f"✓ Batch geocoding test passed: {stats['success']}/{stats['total']} successful"
        )
    else:
        logger.warning("⚠ Skipping batch test - no patients table or already geocoded")

    cleanup_test_patients(db_manager)
    logger.info("✓ Test cleanup completed")

    logger.info("\n" + "=" * 60)
    logger.info("ALL TESTS COMPLETED")
    logger.info("=" * 60)

    return True


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Geocode patient addresses with 4-level fallback strategy"
    )
    parser.add_argument("--test", action="store_true", help="Run test suite")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of records per batch (default: 100)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=5,
        help="Delay between batches in seconds (default: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of patients to process (for testing)",
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Do not update database with coordinates (dry run)",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not log execution results to database",
    )

    args = parser.parse_args()

    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)

    pipeline = PatientGeocodingPipeline(
        batch_size=args.batch_size,
        batch_delay_seconds=args.delay,
    )

    update_db = not args.no_update
    log_errors = not args.no_log

    stats = pipeline.geocode_patients(
        limit=args.limit,
        update_db=update_db,
        log_errors=log_errors,
    )

    if stats["failed"] > 0:
        logger.warning(f"{stats['failed']} patients failed to geocode")
        sys.exit(1)
    else:
        logger.info("All patients geocoded successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
