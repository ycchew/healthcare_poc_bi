"""
ST-06: Geospatial Analytics
Python module for geocoding and geographic analysis
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Tuple
from database import execute_query, execute_sql


def get_patient_geographic_distribution(
    branch_code: Optional[str] = None,
) -> pd.DataFrame:
    """Get patient geographic distribution."""
    query = "SELECT * FROM dk.vw_patient_geographic_distribution WHERE 1=1"
    if branch_code:
        query += f" AND nearest_branch_code = '{branch_code}'"
    return execute_query(query)


def get_catchment_analysis() -> pd.DataFrame:
    """Get catchment area analysis for all branches."""
    return execute_query("SELECT * FROM dk.vw_catchment_analysis")


def get_cannibalization_analysis() -> pd.DataFrame:
    """Get inter-branch cannibalization analysis."""
    return execute_query("SELECT * FROM dk.vw_cannibalization_analysis")


def get_geographic_hotspots(min_patients: int = 5) -> pd.DataFrame:
    """Get geographic hotspots by postcode."""
    query = f"""
    SELECT * FROM dk.vw_geographic_hotspots
    WHERE patient_count >= {min_patients}
    ORDER BY patient_count DESC
    """
    return execute_query(query)


def get_expansion_opportunities() -> pd.DataFrame:
    """Get expansion opportunity analysis."""
    return execute_query(
        "SELECT * FROM dk.vw_expansion_opportunities WHERE priority_level != 'Low Priority'"
    )


def update_patient_distances() -> None:
    """Update patient distances to nearest branch."""
    execute_sql("SELECT dk.update_patient_distances()")


def geocode_patient(
    mrn: str,
    address: str,
    postcode: str,
    city: str,
    state: str,
    latitude: float,
    longitude: float,
    source: str = "manual",
) -> None:
    """Geocode a patient address."""
    query = """
    INSERT INTO dk.patient_geocoding (
        mrn, address, postcode, city, state,
        latitude, longitude, geom, geocoding_source, geocoded_at
    ) VALUES (
        :mrn, :address, :postcode, :city, :state,
        :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
        :source, CURRENT_TIMESTAMP
    )
    ON CONFLICT (mrn) DO UPDATE SET
        address = EXCLUDED.address,
        postcode = EXCLUDED.postcode,
        city = EXCLUDED.city,
        state = EXCLUDED.state,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        geom = EXCLUDED.geom,
        geocoding_source = EXCLUDED.geocoding_source,
        geocoded_at = EXCLUDED.geocoded_at
    """

    params = {
        "mrn": mrn,
        "address": address,
        "postcode": postcode,
        "city": city,
        "state": state,
        "lat": latitude,
        "lon": longitude,
        "source": source,
    }

    execute_sql(query, params)


def create_folium_map(
    branch_code: Optional[str] = None, max_patients: int = 1000
) -> str:
    """Create a Folium map with patient locations."""
    try:
        import folium
        from folium.plugins import MarkerCluster
    except ImportError:
        return "Folium not installed. Install with: pip install folium"

    # Get branch location
    branch_query = "SELECT * FROM dk.branch_locations WHERE 1=1"
    if branch_code:
        branch_query += f" AND branch_code = '{branch_code}'"
    branches = execute_query(branch_query)

    # Get patient locations
    patient_query = f"""
    SELECT * FROM dk.vw_patient_geographic_distribution
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    LIMIT {max_patients}
    """
    if branch_code:
        patient_query = f"""
        SELECT * FROM dk.vw_patient_geographic_distribution
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
          AND nearest_branch_code = '{branch_code}'
        LIMIT {max_patients}
        """

    patients = execute_query(patient_query)

    if branches.empty:
        return "No branch data available"

    # Create map centered on first branch
    center_lat = branches["latitude"].iloc[0]
    center_lon = branches["longitude"].iloc[0]

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

    # Add branch markers
    for _, branch in branches.iterrows():
        folium.Marker(
            location=[branch["latitude"], branch["longitude"]],
            popup=f"{branch['branch_name']}<br>Radius: {branch['catchment_radius_km']}km",
            icon=folium.Icon(color="red", icon="hospital", prefix="fa"),
            tooltip=branch["branch_name"],
        ).add_to(m)

        # Add catchment circle
        folium.Circle(
            location=[branch["latitude"], branch["longitude"]],
            radius=branch["catchment_radius_km"] * 1000,  # Convert to meters
            popup=f"{branch['branch_name']} Catchment",
            color="blue",
            fill=True,
            fill_opacity=0.1,
        ).add_to(m)

    # Add patient markers
    if not patients.empty:
        marker_cluster = MarkerCluster().add_to(m)

        for _, patient in patients.iterrows():
            folium.CircleMarker(
                location=[patient["latitude"], patient["longitude"]],
                radius=5,
                popup=f"MRN: {patient['mrn']}<br>Revenue: ${patient['total_revenue']:.2f}",
                color="green"
                if patient["catchment_status"] == "Within Catchment"
                else "orange",
                fill=True,
                fill_opacity=0.7,
            ).add_to(marker_cluster)

    # Save map
    output_path = "./docs/output/patient_geographic_map.html"
    m.save(output_path)
    return output_path


def analyze_distance_distribution() -> pd.DataFrame:
    """Analyze patient distance distribution."""
    query = """
    SELECT 
        distance_band,
        catchment_status,
        COUNT(*) AS patient_count,
        AVG(total_revenue) AS avg_revenue,
        SUM(total_revenue) AS total_revenue
    FROM dk.vw_patient_geographic_distribution
    GROUP BY distance_band, catchment_status
    ORDER BY 
        CASE distance_band
            WHEN '0-5km' THEN 1
            WHEN '5-10km' THEN 2
            WHEN '10-20km' THEN 3
            WHEN '20-50km' THEN 4
            ELSE 5
        END
    """
    return execute_query(query)


def export_geographic_analysis(
    output_path: str = "./docs/output/geographic_analysis.xlsx",
) -> str:
    """Export geographic analysis to Excel."""
    distribution = get_patient_geographic_distribution()
    catchment = get_catchment_analysis()
    hotspots = get_geographic_hotspots()
    opportunities = get_expansion_opportunities()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        distribution.to_excel(writer, sheet_name="Patient Distribution", index=False)
        catchment.to_excel(writer, sheet_name="Catchment Analysis", index=False)
        hotspots.to_excel(writer, sheet_name="Hotspots", index=False)
        opportunities.to_excel(
            writer, sheet_name="Expansion Opportunities", index=False
        )

    return output_path


if __name__ == "__main__":
    print("ST-06 Geospatial Analytics Module")
    print("=" * 50)

    catchment = get_catchment_analysis()
    print(f"\nCatchment Analysis: {len(catchment)} branches")
    if not catchment.empty:
        print(
            catchment[
                ["branch_name", "patients_in_catchment", "total_revenue_in_catchment"]
            ].to_string(index=False)
        )
