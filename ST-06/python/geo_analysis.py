"""
============================================================
HEALTHCARE GROUP — GEOSPATIAL ANALYTICS
FILE: geo_analysis.py
Purpose:
  1. DBSCAN patient clustering → dk.patient_geo_clusters
  2. Cannibalization detection → dk.branch_overlap_analysis
  3. Whitespace / expansion opportunity scoring
  4. Interactive Folium HTML maps export

Database: PostgreSQL + PostGIS | Schema: dk
Libraries: scikit-learn (DBSCAN), pandas, folium
Author  : Chief Digital Officer
============================================================
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import DatabaseManager from ST-01
import importlib.util

spec = importlib.util.spec_from_file_location(
    "database", os.path.join(project_root, "ST-01", "python", "database.py")
)
if spec is not None:
    database_module = importlib.util.module_from_spec(spec)
    sys.modules["ST_01.python.database"] = database_module
    spec.loader.exec_module(database_module)
    DatabaseManager = database_module.DatabaseManager
else:
    raise ImportError("Could not load database module")

# ML and visualization libraries
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from scipy.spatial.distance import cdist
import folium
from folium.plugins import MarkerCluster, HeatMap, MeasureControl, MiniMap, Fullscreen

import warnings

warnings.filterwarnings("ignore")

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class GeoAnalyzer:
    """
    Geospatial analytics for healthcare BI.

    Features:
    - DBSCAN clustering for patient demand analysis
    - Cannibalization detection between branches
    - Whitespace site scoring for expansion planning
    - Interactive Folium map generation
    """

    # Configuration defaults
    DEFAULT_EPS_KM = 5.0  # DBSCAN cluster radius in km
    DEFAULT_MIN_SAMPLES = 5  # Minimum patients per cluster
    EARTH_RADIUS_KM = 6371.0
    KM_PER_DEGREE = 111.32  # Approximate km per degree at equator

    # Cannibalization thresholds (per plan spec: None<0.1, Low[0.1-0.25), Moderate[0.25-0.5), Severe>=0.5)
    CANNIBAL_THRESHOLDS = {
        "None": 0.10,
        "Low": 0.25,
        "Moderate": 0.50,
        "Severe": 1.01,
    }

    # Maximum distance for cannibalization consideration (km)
    MAX_CANNIBALIZATION_DISTANCE_KM = 50.0

    # Brand colors for visualization
    BRAND_COLORS = {
        "primary": "#2D6A9F",
        "accent": "#F4A261",
        "green": "#52B788",
        "red": "#E63946",
        "yellow": "#FFB703",
        "dark": "#1D3557",
        "purple": "#9B5DE5",
        "teal": "#2EC4B6",
    }

    DIST_BAND_COLORS = {
        "<2km": "#1a9850",
        "2-5km": "#91cf60",
        "5-10km": "#d9ef8b",
        "10-20km": "#fee08b",
        "20km+": "#d73027",
    }

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        eps_km: float = DEFAULT_EPS_KM,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ):
        """
        Initialize the geo analyzer.

        Args:
            db_manager: DatabaseManager instance
            eps_km: DBSCAN eps parameter in kilometers (default: 5km)
            min_samples: DBSCAN min_samples parameter (default: 5)
        """
        # Set database manager, use singleton instance if none provided
        if db_manager is not None:
            self.db_manager = db_manager
        else:
            # Try to get instance, instantiate if none exists
            try:
                self.db_manager = DatabaseManager.get_instance()
            except AttributeError:
                # Fall back to creating new instance
                self.db_manager = DatabaseManager()

        self.eps_km = eps_km
        self.min_samples = min_samples

        # Convert eps from km to degrees for coordinate-based clustering
        self.eps_deg = eps_km / self.KM_PER_DEGREE

        # Malaysia map center
        self.my_lat = 3.9
        self.my_lng = 108.5

        # Output directories
        self.maps_dir = os.path.join(project_root, "ST-06", "maps")
        os.makedirs(self.maps_dir, exist_ok=True)

    def _execute_query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """Execute SQL query and return DataFrame."""
        return self.db_manager.execute_query(query, params=params)

    def _execute_sql(self, query: str, params: Optional[Dict] = None) -> None:
        """Execute SQL statement without returning results."""
        self.db_manager.execute_query(query, params=params, return_df=False)

    def _write_table(
        self, df: pd.DataFrame, table_name: str, if_exists: str = "replace"
    ) -> None:
        """Write DataFrame to database table."""
        if df.empty:
            logger.info(f"  ⚠ Skipping write for {table_name} - empty dataframe")
            return

        try:
            df.to_sql(
                table_name,
                self.db_manager.engine,
                schema="dk",
                if_exists=if_exists,
                index=False,
                chunksize=500,
            )
            logger.info(f"  ✓ Written {len(df):,} rows → dk.{table_name}")
        except Exception as e:
            logger.error(f"Failed to write table {table_name}: {e}")
            raise

    def run_dbscan_clustering(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Run DBSCAN clustering on geocoded patients.

        Uses scikit-learn DBSCAN with haversine metric for geographic clustering.

        Returns:
            Tuple of (patient_assignments_df, cluster_summary_df)
        """
        logger.info("=" * 60)
        logger.info("STEP 1: DBSCAN Patient Clustering")
        logger.info("=" * 60)
        logger.info(f"  Using eps_km={self.eps_km}, min_samples={self.min_samples}")
        logger.info(f"  eps_degrees={self.eps_deg:.6f}")

        # Load geocoded patients with nearest branch info
        query = f"""
            SELECT
                pg.mrn,
                pg.patient_lat,
                pg.patient_lng,
                pg.city_name,
                pg.state_name,
                pg.zip,
                pbd.branch_code AS nearest_branch,
                pbd.distance_km AS dist_to_nearest,
                pbd.distance_band,
                COALESCE(txn.lifetime_revenue, 0) AS lifetime_revenue
            FROM dk.patient_geocode pg
            LEFT JOIN dk.patient_branch_distance pbd
                ON pg.mrn = pbd.mrn AND pbd.is_nearest_branch = TRUE
            LEFT JOIN (
                SELECT mrn, SUM(standalone_and_package_sales_rm) AS lifetime_revenue
                FROM dk.collection_report
                WHERE status NOT ILIKE '%void%'
                GROUP BY mrn
            ) txn ON pg.mrn = txn.mrn
            WHERE pg.patient_lat IS NOT NULL
              AND pg.patient_lng IS NOT NULL
              AND pg.geocode_quality != 'failed'
        """

        patients = self._execute_query(query)

        if len(patients) < self.min_samples:
            logger.warning(
                f"  Too few geocoded patients ({len(patients)}) for clustering (min={self.min_samples})"
            )
            return pd.DataFrame(), pd.DataFrame()

        logger.info(f"  Clustering {len(patients):,} geocoded patients...")

        # Convert coordinates to radians for haversine metric
        coords_rad = np.radians(patients[["patient_lat", "patient_lng"]].values)
        eps_rad = self.eps_km / self.EARTH_RADIUS_KM

        # Run DBSCAN with haversine metric
        db = DBSCAN(
            eps=eps_rad,
            min_samples=self.min_samples,
            algorithm="ball_tree",
            metric="haversine",
        )
        labels = db.fit_predict(coords_rad)

        patients["cluster_id"] = labels

        # Build cluster summary
        cluster_rows = []
        for cid in sorted(patients["cluster_id"].unique()):
            subset = patients[patients["cluster_id"] == cid]

            # Calculate centroid (mean lat/lng)
            centroid_lat = subset["patient_lat"].mean()
            centroid_lng = subset["patient_lng"].mean()

            # Calculate cluster radius (90th percentile of distances to centroid)
            dists_to_centroid = []
            for _, row in subset.iterrows():
                d_lat = np.radians(row.patient_lat - centroid_lat)
                d_lng = np.radians(row.patient_lng - centroid_lng)
                a = (
                    np.sin(d_lat / 2) ** 2
                    + np.cos(np.radians(row.patient_lat))
                    * np.cos(np.radians(centroid_lat))
                    * np.sin(d_lng / 2) ** 2
                )
                c = 2 * np.arcsin(np.sqrt(a))
                dists_to_centroid.append(self.EARTH_RADIUS_KM * c)
            radius_km = (
                float(np.percentile(dists_to_centroid, 90))
                if dists_to_centroid
                else 0.0
            )

            # Dominant location - add defensive checks
            dom_state = (
                str(subset["state_name"].mode().iloc[0])
                if len(subset["state_name"]) > 0
                and not subset["state_name"].mode().empty
                else ""
            )
            dom_city = (
                str(subset["city_name"].mode().iloc[0])
                if len(subset["city_name"]) > 0 and not subset["city_name"].mode().empty
                else ""
            )
            dom_zip = (
                str(subset["zip"].mode().iloc[0])
                if len(subset["zip"]) > 0 and not subset["zip"].mode().empty
                else ""
            )
            near_br = (
                str(subset["nearest_branch"].mode().iloc[0])
                if len(subset["nearest_branch"]) > 0
                and not subset["nearest_branch"].mode().empty
                else ""
            )
            # Calculate average distance with null check
            dist_series = subset["dist_to_nearest"]
            dist_mean = dist_series.mean() if dist_series.dropna().size > 0 else None

            # Flag underserved clusters (distance to nearest branch > 10km)
            is_underserved = bool(dist_mean > 10.0) if dist_mean is not None else False

            cluster_rows.append(
                {
                    "cluster_id": int(cid),
                    "cluster_label": f"Cluster-{cid}" if cid >= 0 else "Noise",
                    "centroid_lat": round(centroid_lat, 6),
                    "centroid_lng": round(centroid_lng, 6),
                    "patient_count": len(subset),
                    "cluster_radius_km": round(radius_km, 3),
                    "dominant_state": dom_state,
                    "dominant_city": dom_city,
                    "dominant_zip": dom_zip,
                    "total_revenue": round(float(subset["lifetime_revenue"].sum()), 2),
                    "avg_revenue_per_patient": round(
                        float(subset["lifetime_revenue"].mean()), 2
                    ),
                    "nearest_branch": near_br,
                    "distance_to_nearest_branch_km": round(dist_mean, 3)
                    if dist_mean is not None
                    else None,
                    "is_underserved": is_underserved,
                    "computed_at": datetime.now(),
                }
            )

        # Create cluster DataFrame from the rows collected
        cluster_df = pd.DataFrame(cluster_rows) if cluster_rows else pd.DataFrame()

        # Handle case where there are no clusters but we want empty DataFrame with proper structure
        if cluster_df.empty and cluster_rows:
            cluster_df = pd.DataFrame(columns=list(cluster_rows[0].keys()))

        # Store results in database
        self._write_table(cluster_df, "patient_geo_clusters", if_exists="replace")

        # Log summary
        n_clusters = int((labels >= 0).sum())
        n_noise = int((labels == -1).sum())
        n_underserved = (
            int(cluster_df["is_underserved"].sum()) if not cluster_df.empty else 0
        )

        logger.info(f"  ✓ Clustering complete:")
        logger.info(f"    - Total clusters: {len(cluster_rows) - 1} (excluding noise)")
        logger.info(f"    - Noise points: {n_noise}")
        logger.info(f"    - Underserved clusters: {n_underserved}")

        return patients, cluster_df

    def run_cannibalization_analysis(self) -> pd.DataFrame:
        """
        Detect branch cannibalization based on shared patients.

        Returns:
            DataFrame with branch pair analysis
        """
        logger.info("=" * 60)
        logger.info("STEP 2: Cannibalization Detection")
        logger.info("=" * 60)

        # Load active branches
        branches = self._execute_query("""
            SELECT branch_code, branch_lat, branch_lng, catchment_radius_km
            FROM dk.branch_master
            WHERE is_active = TRUE AND branch_lat IS NOT NULL
        """)

        if len(branches) < 2:
            logger.warning("  Need at least 2 branches for cannibalization analysis")
            return pd.DataFrame()

        # Load transactions per patient per branch
        txns = self._execute_query("""
            SELECT cr.mrn, bm.branch_code AS branch,
                   COUNT(DISTINCT cr.sale_order_no) AS visit_count,
                   SUM(cr.standalone_and_package_sales_rm) AS revenue
            FROM dk.collection_report cr
            JOIN dk.branch_master bm ON LOWER(TRIM(cr.branch)) = LOWER(TRIM(bm.city))
            WHERE cr.status NOT ILIKE '%void%'
            GROUP BY cr.mrn, bm.branch_code
        """)

        # Build branch patient sets
        branch_patients = {}
        for _, br in branches.iterrows():
            branch_patients[br["branch_code"]] = set(
                txns[txns["branch"] == br["branch_code"]]["mrn"]
            )

        # Analyze branch pairs
        overlap_rows = []
        branch_list = branches["branch_code"].tolist()

        for i, ba in enumerate(branch_list):
            for j, bb in enumerate(branch_list):
                if j <= i:
                    continue

                set_a = branch_patients.get(ba, set())
                set_b = branch_patients.get(bb, set())
                shared = set_a & set_b

                if not set_a or not set_b:
                    continue

                # Inter-branch distance (Haversine)
                br_a = branches[branches["branch_code"] == ba].iloc[0]
                br_b = branches[branches["branch_code"] == bb].iloc[0]

                lat1, lon1 = (
                    np.radians(br_a["branch_lat"]),
                    np.radians(br_a["branch_lng"]),
                )
                lat2, lon2 = (
                    np.radians(br_b["branch_lat"]),
                    np.radians(br_b["branch_lng"]),
                )
                dlat, dlon = lat2 - lat1, lon2 - lon1
                a = (
                    np.sin(dlat / 2) ** 2
                    + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
                )
                inter_km = float(self.EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a)))

                # MUST NOT: Skip branch pairs with distance > 50km (unlikely real cannibalization)
                if inter_km > self.MAX_CANNIBALIZATION_DISTANCE_KM:
                    logger.debug(
                        f"  {ba} ↔ {bb}: Skipping (distance={inter_km:.1f}km > 50km)"
                    )
                    continue

                # Shared revenue
                shared_rev = float(txns[txns["mrn"].isin(shared)]["revenue"].sum() or 0)

                # Cannibalization index
                pct_a = len(shared) / len(set_a) * 100 if set_a else 0
                pct_b = len(shared) / len(set_b) * 100 if set_b else 0
                cannibal_idx = round((pct_a + pct_b) / 200, 3)

                # Severity classification
                sev = "None"
                for label, threshold in self.CANNIBAL_THRESHOLDS.items():
                    if cannibal_idx < threshold:
                        sev = label
                        break

                overlap_rows.append(
                    {
                        "branch_a": ba,
                        "branch_b": bb,
                        "branch_distance_km": round(inter_km, 3),
                        "shared_patient_count": len(shared),
                        "shared_patient_pct_of_a": round(pct_a, 2),
                        "shared_patient_pct_of_b": round(pct_b, 2),
                        "shared_revenue_total": round(shared_rev, 2),
                        "cannibalization_index": cannibal_idx,
                        "cannibalization_severity": sev,
                        "computed_at": datetime.now(),
                    }
                )

                logger.info(
                    f"  {ba} ↔ {bb}: {len(shared)} shared | idx={cannibal_idx:.3f} [{sev}]"
                )

        if overlap_rows:
            overlap_df = pd.DataFrame(overlap_rows)
            self._write_table(
                overlap_df, "branch_overlap_analysis", if_exists="replace"
            )

            severe_count = len(
                overlap_df[
                    overlap_df["cannibalization_severity"].isin(["Moderate", "Severe"])
                ]
            )
            if severe_count > 0:
                logger.warning(
                    f"  ⚠ {severe_count} pairs with MODERATE/SEVERE cannibalization!"
                )

            return overlap_df

        return pd.DataFrame()

    def analyze_whitespace(self) -> pd.DataFrame:
        """
        Score whitespace expansion opportunities.

        Site Priority Score = cluster_patient_count * avg_revenue / distance_to_nearest_branch

        Priority Tiers (per plan spec):
        - High: SPS > 100
        - Medium: 50 <= SPS <= 100
        - Low: SPS < 50

        Returns:
            DataFrame with top 15 expansion site rankings
        """
        logger.info("=" * 60)
        logger.info("STEP 3: Whitespace Site Scoring")
        logger.info("=" * 60)

        # Load cluster data
        clusters = self._execute_query("""
            SELECT * FROM dk.patient_geo_clusters
            WHERE cluster_id >= 0
        """)

        if clusters.empty:
            logger.warning("  No clusters found for whitespace analysis")
            return pd.DataFrame()

        # MUST NOT: Skip sites with <50 patients (not viable for expansion)
        clusters = clusters[clusters["patient_count"] >= 50].copy()

        if clusters.empty:
            logger.warning("  No clusters with >=50 patients found")
            return pd.DataFrame()

        # Calculate site priority score
        # Formula: SPS = (cluster_patient_count * avg_revenue) / distance_to_nearest_branch
        clusters["distance_to_nearest_branch_km"] = clusters[
            "distance_to_nearest_branch_km"
        ].fillna(999)

        # Avoid division by zero with small epsilon
        clusters["site_priority_score"] = (
            clusters["patient_count"]
            * clusters["avg_revenue_per_patient"]
            / clusters["distance_to_nearest_branch_km"].clip(lower=0.1)
        )

        # Assign priority tiers based on SPS score (per plan spec)
        # High: SPS > 100, Medium: 50-100, Low: <50
        def assign_priority_tier(sps):
            if sps > 100:
                return "High"
            elif sps >= 50:
                return "Medium"
            else:
                return "Low"

        clusters["expansion_priority"] = clusters["site_priority_score"].apply(
            assign_priority_tier
        )

        # Estimate annual market (assuming 12 visits/year * avg transaction value)
        clusters["est_annual_market_rm"] = (
            clusters["patient_count"] * clusters["avg_revenue_per_patient"] * 12
        )

        # Rank by site priority score and select top 15 expansion sites
        clusters = clusters.sort_values("site_priority_score", ascending=False)
        top_15_sites = clusters.head(15).copy()

        logger.info(f"  ✓ Analyzed {len(clusters)} clusters (>=50 patients)")
        logger.info(f"  ✓ Ranked top {len(top_15_sites)} expansion sites")

        # Log priority tier distribution
        tier_counts = top_15_sites["expansion_priority"].value_counts()
        for tier in ["High", "Medium", "Low"]:
            count = tier_counts.get(tier, 0)
            logger.info(f"    - {tier} priority: {count} sites")

        if not top_15_sites.empty:
            top_site = top_15_sites.iloc[0]
            logger.info(
                f"  Top site: {top_site['dominant_city']}, {top_site['dominant_state']}"
            )
            logger.info(f"    - Patients: {top_site['patient_count']:,}")
            logger.info(
                f"    - Site Priority Score: {top_site['site_priority_score']:.0f}"
            )
            logger.info(f"    - Priority Tier: {top_site['expansion_priority']}")
            logger.info(
                f"    - Est. Annual Market: RM {top_site['est_annual_market_rm']:,.0f}"
            )

        return top_15_sites

    def build_patient_origin_map(self, patients_df: pd.DataFrame) -> str:
        """
        Map 1: Patient dots colored by distance band.

        Args:
            patients_df: Patient data with distance bands

        Returns:
            Path to saved HTML map
        """
        logger.info("=" * 60)
        logger.info("MAP 1: Patient Origin by Distance Band")
        logger.info("=" * 60)

        if patients_df.empty or "distance_band" not in patients_df.columns:
            logger.warning("  No distance band data for patient origin map")
            return ""

        # Create map centered on Malaysia
        m = folium.Map(
            location=[self.my_lat, self.my_lng], zoom_start=6, tiles="CartoDB positron"
        )

        # Add patient dots colored by distance band
        for band, color in self.DIST_BAND_COLORS.items():
            band_patients = patients_df[patients_df["distance_band"] == band]
            if band_patients.empty:
                continue

            sample_size = min(3000, len(band_patients))
            sample = band_patients.sample(n=sample_size, random_state=42)

            mc = MarkerCluster(name=f"Distance: {band}")
            for _, pt in sample.iterrows():
                folium.CircleMarker(
                    location=[pt["patient_lat"], pt["patient_lng"]],
                    radius=3,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.6,
                    popup=folium.Popup(
                        f"<b>Patient: {pt['mrn']}</b><br>"
                        f"📍 {pt.get('city_name', 'N/A')}, {pt.get('state_name', 'N/A')}<br>"
                        f"📏 Distance Band: {band}<br>"
                        f"🏥 Nearest Branch: {pt.get('nearest_branch', 'N/A')}<br>"
                        f"💰 Lifetime Revenue: RM {pt.get('lifetime_revenue', 0):,.0f}",
                        max_width=250,
                    ),
                    tooltip=f"{band} - {pt.get('mrn', 'Patient')}",
                ).add_to(mc)
            mc.add_to(m)

        # Add controls
        Fullscreen().add_to(m)
        MiniMap().add_to(m)
        MeasureControl().add_to(m)

        # Legend
        legend_html = f"""
        <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:white;padding:10px;border:2px solid grey;
                    border-radius:6px;font-size:12px">
        <b>Patient Distance Bands</b><br>
        """
        for band, color in self.DIST_BAND_COLORS.items():
            legend_html += f'<span style="color:{color}">●</span> {band}<br>'
        legend_html += """</div>"""
        m.get_root().html.add_child(folium.Element(legend_html))

        map_path = os.path.join(self.maps_dir, "map_01_patient_origin.html")
        m.save(map_path)
        logger.info(f"  ✓ Map saved: {map_path}")
        return map_path

    def build_branch_catchments_map(
        self, branches_df: pd.DataFrame, catchment_summary_df: pd.DataFrame
    ) -> str:
        """
        Map 2: Branch circles with catchment radius.

        Args:
            branches_df: Branch master data with coordinates
            catchment_summary_df: Patient counts by distance band per branch

        Returns:
            Path to saved HTML map
        """
        logger.info("=" * 60)
        logger.info("MAP 2: Branch Catchment Areas")
        logger.info("=" * 60)

        if branches_df.empty:
            logger.warning("  No branch data for catchment map")
            return ""

        # Create map centered on Malaysia
        m = folium.Map(
            location=[self.my_lat, self.my_lng], zoom_start=6, tiles="CartoDB positron"
        )

        for _, branch in branches_df.iterrows():
            radius_km = float(branch.get("catchment_radius_km", 5.0))

            folium.Circle(
                location=[branch["branch_lat"], branch["branch_lng"]],
                radius=int(radius_km * 1000),  # Convert to meters
                color=self.BRAND_COLORS["red"],
                fill=True,
                fill_color=self.BRAND_COLORS["red"],
                fill_opacity=0.2,
                popup=folium.Popup(
                    f"<b>{branch['branch_code']}</b><br>"
                    f"📍 Catchment Radius: {radius_km:.1f} km<br>"
                    f"👥 Total Patients: {catchment_summary_df[catchment_summary_df['branch_code'] == branch['branch_code']]['total_patients'].sum() if not catchment_summary_df.empty else 'N/A'}",
                    max_width=250,
                ),
            ).add_to(m)

            # Branch marker
            folium.Marker(
                location=[branch["branch_lat"], branch["branch_lng"]],
                icon=folium.Icon(color="red", icon="hospital", prefix="fa"),
                popup=f"<b>{branch['branch_code']}</b>",
            ).add_to(m)

        # Add controls
        Fullscreen().add_to(m)
        MiniMap().add_to(m)
        MeasureControl().add_to(m)

        # Legend
        legend_html = f"""
        <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:white;padding:10px;border:2px solid grey;
                    border-radius:6px;font-size:12px">
        <b>Branch Catchment</b><br>
        <span style="color:{self.BRAND_COLORS["red"]}">●</span> Branch Location<br>
        <span style="color:{self.BRAND_COLORS["red"]};opacity:0.3">●</span> Catchment Radius
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        map_path = os.path.join(self.maps_dir, "map_02_branch_catchments.html")
        m.save(map_path)
        logger.info(f"  ✓ Map saved: {map_path}")
        return map_path

    def build_cluster_map(
        self, patients_df: pd.DataFrame, clusters_df: pd.DataFrame
    ) -> str:
        """
        Map 3: Interactive Folium map showing patient clusters with DBSCAN centroids.

        Args:
            patients_df: Patient assignments with cluster_id
            clusters_df: Cluster summary with centroids

        Returns:
            Path to saved HTML map
        """
        logger.info("=" * 60)
        logger.info("MAP 3: Patient Clusters (DBSCAN)")
        logger.info("=" * 60)

        if patients_df.empty or clusters_df.empty:
            logger.warning("  No data for cluster map")
            return ""

        # Create map centered on Malaysia
        m = folium.Map(
            location=[self.my_lat, self.my_lng], zoom_start=6, tiles="CartoDB positron"
        )

        # Color palette for clusters
        cluster_colors = [
            "#2D6A9F",
            "#E63946",
            "#52B788",
            "#F4A261",
            "#9B5DE5",
            "#2EC4B6",
            "#FFB703",
            "#D62828",
            "#0077B6",
            "#FCBF49",
        ]

        # Add cluster centroids
        for idx, (_, cluster) in enumerate(
            clusters_df[clusters_df["cluster_id"] >= 0].iterrows()
        ):
            color = (
                self.BRAND_COLORS["red"]
                if cluster["is_underserved"]
                else cluster_colors[idx % len(cluster_colors)]
            )

            folium.CircleMarker(
                location=[cluster["centroid_lat"], cluster["centroid_lng"]],
                radius=8 + min(12, cluster["patient_count"] / 50),
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                popup=folium.Popup(
                    f"<b>{cluster['cluster_label']}</b><br>"
                    f"📍 {cluster['dominant_city']}, {cluster['dominant_state']}<br>"
                    f"👥 Patients: {cluster['patient_count']:,}<br>"
                    f"💰 Avg Revenue: RM {cluster['avg_revenue_per_patient']:,.0f}<br>"
                    f"📏 Distance to branch: {cluster['distance_to_nearest_branch_km']:.1f} km<br>"
                    if cluster["distance_to_nearest_branch_km"] is not None
                    else f"📏 Distance to branch: N/A<br>"
                    f"⚠️ Underserved: {'Yes' if cluster['is_underserved'] else 'No'}",
                    max_width=250,
                ),
                tooltip=f"{cluster['cluster_label']} - {cluster['patient_count']} patients",
            ).add_to(m)

        # Add patient dots (sample for performance)
        sample_size = min(10000, len(patients_df))
        patient_sample = patients_df.sample(n=sample_size, random_state=42)

        mc = MarkerCluster(name="Patients")
        for _, pt in patient_sample.iterrows():
            if pt["cluster_id"] == -1:
                color = "#888888"  # Grey for noise
            else:
                color = cluster_colors[pt["cluster_id"] % len(cluster_colors)]

            folium.CircleMarker(
                location=[pt["patient_lat"], pt["patient_lng"]],
                radius=2,
                color=color,
                fill=True,
                fill_opacity=0.5,
            ).add_to(mc)
        mc.add_to(m)

        # Add map controls
        Fullscreen().add_to(m)
        MiniMap().add_to(m)
        MeasureControl().add_to(m)

        # Legend
        legend_html = f"""
        <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:white;padding:10px;border:2px solid grey;
                    border-radius:6px;font-size:12px">
        <b>Patient Clusters</b><br>
        <span style="color:{self.BRAND_COLORS["green"]}">●</span> Served Cluster<br>
        <span style="color:{self.BRAND_COLORS["red"]}">●</span> Underserved Cluster<br>
        <span style="color:#888888">●</span> Noise (unclustered)
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        # Save map
        map_path = os.path.join(self.maps_dir, "map_03_patient_clusters.html")
        m.save(map_path)
        logger.info(f"  ✓ Map saved: {map_path}")

        return map_path

    def build_cannibalization_network_map(
        self, overlap_df: pd.DataFrame, branches_df: pd.DataFrame
    ) -> str:
        """
        Map 4: Branch network diagram showing cannibalization relationships.

        Args:
            overlap_df: Branch overlap analysis data
            branches_df: Branch master data

        Returns:
            Path to saved HTML map
        """
        logger.info("=" * 60)
        logger.info("MAP 4: Cannibalization Network")
        logger.info("=" * 60)

        if overlap_df.empty:
            logger.warning("  No overlap data for network map")
            return ""

        # Create map centered on Malaysia
        m = folium.Map(
            location=[self.my_lat, self.my_lng], zoom_start=6, tiles="CartoDB positron"
        )

        # Severity colors
        severity_colors = {
            "None": "#888888",
            "Low": "#FFB703",
            "Moderate": "#F4A261",
            "Severe": "#E63946",
        }

        # Add branches as markers
        for _, branch in branches_df.iterrows():
            folium.Marker(
                location=[branch["branch_lat"], branch["branch_lng"]],
                icon=folium.Icon(color="red", icon="hospital", prefix="fa"),
                popup=f"<b>{branch['branch_code']}</b>",
            ).add_to(m)

        # Add network lines for severe/moderate cannibalization
        for _, overlap in overlap_df.iterrows():
            if overlap["cannibalization_severity"] in ["None", "Low"]:
                continue  # Skip low severity for clarity

            br_a = branches_df[branches_df["branch_code"] == overlap["branch_a"]].iloc[
                0
            ]
            br_b = branches_df[branches_df["branch_code"] == overlap["branch_b"]].iloc[
                0
            ]

            line_color = severity_colors.get(
                overlap["cannibalization_severity"], "#888888"
            )
            line_weight = {
                "Severe": 6,
                "Moderate": 4,
                "Low": 2,
                "None": 1,
            }.get(overlap["cannibalization_severity"], 2)

            # Draw line between branches
            folium.PolyLine(
                locations=[
                    [br_a["branch_lat"], br_a["branch_lng"]],
                    [br_b["branch_lat"], br_b["branch_lng"]],
                ],
                color=line_color,
                weight=line_weight,
                opacity=0.7,
                popup=folium.Popup(
                    f"<b>{overlap['branch_a']} ↔ {overlap['branch_b']}</b><br>"
                    f"📏 Distance: {overlap['branch_distance_km']:.1f} km<br>"
                    f"👥 Shared Patients: {overlap['shared_patient_count']}<br>"
                    f"💰 Shared Revenue: RM {overlap['shared_revenue_total']:,.0f}<br>"
                    f"⚠️ Severity: {overlap['cannibalization_severity']}",
                    max_width=250,
                ),
            ).add_to(m)

        # Add controls
        Fullscreen().add_to(m)
        MiniMap().add_to(m)
        MeasureControl().add_to(m)

        # Legend
        legend_html = f"""
        <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:white;padding:10px;border:2px solid grey;
                    border-radius:6px;font-size:12px">
        <b>Cannibalization Severity</b><br>
        <span style="color:#E63946">─</span> Severe (≥0.50)<br>
        <span style="color:#F4A261">─</span> Moderate (0.25-0.50)<br>
        <span style="color:#FFB703">─</span> Low (0.10-0.25)<br>
        <span style="color:#E63946">📍</span> Branch
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        map_path = os.path.join(self.maps_dir, "map_04_cannibalization_network.html")
        m.save(map_path)
        logger.info(f"  ✓ Map saved: {map_path}")
        return map_path

    def build_whitespace_opportunity_map(self, whitespace_df: pd.DataFrame) -> str:
        """
        Map 5: Expansion site bubbles showing whitespace opportunities.

        Args:
            whitespace_df: Whitespace analysis results with priority scores

        Returns:
            Path to saved HTML map
        """
        logger.info("=" * 60)
        logger.info("MAP 5: Whitespace Expansion Opportunities")
        logger.info("=" * 60)

        if whitespace_df.empty:
            logger.warning("  No whitespace data for opportunity map")
            return ""

        # Create map centered on Malaysia
        m = folium.Map(
            location=[self.my_lat, self.my_lng], zoom_start=6, tiles="CartoDB positron"
        )

        # Priority colors
        priority_colors = {
            "High": self.BRAND_COLORS["green"],
            "Medium": self.BRAND_COLORS["yellow"],
            "Low": self.BRAND_COLORS["primary"],
        }

        for _, site in whitespace_df.iterrows():
            color = priority_colors.get(
                site["expansion_priority"], self.BRAND_COLORS["primary"]
            )
            radius = 10 + min(20, site["patient_count"] / 20)  # Scale by patient count

            folium.CircleMarker(
                location=[site["centroid_lat"], site["centroid_lng"]],
                radius=radius,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.6,
                popup=folium.Popup(
                    f"<b>{site['dominant_city']}, {site['dominant_state']}</b><br>"
                    f"📍 {site['cluster_label']}<br>"
                    f"👥 Patients: {site['patient_count']:,}<br>"
                    f"💰 Avg Revenue: RM {site['avg_revenue_per_patient']:,.0f}<br>"
                    f"📊 Priority Score: {site['site_priority_score']:.0f}<br>"
                    f"🏆 Tier: {site['expansion_priority']}<br>"
                    f"💵 Est. Annual Market: RM {site['est_annual_market_rm']:,.0f}",
                    max_width=280,
                ),
                tooltip=f"{site['dominant_city']} - {site['expansion_priority']}",
            ).add_to(m)

        # Add controls
        Fullscreen().add_to(m)
        MiniMap().add_to(m)
        MeasureControl().add_to(m)

        # Legend
        legend_html = f"""
        <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:white;padding:10px;border:2px solid grey;
                    border-radius:6px;font-size:12px">
        <b>Expansion Priority</b><br>
        <span style="color:{self.BRAND_COLORS["green"]}">●</span> High (SPS >100)<br>
        <span style="color:{self.BRAND_COLORS["yellow"]}">●</span> Medium (SPS 50-100)<br>
        <span style="color:{self.BRAND_COLORS["primary"]}">●</span> Low (SPS <50)
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        map_path = os.path.join(self.maps_dir, "map_05_whitespace_opportunity.html")
        m.save(map_path)
        logger.info(f"  ✓ Map saved: {map_path}")
        return map_path

    def build_revenue_heatmap(self, patients_df: pd.DataFrame) -> str:
        """
        Map 6: Revenue concentration heatmap.

        Args:
            patients_df: Patient data with lifetime_revenue

        Returns:
            Path to saved HTML map
        """
        logger.info("=" * 60)
        logger.info("MAP 6: Revenue Concentration Heatmap")
        logger.info("=" * 60)

        if patients_df.empty or "lifetime_revenue" not in patients_df.columns:
            logger.warning("  No revenue data for heatmap")
            return ""

        # Filter to patients with revenue
        revenue_patients = patients_df[
            (patients_df["patient_lat"].notna())
            & (patients_df["patient_lng"].notna())
            & (patients_df["lifetime_revenue"] > 0)
        ].copy()

        if revenue_patients.empty:
            logger.warning("  No valid revenue data points")
            return ""

        # Create map centered on Malaysia
        m = folium.Map(
            location=[self.my_lat, self.my_lng],
            zoom_start=6,
            tiles="CartoDB dark_matter",
        )

        # Prepare heatmap data - weight by revenue
        # Normalize revenue for better visualization
        max_revenue = revenue_patients["lifetime_revenue"].max()
        if max_revenue > 0:
            revenue_patients["weight"] = (
                revenue_patients["lifetime_revenue"] / max_revenue
            )
        else:
            revenue_patients["weight"] = 1.0

        # Sample if too many points
        sample_size = min(5000, len(revenue_patients))
        sample = revenue_patients.sample(n=sample_size, random_state=42)

        heat_data = [
            [row["patient_lat"], row["patient_lng"], float(row["weight"])]
            for _, row in sample.iterrows()
        ]

        HeatMap(
            heat_data,
            radius=15,
            blur=20,
            max_zoom=1,
            gradient={
                0.0: "#000080",
                0.2: "#0000FF",
                0.4: "#00FFFF",
                0.6: "#00FF00",
                0.8: "#FFFF00",
                1.0: "#FF0000",
            },
            min_opacity=0.5,
        ).add_to(m)

        # Add controls
        Fullscreen().add_to(m)
        MiniMap().add_to(m)
        MeasureControl().add_to(m)

        # Legend
        legend_html = f"""
        <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:white;padding:10px;border:2px solid grey;
                    border-radius:6px;font-size:12px">
        <b>Revenue Density</b><br>
        <span style="color:#FF0000">●</span> High<br>
        <span style="color:#FFFF00">●</span> Medium<br>
        <span style="color:#00FFFF">●</span> Low<br>
        <span style="color:#0000FF">●</span> Very Low
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        map_path = os.path.join(self.maps_dir, "map_06_revenue_heatmap.html")
        m.save(map_path)
        logger.info(f"  ✓ Map saved: {map_path}")
        return map_path

    def build_new_patient_flow_map(self, patients_df: pd.DataFrame) -> str:
        """
        Map 7: New patient acquisition flow (simulated animation).

        Args:
            patients_df: Patient data with transaction dates

        Returns:
            Path to saved HTML map
        """
        logger.info("=" * 60)
        logger.info("MAP 7: New Patient Acquisition Flow")
        logger.info("=" * 60)

        if patients_df.empty:
            logger.warning("  No patient data for flow map")
            return ""

        # Create map centered on Malaysia
        m = folium.Map(
            location=[self.my_lat, self.my_lng], zoom_start=6, tiles="CartoDB positron"
        )

        # Color scheme for flow visualization
        flow_colors = ["#1a9850", "#91cf60", "#d9ef8b", "#fee08b", "#fc8d59", "#d73027"]

        # Group patients by time period (simulated quarters if no date info)
        if "first_visit_date" in patients_df.columns:
            patients_df["first_visit_date"] = pd.to_datetime(
                patients_df["first_visit_date"]
            )
            time_groups = patients_df.groupby(
                patients_df["first_visit_date"].dt.to_period("Q")
            )
        else:
            # Assign to simulated time periods based on revenue quintiles
            revenue = patients_df["lifetime_revenue"].clip(lower=1)
            try:
                patients_df["revenue_quintile"] = pd.qcut(
                    revenue,
                    q=5,
                    labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
                    duplicates="drop",
                )
            except ValueError:
                # All values identical — assign all to Q1
                patients_df["revenue_quintile"] = "Q1"
            time_groups = patients_df.groupby("revenue_quintile")

        # Add patient dots for each time period
        for idx, (period, group) in enumerate(time_groups):
            color = flow_colors[idx % len(flow_colors)]
            sample_size = min(2000, len(group))
            sample = group.sample(n=sample_size, random_state=42)

            mc = MarkerCluster(name=f"Period {idx + 1}")
            for _, pt in sample.iterrows():
                folium.CircleMarker(
                    location=[pt["patient_lat"], pt["patient_lng"]],
                    radius=3,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.5,
                    popup=folium.Popup(
                        f"<b>Patient: {pt['mrn']}</b><br>"
                        f"📍 {pt.get('city_name', 'N/A')}, {pt.get('state_name', 'N/A')}<br>"
                        f"📊 Revenue: RM {pt.get('lifetime_revenue', 0):,.0f}",
                        max_width=200,
                    ),
                ).add_to(mc)
            mc.add_to(m)

        # Add controls
        Fullscreen().add_to(m)
        MiniMap().add_to(m)
        MeasureControl().add_to(m)
        folium.LayerControl().add_to(m)

        # Legend
        legend_html = f"""
        <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:white;padding:10px;border:2px solid grey;
                    border-radius:6px;font-size:12px">
        <b>Patient Acquisition Flow</b><br>
        """
        for idx, color in enumerate(flow_colors[: len(time_groups)]):
            legend_html += f'<span style="color:{color}">●</span> Period {idx + 1}<br>'
        legend_html += """</div>"""
        m.get_root().html.add_child(folium.Element(legend_html))

        map_path = os.path.join(self.maps_dir, "map_07_new_patient_flow.html")
        m.save(map_path)
        logger.info(f"  ✓ Map saved: {map_path}")
        return map_path

    def run_full_analysis(self) -> Dict[str, Any]:
        """
        Run complete geospatial analysis pipeline.

        Returns:
            Dictionary with analysis results summary
        """
        logger.info("=" * 60)
        logger.info("GEOSPATIAL ANALYSIS STARTED")
        logger.info(f"Run: {datetime.now()}")
        logger.info("=" * 60)

        results = {}

        # Step 1: DBSCAN Clustering
        patients_df, clusters_df = self.run_dbscan_clustering()
        results["clustering"] = {
            "patients_analyzed": len(patients_df) if not patients_df.empty else 0,
            "clusters_found": len(clusters_df[clusters_df["cluster_id"] >= 0])
            if not clusters_df.empty
            else 0,
            "noise_points": len(patients_df[patients_df["cluster_id"] == -1])
            if not patients_df.empty
            else 0,
        }

        # Step 2: Cannibalization
        overlap_df = self.run_cannibalization_analysis()
        results["cannibalization"] = {
            "branch_pairs_analyzed": len(overlap_df),
            "severe_cases": len(
                overlap_df[overlap_df["cannibalization_severity"] == "Severe"]
            )
            if not overlap_df.empty
            else 0,
        }

        # Step 3: Whitespace
        whitespace_df = self.analyze_whitespace()
        results["whitespace"] = {
            "opportunities_found": len(whitespace_df),
            "high_priority": len(
                whitespace_df[whitespace_df["expansion_priority"] == "High"]
            )
            if not whitespace_df.empty
            else 0,
        }

        # Step 4: Generate all 7 maps
        self.generate_all_maps(
            patients_df=patients_df,
            clusters_df=clusters_df,
            overlap_df=overlap_df,
            whitespace_df=whitespace_df,
        )

        logger.info("=" * 60)
        logger.info("GEOSPATIAL ANALYSIS COMPLETE")
        logger.info("=" * 60)

        return results

    def generate_all_maps(
        self,
        patients_df: pd.DataFrame,
        clusters_df: pd.DataFrame,
        overlap_df: pd.DataFrame,
        whitespace_df: pd.DataFrame,
    ) -> Dict[str, str]:
        """
        Generate all 7 interactive Folium HTML maps.

        Args:
            patients_df: Patient data with coordinates and revenue
            clusters_df: Cluster summary data
            overlap_df: Cannibalization overlap analysis
            whitespace_df: Whitespace opportunity analysis

        Returns:
            Dictionary mapping map names to their file paths
        """
        logger.info("=" * 60)
        logger.info("GENERATING ALL 7 INTERACTIVE MAPS")
        logger.info("=" * 60)

        map_paths = {}

        # Load branch data for multiple maps
        branches_df = self._execute_query("""
            SELECT branch_code, branch_lat, branch_lng, catchment_radius_km
            FROM dk.branch_master
            WHERE is_active = TRUE AND branch_lat IS NOT NULL
        """)

        # Map 1: Patient Origin by Distance Band
        try:
            path = self.build_patient_origin_map(patients_df)
            if path:
                map_paths["map_01_patient_origin"] = path
        except Exception as e:
            logger.error(f"Failed to build map_01: {e}")

        # Map 2: Branch Catchments
        catchment_summary_df = self._execute_query("""
            SELECT branch_code, distance_band, COUNT(DISTINCT mrn) AS total_patients
            FROM dk.patient_branch_distance
            WHERE is_nearest_branch = TRUE
            GROUP BY branch_code, distance_band
        """)
        try:
            path = self.build_branch_catchments_map(branches_df, catchment_summary_df)
            if path:
                map_paths["map_02_branch_catchments"] = path
        except Exception as e:
            logger.error(f"Failed to build map_02: {e}")

        # Map 3: Patient Clusters
        try:
            path = self.build_cluster_map(patients_df, clusters_df)
            if path:
                map_paths["map_03_patient_clusters"] = path
        except Exception as e:
            logger.error(f"Failed to build map_03: {e}")

        # Map 4: Cannibalization Network
        try:
            path = self.build_cannibalization_network_map(overlap_df, branches_df)
            if path:
                map_paths["map_04_cannibalization_network"] = path
        except Exception as e:
            logger.error(f"Failed to build map_04: {e}")

        # Map 5: Whitespace Opportunities
        try:
            path = self.build_whitespace_opportunity_map(whitespace_df)
            if path:
                map_paths["map_05_whitespace_opportunity"] = path
        except Exception as e:
            logger.error(f"Failed to build map_05: {e}")

        # Map 6: Revenue Heatmap
        try:
            path = self.build_revenue_heatmap(patients_df)
            if path:
                map_paths["map_06_revenue_heatmap"] = path
        except Exception as e:
            logger.error(f"Failed to build map_06: {e}")

        # Map 7: New Patient Flow
        try:
            path = self.build_new_patient_flow_map(patients_df)
            if path:
                map_paths["map_07_new_patient_flow"] = path
        except Exception as e:
            logger.error(f"Failed to build map_07: {e}")

        logger.info(f"✓ Generated {len(map_paths)}/7 maps successfully")
        for name, path in map_paths.items():
            logger.info(f"  - {name}: {path}")

        return map_paths


def main():
    """Main entry point with command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run geospatial analytics for healthcare BI"
    )
    parser.add_argument(
        "--cluster",
        action="store_true",
        help="Run DBSCAN clustering (default action)",
    )
    parser.add_argument(
        "--cannibalization",
        action="store_true",
        help="Run cannibalization analysis only",
    )
    parser.add_argument(
        "--whitespace",
        action="store_true",
        help="Run whitespace analysis only",
    )
    parser.add_argument(
        "--eps-km",
        type=float,
        default=GeoAnalyzer.DEFAULT_EPS_KM,
        help=f"DBSCAN eps in km (default: {GeoAnalyzer.DEFAULT_EPS_KM})",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=GeoAnalyzer.DEFAULT_MIN_SAMPLES,
        help=f"DBSCAN min_samples (default: {GeoAnalyzer.DEFAULT_MIN_SAMPLES})",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full analysis (clustering + cannibalization + whitespace + maps)",
    )
    parser.add_argument(
        "--maps",
        action="store_true",
        help="Generate all 7 interactive Folium HTML maps only",
    )

    args = parser.parse_args()

    # Initialize analyzer with configurable parameters
    analyzer = GeoAnalyzer(
        eps_km=args.eps_km,
        min_samples=args.min_samples,
    )

    # Determine which analysis to run
    if args.maps:
        # Run full analysis pipeline and generate all maps
        results = analyzer.run_full_analysis()
    elif args.full:
        results = analyzer.run_full_analysis()
    elif args.cannibalization:
        analyzer.run_cannibalization_analysis()
        results = {"cannibalization": "complete"}
    elif args.whitespace:
        analyzer.analyze_whitespace()
        results = {"whitespace": "complete"}
    else:
        # Default: run clustering (task requirement)
        patients_df, clusters_df = analyzer.run_dbscan_clustering()

        # Build cluster map
        if not patients_df.empty and not clusters_df.empty:
            analyzer.build_cluster_map(patients_df, clusters_df)

        results = {
            "patients_analyzed": len(patients_df),
            "clusters_found": len(clusters_df[clusters_df["cluster_id"] >= 0]),
        }

    logger.info(f"\nResults summary: {results}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
