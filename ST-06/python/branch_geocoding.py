"""
ST-06: Geospatial Analytics
Branch Geocoding Module - Azure Maps API with Nominatim Fallback

This module geocodes branch addresses using Azure Maps API with fallback to Nominatim.
It updates branch coordinates in dk.branch_master and logs execution to dk.branch_geocode_log.

Usage:
    python ST-06/python/branch_geocoding.py              # Run geocoding
    python ST-06/python/branch_geocoding.py --test       # Run test mode
    python ST-06/python/branch_geocoding.py --csv <path> # Use custom CSV file
"""

import os
import sys
import logging
import argparse
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


class BranchGeocoder:
    """
    Geocodes branch addresses using Azure Maps API with Nominatim fallback.
    """

    AZURE_MAPS_BASE_URL = "https://atlas.microsoft.com/search"
    NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search"
    MALAYSIA_LAT_MIN = 0.5
    MALAYSIA_LAT_MAX = 7.5
    MALAYSIA_LNG_MIN = 99.0
    MALAYSIA_LNG_MAX = 120.0

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager.get_instance()
        self.azure_maps_key = os.getenv("AZURE_MAPS_PRIMARY_KEY")
        self.azure_maps_client_id = os.getenv("AZURE_MAPS_CLIENT_ID")
        self.azure_timeout = int(os.getenv("AZURE_MAPS_TIMEOUT", "30"))
        self.nominatim_timeout = int(os.getenv("NOMINATIM_TIMEOUT", "30"))
        self.user_agent = os.getenv(
            "NOMINATIM_USER_AGENT", "healthcare_bi_geocoder/1.0"
        )

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
            Dictionary with 'lat', 'lng', 'formatted_address' or None if failed
        """
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

                    logger.info(
                        f"Azure Maps: {address[:50]}... -> ({lat:.6f}, {lng:.6f})"
                    )

                    return {
                        "lat": lat,
                        "lng": lng,
                        "formatted_address": formatted_address,
                        "source": "azure_maps",
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
            return None
        except Exception as e:
            logger.error(f"Azure Maps parsing error: {e}")
            return None

    def geocode_with_nominatim(
        self, address: str, country: str = "Malaysia"
    ) -> Optional[Dict[str, Any]]:
        """
        Geocode an address using Nominatim (OpenStreetMap) as fallback.

        Args:
            address: The address to geocode
            country: Country name to append to query (default: Malaysia)

        Returns:
            Dictionary with 'lat', 'lng', 'formatted_address' or None if failed
        """
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

                    logger.info(
                        f"Nominatim: {address[:50]}... -> ({lat:.6f}, {lng:.6f})"
                    )

                    return {
                        "lat": lat,
                        "lng": lng,
                        "formatted_address": formatted_address,
                        "source": "nominatim",
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

    def geocode(
        self, address: str, country: str = "Malaysia"
    ) -> Optional[Dict[str, Any]]:
        """
        Geocode an address using Azure Maps with Nominatim fallback.

        Args:
            address: The address to geocode
            country: Country name to append to query (default: Malaysia)

        Returns:
            Dictionary with 'lat', 'lng', 'formatted_address', 'source' or None if failed
        """
        # Try Azure Maps first (if key is configured)
        if self.azure_maps_key:
            result = self.geocode_with_azure_maps(address, country)
            if result:
                return result
            else:
                logger.info(
                    f"Azure Maps failed, trying Nominatim for: {address[:50]}..."
                )

        # Fallback to Nominatim
        result = self.geocode_with_nominatim(address, country)
        if result:
            return result

        # Both methods failed
        logger.warning(f"Geocoding failed for address: {address}")
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

    def load_branches_from_csv(self, csv_path: str) -> pd.DataFrame:
        """
        Load branch addresses from CSV file.

        Expected columns: branch_code, branch_name, address, street, city, state, zip, country

        Args:
            csv_path: Path to CSV file

        Returns:
            DataFrame with branch data
        """
        logger.info(f"Loading branches from: {csv_path}")

        df = pd.read_csv(csv_path)

        # Validate required columns
        required_cols = ["branch_name", "address", "city", "state", "zip"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Add branch_code if not present (auto-generate)
        if "branch_code" not in df.columns:
            df["branch_code"] = [f"B{str(i).zfill(3)}" for i in range(1, len(df) + 1)]

        # Add country if not present (default: Malaysia)
        if "country" not in df.columns:
            df["country"] = "Malaysia"

        # Add street if not present (extract from address or use empty)
        if "street" not in df.columns:
            df["street"] = ""

        logger.info(f"Loaded {len(df)} branches from CSV")
        return df

    def build_address_string(self, row: pd.Series) -> str:
        """
        Build a complete address string from row components.

        Args:
            row: DataFrame row with address components

        Returns:
            Formatted address string
        """
        parts = []

        # Add street if available
        if pd.notna(row.get("street")) and str(row["street"]).strip():
            parts.append(str(row["street"]).strip())

        # Add address if available
        if pd.notna(row.get("address")) and str(row["address"]).strip():
            parts.append(str(row["address"]).strip())

        # Add city
        if pd.notna(row.get("city")) and str(row["city"]).strip():
            parts.append(str(row["city"]).strip())

        # Add state
        if pd.notna(row.get("state")) and str(row["state"]).strip():
            parts.append(str(row["state"]).strip())

        # Add zip
        if pd.notna(row.get("zip")) and str(row["zip"]).strip():
            parts.append(str(row["zip"]).strip())

        # Join with commas
        return ", ".join(parts)

    def update_branch_coordinates(
        self,
        branch_code: str,
        lat: float,
        lng: float,
        formatted_address: str,
        source: str,
    ) -> bool:
        """
        Update branch coordinates in dk.branch_master table.

        Args:
            branch_code: Branch code identifier
            lat: Latitude coordinate
            lng: Longitude coordinate
            formatted_address: Formatted address from geocoding
            source: Geocoding source (azure_maps or nominatim)

        Returns:
            True if successful, False otherwise
        """
        sql = """
            UPDATE dk.branch_master
            SET lat = :lat,
                lng = :lng,
                geocoded_address = :geocoded_address,
                geocode_source = :geocode_source,
                geocode_timestamp = :geocode_timestamp
            WHERE branch_code = :branch_code
        """

        params = {
            "branch_code": branch_code,
            "lat": lat,
            "lng": lng,
            "geocoded_address": formatted_address,
            "geocode_source": source,
            "geocode_timestamp": datetime.now(),
        }

        try:
            # Use execute_query with return_df=False for UPDATE operations
            self.db_manager.execute_query_raw(sql, params)
            logger.info(f"Updated coordinates for branch {branch_code}")
            return True
        except Exception as e:
            logger.error(f"Failed to update coordinates for {branch_code}: {e}")
            return False

    def log_geocode_execution(
        self,
        branch_code: str,
        original_address: str,
        geocoded_address: str,
        lat: Optional[float],
        lng: Optional[float],
        source: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Log geocoding execution to dk.branch_geocode_log table.

        Args:
            branch_code: Branch code identifier
            original_address: Original address that was geocoded
            geocoded_address: Geocoded address returned by API
            lat: Latitude coordinate (None if failed)
            lng: Longitude coordinate (None if failed)
            source: Geocoding source (azure_maps, nominatim, or none)
            status: Execution status (SUCCESS or FAILED)
            error_message: Error message if failed

        Returns:
            True if successful, False otherwise
        """
        sql = """
            INSERT INTO dk.branch_geocode_log (
                branch_code,
                original_address,
                geocoded_address,
                lat,
                lng,
                geocode_source,
                status,
                error_message,
                execution_timestamp
            ) VALUES (
                :branch_code,
                :original_address,
                :geocoded_address,
                :lat,
                :lng,
                :geocode_source,
                :status,
                :error_message,
                :execution_timestamp
            )
        """

        params = {
            "branch_code": branch_code,
            "original_address": original_address,
            "geocoded_address": geocoded_address
            if geocoded_address
            else original_address,
            "lat": lat,
            "lng": lng,
            "geocode_source": source if source != "none" else None,
            "status": status,
            "error_message": error_message,
            "execution_timestamp": datetime.now(),
        }

        try:
            self.db_manager.execute_query_raw(sql, params)
            logger.debug(f"Logged geocode execution for branch {branch_code}")
            return True
        except Exception as e:
            logger.error(f"Failed to log geocode execution: {e}")
            return False

    def geocode_branches(
        self, csv_path: str, update_db: bool = True, log_errors: bool = True
    ) -> Dict[str, Any]:
        """
        Geocode all branches from CSV file.

        Args:
            csv_path: Path to CSV file with branch addresses
            update_db: If True, update coordinates in database
            log_errors: If True, log execution results to database

        Returns:
            Dictionary with geocoding statistics
        """
        logger.info("Starting branch geocoding process...")

        # Load branches from CSV
        df = self.load_branches_from_csv(csv_path)

        # Track statistics
        stats = {
            "total": len(df),
            "success": 0,
            "failed": 0,
            "azure_maps": 0,
            "nominatim": 0,
            "results": [],
        }

        # Process each branch
        for idx, row in df.iterrows():
            branch_code = row.get("branch_code", f"UNKNOWN_{idx}")
            branch_name = row.get("branch_name", "Unknown")

            # Build address string
            address = self.build_address_string(row)
            country = row.get("country", "Malaysia")

            logger.info(
                f"Geocoding [{idx + 1}/{len(df)}]: {branch_code} - {branch_name}"
            )

            # Geocode the address
            result = self.geocode(address, country)

            if result:
                # Success
                stats["success"] += 1
                if result["source"] == "azure_maps":
                    stats["azure_maps"] += 1
                else:
                    stats["nominatim"] += 1

                # Update database if requested
                if update_db:
                    self.update_branch_coordinates(
                        branch_code=branch_code,
                        lat=result["lat"],
                        lng=result["lng"],
                        formatted_address=result["formatted_address"],
                        source=result["source"],
                    )

                # Log execution
                if log_errors:
                    self.log_geocode_execution(
                        branch_code=branch_code,
                        original_address=address,
                        geocoded_address=result["formatted_address"],
                        lat=result["lat"],
                        lng=result["lng"],
                        source=result["source"],
                        status="SUCCESS",
                    )

                stats["results"].append(
                    {
                        "branch_code": branch_code,
                        "branch_name": branch_name,
                        "status": "SUCCESS",
                        "source": result["source"],
                        "lat": result["lat"],
                        "lng": result["lng"],
                    }
                )

            else:
                # Failed
                stats["failed"] += 1

                # Log error
                if log_errors:
                    self.log_geocode_execution(
                        branch_code=branch_code,
                        original_address=address,
                        geocoded_address=None,
                        lat=None,
                        lng=None,
                        source="none",
                        status="FAILED",
                        error_message="No geocoding result from Azure Maps or Nominatim",
                    )

                stats["results"].append(
                    {
                        "branch_code": branch_code,
                        "branch_name": branch_name,
                        "status": "FAILED",
                        "source": None,
                        "lat": None,
                        "lng": None,
                    }
                )

        # Log summary
        logger.info("=" * 60)
        logger.info("GEOCODING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total branches: {stats['total']}")
        logger.info(f"Successful: {stats['success']}")
        logger.info(f"Failed: {stats['failed']}")
        logger.info(f"Azure Maps: {stats['azure_maps']}")
        logger.info(f"Nominatim: {stats['nominatim']}")
        logger.info(f"Success rate: {stats['success'] / stats['total'] * 100:.1f}%")
        logger.info("=" * 60)

        return stats


def create_test_csv() -> str:
    """Create a test CSV file with sample branch addresses."""
    csv_content = """branch_code,branch_name,address,street,city,state,zip,country
B001,Klinik Dr Ko Ampang,"Ampang Point, 73, Jalan Memanda 1, Taman Dato Ahmad Razali",Jalan Memanda 1,Ampang,Selangor,68000,Malaysia
B002,Klinik Dr Ko Cyberjaya,"Unit 4812-0-52, Blok 4812, Jln Perdana, CBD Perdana 2",Jalan Perdana,Cyberjaya,Selangor,63000,Malaysia
B003,Klinik Dr Ko Kajang,"Kompleks Sentral Point G-10, G, 11, Jalan TKS 1, Taman Kajang Sentral",Jalan TKS 1,Kajang,Selangor,43000,Malaysia
B004,Klinik Dr Ko Taman Melawati,"No.7-1, Jalan Ulu Kelang, Batu 8, Ukay Boulevard",Jalan Ulu Kelang,Ampang,Selangor,68000,Malaysia
B005,Klinik Dr Ko Subang Jaya,"No. 12, Jalan USJ 1/1, USJ 1",Jalan USJ 1/1,Subang Jaya,Selangor,47600,Malaysia
"""

    csv_path = os.path.join(os.path.dirname(__file__), "test_branches.csv")

    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(csv_content)

    logger.info(f"Created test CSV file: {csv_path}")
    return csv_path


def run_tests():
    """Run tests for the branch geocoding module."""
    logger.info("=" * 60)
    logger.info("RUNNING BRANCH GEOCODING TESTS")
    logger.info("=" * 60)

    # Initialize geocoder
    geocoder = BranchGeocoder()

    # Test 1: Coordinate validation
    logger.info("\nTest 1: Coordinate validation")
    assert geocoder._validate_coordinates(3.139, 101.6869), (
        "Kuala Lumpur should be valid"
    )
    assert geocoder._validate_coordinates(5.4164, 100.3327), "Penang should be valid"
    assert geocoder._validate_coordinates(1.3521, 103.8198), (
        "Singapore should be valid (close to MY)"
    )
    assert not geocoder._validate_coordinates(40.7128, -74.0060), (
        "New York should be invalid"
    )
    assert not geocoder._validate_coordinates(51.5074, -0.1278), (
        "London should be invalid"
    )
    logger.info("✓ Coordinate validation tests passed")

    # Test 2: Address building
    logger.info("\nTest 2: Address building")
    test_row = pd.Series(
        {
            "street": "123 Main St",
            "address": "Building A",
            "city": "Kuala Lumpur",
            "state": "Wilayah Persekutuan",
            "zip": "50000",
        }
    )
    address = geocoder.build_address_string(test_row)
    assert "123 Main St" in address
    assert "Kuala Lumpur" in address
    assert "50000" in address
    logger.info(f"✓ Address building test passed: {address}")

    # Test 3: Geocoding (Azure Maps or Nominatim)
    logger.info("\nTest 3: Geocoding single address")
    test_address = "Ampang Point, 73, Jalan Memanda 1, Taman Dato Ahmad Razali, Ampang, Selangor, 68000"
    result = geocoder.geocode(test_address, "Malaysia")

    if result:
        logger.info(f"✓ Geocoding test passed:")
        logger.info(f"  Source: {result['source']}")
        logger.info(f"  Coordinates: ({result['lat']:.6f}, {result['lng']:.6f})")
        logger.info(f"  Address: {result['formatted_address'][:80]}...")

        # Validate coordinates
        assert geocoder._validate_coordinates(result["lat"], result["lng"]), (
            "Coordinates should be within Malaysia"
        )
    else:
        logger.warning("⚠ Geocoding test skipped - no API access or address not found")

    # Test 4: CSV loading
    logger.info("\nTest 4: CSV loading and processing")
    test_csv = create_test_csv()
    df = geocoder.load_branches_from_csv(test_csv)
    assert len(df) == 5, "Should load 5 test branches"
    assert "branch_code" in df.columns
    assert "branch_name" in df.columns
    assert "country" in df.columns
    logger.info(f"✓ CSV loading test passed: {len(df)} branches loaded")

    # Test 5: Full geocoding process (small batch)
    logger.info("\nTest 5: Batch geocoding (test mode)")
    stats = geocoder.geocode_branches(
        test_csv,
        update_db=False,  # Don't update database in test mode
        log_errors=False,  # Don't log to database in test mode
    )

    assert stats["total"] == 5, "Should process 5 branches"
    assert stats["success"] + stats["failed"] == 5, "All branches should have status"
    logger.info(
        f"✓ Batch geocoding test passed: {stats['success']}/{stats['total']} successful"
    )

    # Cleanup
    if os.path.exists(test_csv):
        os.remove(test_csv)
        logger.info(f"Cleaned up test CSV file")

    logger.info("\n" + "=" * 60)
    logger.info("ALL TESTS COMPLETED")
    logger.info("=" * 60)

    return True


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Geocode branch addresses using Azure Maps API with Nominatim fallback"
    )
    parser.add_argument("--test", action="store_true", help="Run test suite")
    parser.add_argument(
        "--csv", type=str, default=None, help="Path to CSV file with branch addresses"
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Do not update database with coordinates (dry run)",
    )
    parser.add_argument(
        "--no-log", action="store_true", help="Do not log execution results to database"
    )

    args = parser.parse_args()

    # Run tests if requested
    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)

    # Get CSV path from args or use default
    csv_path = args.csv
    if not csv_path:
        # Check for default CSV in project root
        default_csv = os.path.join(
            os.path.dirname(__file__), "../../branch_address.csv"
        )
        if os.path.exists(default_csv):
            csv_path = default_csv
        else:
            logger.error(
                "No CSV file specified. Use --csv <path> or place branch_address.csv in project root"
            )
            sys.exit(1)

    # Validate CSV exists
    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)

    # Initialize geocoder
    geocoder = BranchGeocoder()

    # Run geocoding
    update_db = not args.no_update
    log_errors = not args.no_log

    stats = geocoder.geocode_branches(
        csv_path, update_db=update_db, log_errors=log_errors
    )

    # Exit with appropriate code
    if stats["failed"] > 0:
        logger.warning(f"{stats['failed']} branches failed to geocode")
        sys.exit(1)
    else:
        logger.info("All branches geocoded successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
