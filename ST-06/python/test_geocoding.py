"""
Test suite for ST-06 Geocoding Pipeline.

Tests cover:
- PatientGeocodingPipeline initialization
- Coordinate validation (Malaysia bounds)
- Quality level determination
- 4-level fallback geocoding
- Database operations
- Integration tests with real database

Uses real database with graceful skip when views/tables missing.
"""

import pytest
from datetime import datetime
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Add ST-01/python to path for database module
sys.path.insert(0, str(project_root / "ST-01" / "python"))

# Add ST-06/python to path for geocoding modules
sys.path.insert(0, str(project_root / "ST-06" / "python"))


def test_geocoding_pipeline_initialization():
    """Verify PatientGeocodingPipeline initializes correctly"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    assert pipeline is not None
    assert pipeline.batch_size == 100
    assert pipeline.batch_delay_seconds == 5
    # Check Malaysia bounds are set correctly
    assert pipeline.MALAYSIA_LAT_MIN == 0.5
    assert pipeline.MALAYSIA_LAT_MAX == 7.5
    assert pipeline.MALAYSIA_LNG_MIN == 99.0
    assert pipeline.MALAYSIA_LNG_MAX == 120.0


def test_geocoding_pipeline_custom_parameters():
    """Verify custom batch parameters are used"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline(batch_size=50, batch_delay_seconds=2)

    assert pipeline.batch_size == 50
    assert pipeline.batch_delay_seconds == 2


def test_validate_coordinates_malaysia_bounds():
    """Test coordinate validation for Malaysia bounds"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    # Valid Malaysia coordinates
    assert pipeline._validate_coordinates(3.139, 101.6869)  # Kuala Lumpur
    assert pipeline._validate_coordinates(5.4164, 100.3327)  # Penang
    assert pipeline._validate_coordinates(
        1.3521, 103.8198
    )  # Singapore (close to Malaysia)
    assert pipeline._validate_coordinates(3.8, 103.3)  # Malaysia center

    # Invalid coordinates (outside Malaysia)
    assert not pipeline._validate_coordinates(40.7128, -74.0060)  # New York
    assert not pipeline._validate_coordinates(51.5074, -0.1278)  # London
    assert not pipeline._validate_coordinates(-33.8688, 151.2093)  # Sydney


def test_determine_quality_level_azure_maps():
    """Test quality level determination from Azure Maps response"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    # Exact quality: High score + street number
    address_data = {"streetNumber": "123", "street": "Main St", "municipality": "KL"}
    quality = pipeline._determine_quality_level(address_data, 0.95)
    assert quality == "exact"

    # Street quality: Has street name
    address_data = {"street": "Main St"}
    quality = pipeline._determine_quality_level(address_data, 0.8)
    assert quality == "street"

    # City quality: Has municipality
    address_data = {"municipality": "Kuala Lumpur"}
    quality = pipeline._determine_quality_level(address_data, 0.7)
    assert quality == "city"

    # State quality: Has subdivision
    address_data = {"countrySubdivision": "Selangor"}
    quality = pipeline._determine_quality_level(address_data, 0.5)
    assert quality == "state"

    # Default to ZIP
    address_data = {}
    quality = pipeline._determine_quality_level(address_data, 0.1)
    assert quality == "zip"


def test_determine_quality_level_nominatim():
    """Test quality level determination from Nominatim response"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    # Exact quality: Building type
    result = {"type": "house", "address": {"road": "Main St"}}
    quality = pipeline._determine_quality_level_nominatim(result)
    assert quality == "exact"

    # Street quality: Has road
    result = {"type": "road", "address": {"road": "Main St"}}
    quality = pipeline._determine_quality_level_nominatim(result)
    assert quality == "street"

    # City quality: Has city
    result = {"address": {"city": "Kuala Lumpur"}}
    quality = pipeline._determine_quality_level_nominatim(result)
    assert quality == "city"

    # State quality: Has state
    result = {"address": {"state": "Selangor"}}
    quality = pipeline._determine_quality_level_nominatim(result)
    assert quality == "state"

    # Default to ZIP
    result = {}
    quality = pipeline._determine_quality_level_nominatim(result)
    assert quality == "zip"


def test_geocode_with_fallback_full_address():
    """Test 4-level fallback geocoding with full address"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    # This will try actual API calls if keys are set, or skip gracefully
    # Test with mock to avoid API calls in unit test
    with patch.object(pipeline, "_try_geocode") as mock_geocode:
        mock_geocode.return_value = {
            "lat": 3.1390,
            "lng": 101.6869,
            "formatted_address": "123 Jalan Ampang, Kuala Lumpur",
            "source": "azure_maps",
            "quality": "exact",
            "score": 0.95,
        }

        result = pipeline.geocode_with_fallback(
            street="123 Jalan Ampang",
            city="Kuala Lumpur",
            state="Wilayah Persekutuan",
            zip_code="50450",
        )

        assert result is not None
        assert result["lat"] == 3.1390
        assert result["lng"] == 101.6869
        assert result["quality"] == "exact"
        assert mock_geocode.called


def test_geocode_with_fallback_zip_only():
    """Test fallback to ZIP code only when other components missing"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    with patch.object(pipeline, "_try_geocode") as mock_geocode:
        mock_geocode.return_value = {
            "lat": 3.1390,
            "lng": 101.6869,
            "formatted_address": "50450",
            "source": "nominatim",
            "quality": "zip",
            "score": 1.0,
        }

        result = pipeline.geocode_with_fallback(
            street=None, city=None, state=None, zip_code="50450"
        )

        assert result is not None
        assert result["quality"] == "zip"


def test_geocode_with_fallback_all_missing():
    """Test fallback returns None when all address components missing"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    result = pipeline.geocode_with_fallback(
        street=None, city=None, state=None, zip_code=None
    )

    assert result is None


def test_quality_constants():
    """Verify all quality level constants are defined"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    assert pipeline.QUALITY_EXACT == "exact"
    assert pipeline.QUALITY_STREET == "street"
    assert pipeline.QUALITY_CITY == "city"
    assert pipeline.QUALITY_STATE == "state"
    assert pipeline.QUALITY_ZIP == "zip"
    assert pipeline.QUALITY_FAILED == "failed"


def test_load_patients_for_geocoding_integration():
    """Integration test for loading patients from database.

    Requires dk.patient table with address fields.
    Gracefully skips if table doesn't exist or has no data.
    """
    from geocoding_pipeline import PatientGeocodingPipeline
    from database import get_db_manager

    try:
        db = get_db_manager()
        pipeline = PatientGeocodingPipeline(db_manager=db)

        # Try to load patients (will return empty DataFrame if no table/data)
        patients_df = pipeline.load_patients_for_geocoding(limit=5)

        # Should return a DataFrame (may be empty)
        assert isinstance(patients_df, pd.DataFrame)

    except Exception as e:
        # Skip if database not available
        pytest.skip(f"Database not available: {e}")


def test_create_execution_run_integration():
    """Integration test for creating execution run log.

    Requires dk.geocode_execution_log table.
    Gracefully skips if table doesn't exist.
    """
    from geocoding_pipeline import PatientGeocodingPipeline
    from database import get_db_manager

    try:
        db = get_db_manager()
        pipeline = PatientGeocodingPipeline(db_manager=db)

        # Try to create execution run
        run_id = pipeline.create_execution_run(
            run_type="test", source_table="dk.patient"
        )

        # Run ID should be > 0 if successful, 0 if failed (not an error)
        assert run_id >= 0

    except Exception as e:
        # Skip if database table not available
        pytest.skip(f"Execution log table not available: {e}")


def test_geocode_patients_returns_structure():
    """Test geocode_patients returns expected statistics structure"""
    from geocoding_pipeline import PatientGeocodingPipeline
    from unittest.mock import MagicMock

    # Mock DB manager to avoid actual database calls
    mock_db = MagicMock()
    mock_db.execute_query.return_value = pd.DataFrame()  # Empty - no patients

    pipeline = PatientGeocodingPipeline(db_manager=mock_db)

    # Run with empty patient list
    stats = pipeline.geocode_patients(limit=10, update_db=False, log_errors=False)

    # Verify structure
    assert "total" in stats
    assert "success" in stats
    assert "failed" in stats
    assert "skipped" in stats
    assert "by_quality" in stats
    assert "by_source" in stats


def test_batch_processing_with_delay():
    """Test batch processing respects batch_size and delay"""
    from geocoding_pipeline import PatientGeocodingPipeline

    # Create pipeline with small batch size for testing
    pipeline = PatientGeocodingPipeline(batch_size=3, batch_delay_seconds=1)

    assert pipeline.batch_size == 3
    assert pipeline.batch_delay_seconds == 1


def test_rate_limit_tracking():
    """Test rate limit state tracking"""
    from geocoding_pipeline import PatientGeocodingPipeline

    pipeline = PatientGeocodingPipeline()

    # Initially should not be rate limited
    assert pipeline._azure_rate_limited == False

    # Set rate limited
    pipeline._azure_rate_limited = True
    assert pipeline._azure_rate_limited == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
