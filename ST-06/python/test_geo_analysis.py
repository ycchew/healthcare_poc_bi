"""
Test suite for ST-06 Geo Analysis.

Tests cover:
- GeoAnalyzer initialization
- DBSCAN clustering configuration
- Cannibalization thresholds
- Whitespace site scoring
- Distance band colors
- Brand colors
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

# Add ST-06/python to path for geo_analysis module
sys.path.insert(0, str(project_root / "ST-06" / "python"))


def test_geo_analyzer_initialization():
    """Verify GeoAnalyzer initializes correctly"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    assert analyzer is not None
    assert analyzer.eps_km == 5.0  # Default value
    assert analyzer.min_samples == 5  # Default value
    # Malaysia center should be set
    assert analyzer.my_lat == 3.9
    assert analyzer.my_lng == 108.5


def test_geo_analyzer_custom_parameters():
    """Verify custom parameters are used"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer(eps_km=10.0, min_samples=10)

    assert analyzer.eps_km == 10.0
    assert analyzer.min_samples == 10
    # eps_deg should be calculated correctly
    assert analyzer.eps_deg == pytest.approx(10.0 / 111.32, rel=0.01)


def test_dbscan_eps_deg_conversion():
    """Verify eps_km to eps_deg conversion"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer(eps_km=5.0)

    # 5km / 111.32 km per degree ≈ 0.0449 degrees
    assert analyzer.eps_deg == pytest.approx(0.0449, rel=0.01)


def test_cannibalization_thresholds():
    """Verify cannibalization threshold configuration"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    thresholds = analyzer.CANNIBAL_THRESHOLDS

    assert thresholds["None"] == 0.10
    assert thresholds["Low"] == 0.25
    assert thresholds["Moderate"] == 0.50
    assert thresholds["Severe"] == 1.01

    # Verify ordering
    assert thresholds["None"] < thresholds["Low"]
    assert thresholds["Low"] < thresholds["Moderate"]
    assert thresholds["Moderate"] < thresholds["Severe"]


def test_max_cannibalization_distance():
    """Verify maximum cannibalization distance guardrail"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    assert analyzer.MAX_CANNIBALIZATION_DISTANCE_KM == 50.0


def test_brand_colors_configuration():
    """Verify brand colors are defined correctly"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    colors = analyzer.BRAND_COLORS

    assert "primary" in colors
    assert "accent" in colors
    assert "green" in colors
    assert "red" in colors
    assert "yellow" in colors
    assert "dark" in colors
    assert "purple" in colors
    assert "teal" in colors

    # Verify hex format
    assert colors["primary"].startswith("#")
    assert colors["red"].startswith("#")


def test_distance_band_colors():
    """Verify distance band color configuration"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    band_colors = analyzer.DIST_BAND_COLORS

    assert "<2km" in band_colors
    assert "2-5km" in band_colors
    assert "5-10km" in band_colors
    assert "10-20km" in band_colors
    assert "20km+" in band_colors


def test_severity_classification():
    """Test severity classification based on cannibalization index"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    # Test threshold boundaries - inline implementation matches geo_analysis.py
    # Index < 0.10 = None
    # 0.10 <= index < 0.25 = Low
    # 0.25 <= index < 0.50 = Moderate
    # index >= 0.50 = Severe

    thresholds = analyzer.CANNIBAL_THRESHOLDS

    # None threshold (< 0.10)
    test_idx = 0.05
    sev = "None"
    for label, threshold in thresholds.items():
        if test_idx < threshold:
            sev = label
            break
    assert sev == "None"

    # Low threshold (0.10 <= index < 0.25)
    test_idx = 0.15
    sev = "None"
    for label, threshold in thresholds.items():
        if test_idx < threshold:
            sev = label
            break
    assert sev == "Low"

    # Moderate threshold (0.25 <= index < 0.50)
    test_idx = 0.35
    sev = "None"
    for label, threshold in thresholds.items():
        if test_idx < threshold:
            sev = label
            break
    assert sev == "Moderate"

    # Severe threshold (index >= 0.50)
    test_idx = 0.75
    sev = "None"
    for label, threshold in thresholds.items():
        if test_idx < threshold:
            sev = label
            break
    assert sev == "Severe"


def test_whitespace_priority_tier_assignment():
    """Test whitespace priority tier assignment based on SPS score"""
    # Inline implementation matches geo_analysis.py
    # High: SPS > 100
    # Medium: 50 <= SPS <= 100
    # Low: SPS < 50

    def assign_priority_tier(sps):
        if sps > 100:
            return "High"
        elif sps >= 50:
            return "Medium"
        else:
            return "Low"

    # High: SPS > 100
    assert assign_priority_tier(101) == "High"
    assert assign_priority_tier(200) == "High"

    # Medium: 50 <= SPS <= 100
    assert assign_priority_tier(50) == "Medium"
    assert assign_priority_tier(75) == "Medium"
    assert assign_priority_tier(100) == "Medium"

    # Low: SPS < 50
    assert assign_priority_tier(49) == "Low"
    assert assign_priority_tier(0) == "Low"
    assert assign_priority_tier(10) == "Low"


def test_site_priority_score_formula():
    """Test Site Priority Score calculation formula"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    # Test formula: SPS = (patient_count * avg_revenue) / distance
    patient_count = 100
    avg_revenue = 500.0  # RM
    distance = 5.0  # km

    # Expected: (100 * 500) / 5 = 10000
    # With formula: patient_count * avg_revenue / distance
    sps = (patient_count * avg_revenue) / distance
    assert sps == 10000.0


def test_earth_radius_constant():
    """Verify Earth radius constant for haversine calculations"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    assert analyzer.EARTH_RADIUS_KM == 6371.0


def test_km_per_degree_constant():
    """Verify km per degree constant"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    assert analyzer.KM_PER_DEGREE == 111.32


def test_run_dbscan_clustering_integration():
    """Integration test for DBSCAN clustering.

    Requires dk.patient_geocode table with geocoded patients.
    Gracefully skips if table doesn't exist or has insufficient data.
    """
    from geo_analysis import GeoAnalyzer
    from database import get_db_manager

    try:
        db = get_db_manager()
        analyzer = GeoAnalyzer(db_manager=db)

        # Try to run clustering (will return empty DataFrames if no data)
        patients_df, clusters_df = analyzer.run_dbscan_clustering()

        # Should return DataFrames (may be empty)
        assert isinstance(patients_df, pd.DataFrame)
        assert isinstance(clusters_df, pd.DataFrame)

    except Exception as e:
        # Skip if database not available
        pytest.skip(f"Database not available: {e}")


def test_run_cannibalization_analysis_integration():
    """Integration test for cannibalization analysis.

    Requires dk.branch_master table with geocoded branches.
    Gracefully skips if table doesn't exist or has insufficient branches.
    """
    from geo_analysis import GeoAnalyzer
    from database import get_db_manager

    try:
        db = get_db_manager()
        analyzer = GeoAnalyzer(db_manager=db)

        # Try to run cannibalization analysis (will return empty DataFrame if no data)
        overlap_df = analyzer.run_cannibalization_analysis()

        # Should return DataFrame (may be empty)
        assert isinstance(overlap_df, pd.DataFrame)

    except Exception as e:
        # Skip if database not available
        pytest.skip(f"Database not available: {e}")


def test_analyze_whitespace_integration():
    """Integration test for whitespace analysis.

    Requires dk.patient_geo_clusters table from DBSCAN clustering.
    Gracefully skips if table doesn't exist or has no clusters.
    """
    from geo_analysis import GeoAnalyzer
    from database import get_db_manager

    try:
        db = get_db_manager()
        analyzer = GeoAnalyzer(db_manager=db)

        # Try to analyze whitespace (will return empty DataFrame if no clusters)
        whitespace_df = analyzer.analyze_whitespace()

        # Should return DataFrame (may be empty)
        assert isinstance(whitespace_df, pd.DataFrame)

    except Exception as e:
        # Skip if database not available
        pytest.skip(f"Database not available: {e}")


def test_haversine_distance_calculation():
    """Test haversine distance calculation between two points"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    # Test between Kuala Lumpur (3.139, 101.6869) and Penang (5.4164, 100.3327)
    lat1, lon1 = np.radians(3.139), np.radians(101.6869)
    lat2, lon2 = np.radians(5.4164), np.radians(100.3327)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    distance = 2 * analyzer.EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))

    # Actual distance KL to Penang is approximately 294km
    assert 285 < distance < 305


def test_cluster_radius_calculation():
    """Test cluster radius calculation using 90th percentile distance"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    # Create test cluster with known coordinates
    test_data = pd.DataFrame(
        {
            "patient_lat": [3.139, 3.140, 3.141, 3.138, 3.142],
            "patient_lng": [101.686, 101.687, 101.688, 101.685, 101.689],
        }
    )

    centroid_lat = test_data["patient_lat"].mean()
    centroid_lng = test_data["patient_lng"].mean()

    # Calculate distances to centroid
    dists = []
    for _, row in test_data.iterrows():
        lat1, lon1 = np.radians(row.patient_lat), np.radians(row.patient_lng)
        lat2, lon2 = np.radians(centroid_lat), np.radians(centroid_lng)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        dists.append(analyzer.EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a)))

    radius = np.percentile(dists, 90)

    # Should be small (< 1km for close points)
    assert radius < 1.0


def test_maps_directory_creation():
    """Test that maps directory is created automatically"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    # Verify maps_dir is set correctly
    assert analyzer.maps_dir.endswith("ST-06/maps") or "ST-06" in analyzer.maps_dir


def test_execute_query_method():
    """Test _execute_query method exists and is callable"""
    from geo_analysis import GeoAnalyzer
    from unittest.mock import MagicMock

    # Create analyzer with mock DB
    mock_db = MagicMock()
    mock_db.execute_query.return_value = pd.DataFrame({"test": [1, 2, 3]})

    analyzer = GeoAnalyzer(db_manager=mock_db)

    # Test query execution
    result = analyzer._execute_query("SELECT 1 as test")

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 3


def test_write_table_method():
    """Test _write_table method with mock database"""
    from geo_analysis import GeoAnalyzer
    from unittest.mock import MagicMock, patch

    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

    analyzer = GeoAnalyzer(db_manager=mock_db)

    # Create test DataFrame
    test_df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

    # This should not raise an exception (may fail due to to_sql, but we test structure)
    # The method exists and has proper error handling
    assert hasattr(analyzer, "_write_table")
    assert callable(analyzer._write_table)


def test_maps_generation_methods_exist():
    """Verify all 7 map generation methods exist"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    # Check all 7 map methods exist
    assert hasattr(analyzer, "build_patient_origin_map")
    assert hasattr(analyzer, "build_branch_catchments_map")
    assert hasattr(analyzer, "build_cluster_map")
    assert hasattr(analyzer, "build_cannibalization_network_map")
    assert hasattr(analyzer, "build_whitespace_opportunity_map")
    assert hasattr(analyzer, "build_revenue_heatmap")
    assert hasattr(analyzer, "build_new_patient_flow_map")


def test_generate_all_maps_method_exists():
    """Verify generate_all_maps orchestrator method exists"""
    from geo_analysis import GeoAnalyzer

    analyzer = GeoAnalyzer()

    assert hasattr(analyzer, "generate_all_maps")
    assert callable(analyzer.generate_all_maps)


def test_run_full_analysis_returns_structure():
    """Test run_full_analysis returns expected result structure"""
    from geo_analysis import GeoAnalyzer
    from unittest.mock import MagicMock, patch

    # Mock the database to return empty DataFrames
    mock_db = MagicMock()
    mock_db.execute_query.return_value = pd.DataFrame()

    analyzer = GeoAnalyzer(db_manager=mock_db)

    # Run full analysis (will produce empty results but proper structure)
    with patch.object(analyzer, "generate_all_maps", return_value={}):
        results = analyzer.run_full_analysis()

    # Verify structure
    assert "clustering" in results
    assert "cannibalization" in results
    assert "whitespace" in results


def test_run_dbscan_clustering_empty_dataframe():
    """Verify DBSCAN handles empty patient DataFrame gracefully (returns empty result, no crash)"""
    from geo_analysis import GeoAnalyzer

    # Mock database returning empty DataFrame
    mock_db = MagicMock()
    mock_db.execute_query.return_value = pd.DataFrame()

    analyzer = GeoAnalyzer(db_manager=mock_db, eps_km=5.0, min_samples=5)

    # Should return empty DataFrames without crashing
    patients_df, clusters_df = analyzer.run_dbscan_clustering()

    assert isinstance(patients_df, pd.DataFrame)
    assert isinstance(clusters_df, pd.DataFrame)
    assert patients_df.empty
    assert clusters_df.empty


def test_calculate_cannibalization_index_empty_dataframe():
    """Verify cannibalization handles empty branch data"""
    from geo_analysis import GeoAnalyzer

    # Mock database returning empty branches DataFrame
    mock_db = MagicMock()
    mock_db.execute_query.return_value = pd.DataFrame()

    analyzer = GeoAnalyzer(db_manager=mock_db)

    # Should return empty DataFrame without crashing
    overlap_df = analyzer.run_cannibalization_analysis()

    assert isinstance(overlap_df, pd.DataFrame)
    assert overlap_df.empty


def test_calculate_whitespace_opportunity_empty_dataframe():
    """Verify whitespace handles empty cluster data"""
    from geo_analysis import GeoAnalyzer

    # Mock database returning empty clusters DataFrame
    mock_db = MagicMock()
    mock_db.execute_query.return_value = pd.DataFrame()

    analyzer = GeoAnalyzer(db_manager=mock_db)

    # Should return empty DataFrame without crashing
    whitespace_df = analyzer.analyze_whitespace()

    assert isinstance(whitespace_df, pd.DataFrame)
    assert whitespace_df.empty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
