# ST-06 Geospatial Analytics - Specification & Implementation Plan

> **Status**: ✅ COMPLETE (v1.0.5) - This document provides comprehensive specs and documents the existing implementation

**Goal:** Convert raw patient addresses into geographic intelligence for catchment analysis, cannibalization detection, and expansion whitespace identification.

**Architecture:** PostgreSQL + PostGIS for spatial data storage and queries. Python modules handle geocoding (Azure Maps API + Nominatim fallback), DBSCAN clustering, cannibalization analysis, and Folium map generation. Materialized views cache results for Power BI dashboards.

**Tech Stack:** 
- PostgreSQL 12+ with PostGIS 3.6+
- Python 3.10+ (pandas, scikit-learn, folium, requests)
- Azure Maps API (primary geocoder)
- Nominatim (fallback geocoder)
- pgAgent for job scheduling

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Database Schema](#database-schema)
4. [Python Modules Specification](#python-modules-specification)
5. [SQL Files Specification](#sql-files-specification)
6. [Interactive Maps Specification](#interactive-maps-specification)
7. [API & Configuration](#api--configuration)
8. [Data Flow Diagrams](#data-flow-diagrams)
9. [Implementation Details](#implementation-details)
10. [Testing Specification](#testing-specification)
11. [Scheduling & Automation](#scheduling--automation)
12. [Troubleshooting Guide](#troubleshooting-guide)
13. [Future Enhancement Opportunities](#future-enhancement-opportunities)

---

## Executive Summary

### Business Value

ST-06 transforms patient addresses into actionable geographic intelligence:

| Capability | Business Impact |
|------------|-----------------|
| **Catchment Analysis** | Understand patient origin by distance bands (<2km, 2-5km, 5-10km, 10-20km, 20km+) |
| **Cannibalization Detection** | Identify branch pairs sharing patients with severity classification |
| **Whitespace Identification** | Score expansion sites by patient density and distance from existing branches |
| **Patient Clustering** | DBSCAN clustering reveals demand concentration areas |
| **Interactive Visualization** | 7 HTML maps for strategic planning |

### Key Metrics

- **Patients Geocoded**: Incremental from `dk.patient` table
- **Branches**: Active branches from `dk.branch_master`
- **Distance Bands**: 5 bands with configurable catchment radius (default: 10km)
- **Cannibalization Severity**: None (<0.10), Low (0.10-0.25), Moderate (0.25-0.50), Severe (≥0.50)
- **Whitespace Priority**: High (SPS >100), Medium (50-100), Low (<50)

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ST-06 Geospatial Analytics                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        SQL Layer (PostgreSQL)                        │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  PostGIS Extension                                                   │   │
│  │  ├── 7 Core Tables                                                   │   │
│  │  ├── 7 Analytical Views                                              │   │
│  │  ├── 6 Materialized Views                                           │   │
│  │  └── 3 pgAgent Jobs                                                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     Python Layer (Analytics)                         │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  branch_geocoding.py  →  geocoding_pipeline.py  →  geo_analysis.py  │   │
│  │         │                        │                       │           │   │
│  │         ▼                        ▼                       ▼           │   │
│  │  Azure Maps API          Azure Maps +             DBSCAN           │   │
│  │  → branch_master         Nominatim                 Clustering       │   │
│  │                           fallback →                                    │   │
│  │                           patient_geocode                              │   │
│  │                                              ▼                       │   │
│  │                                      7 Interactive HTML Maps           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     Power BI / Visualization                         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Dependencies

```
01_postgis_setup.sql
       │
       ├──→ 02_branch_geocoding_tables.sql
       │
       └──→ 03_analytical_views.sql
                    │
                    └──→ 04_materialized_views.sql
                                │
                                └──→ 05_scheduling.sql

Python Dependencies:
    branch_geocoding.py (standalone)
    geocoding_pipeline.py (standalone)
    load_postcode_data.py (standalone)
    geo_analysis.py (depends on tables from SQL scripts)
```

---

## Database Schema

### Core Tables (7 Tables)

#### 1. `dk.branch_master`
**Purpose**: Branch locations with geocodes and catchment configuration.

| Column | Type | Description |
|--------|------|-------------|
| `branch_id` | SERIAL PK | Auto-increment primary key |
| `branch_code` | VARCHAR(50) UNIQUE | Branch identifier (e.g., "B001") |
| `branch_name` | VARCHAR(200) | Full branch name |
| `entity` | VARCHAR(100) | Business entity |
| `address_line1` | TEXT | Street address |
| `address_line2` | TEXT | Additional address info |
| `city` | VARCHAR(100) | City name |
| `state` | VARCHAR(100) | State name |
| `postcode` | VARCHAR(20) | Postal code |
| `country` | VARCHAR(50) | Country (default: 'Malaysia') |
| `branch_lat` | NUMERIC(10,7) | Latitude coordinate |
| `branch_lng` | NUMERIC(10,7) | Longitude coordinate |
| `geo_point` | GEOMETRY(Point, 4326) | PostGIS geometry (auto-generated) |
| `is_active` | BOOLEAN | Active branch flag (default: TRUE) |
| `opened_date` | DATE | Branch opening date |
| `branch_type` | VARCHAR(50) | Type (default: 'Clinic') |
| `catchment_radius_km` | NUMERIC(5,2) | Catchment radius (default: 10.0) |
| `geocode_source` | VARCHAR(50) | Geocoding source (azure_maps/nominatim) |
| `geocode_timestamp` | TIMESTAMPTZ | When geocoded |

**Triggers**:
- `trg_branch_geo`: Auto-updates `geo_point` when `branch_lat`/`branch_lng` change

**Indexes**:
- `idx_branch_geo`: GIST spatial index on `geo_point`

#### 2. `dk.patient_geocode`
**Purpose**: Patient geocoding cache with quality tracking.

| Column | Type | Description |
|--------|------|-------------|
| `mrn` | VARCHAR(50) | Patient MRN (PK part 1) |
| `location` | VARCHAR(50) | Patient location (PK part 2) |
| `full_address` | TEXT | Full geocoded address |
| `zip` | VARCHAR(20) | Postal code |
| `city_name` | VARCHAR(100) | City name |
| `state_name` | VARCHAR(100) | State name |
| `country_name` | VARCHAR(50) | Country |
| `patient_lat` | NUMERIC(10,7) | Latitude |
| `patient_lng` | NUMERIC(10,7) | Longitude |
| `geo_point` | GEOMETRY(Point, 4326) | PostGIS geometry (auto-generated) |
| `geocode_source` | VARCHAR(50) | Source (azure_maps/nominatim) |
| `geocode_quality` | VARCHAR(20) | Quality level (exact/street/city/state/zip/failed) |
| `geocode_at` | TIMESTAMPTZ | Geocoding timestamp |

**Primary Key**: `(mrn, location)`

**Quality Levels**:
- `exact`: Full address matched with high confidence
- `street`: Street + city level
- `city`: City + state level
- `state`: State only
- `zip`: Postcode only
- `failed`: Unable to geocode

**Triggers**:
- `trg_patient_geo`: Auto-updates `geo_point`

**Indexes**:
- `idx_patient_geo`: GIST spatial index
- `idx_patient_geocode_mrn_loc`: Unique composite for CONCURRENTLY refresh
- `idx_patient_geocode_zip`: Index on postal code

#### 3. `dk.my_postcode_ref`
**Purpose**: Malaysia postcode reference with coordinates.

| Column | Type | Description |
|--------|------|-------------|
| `postcode` | VARCHAR(10) PK | Postal code |
| `state` | VARCHAR(100) | State name |
| `city` | VARCHAR(100) | City name |
| `lat` | NUMERIC(10,7) | Latitude |
| `lng` | NUMERIC(10,7) | Longitude |
| `geo_point` | GEOMETRY(Point, 4326) | Generated column |

**Data Source**: GeoNames `allCountries.zip` (tab-separated, Malaysia filtered)
**Expected Records**: ~2,757 postcodes

#### 4. `dk.patient_branch_distance`
**Purpose**: Pre-computed patient-branch distance matrix.

| Column | Type | Description |
|--------|------|-------------|
| `mrn` | VARCHAR(50) | Patient MRN (PK part 1) |
| `patient_location` | VARCHAR(50) | Patient location (PK part 2) |
| `branch_code` | VARCHAR(50) | Branch code (PK part 3) |
| `distance_km` | NUMERIC(10,3) | Haversine distance in km |
| `distance_band` | VARCHAR(30) | Band (<2km/2-5km/5-10km/10-20km/20km+) |
| `est_drive_min` | NUMERIC(8,1) | Estimated drive time (minutes) |
| `is_nearest_branch` | BOOLEAN | Is this the nearest branch? |
| `is_within_catchment` | BOOLEAN | Within catchment radius? |
| `route_line` | GEOMETRY(LineString, 4326) | Line geometry for visualization |
| `computed_at` | TIMESTAMPTZ | Calculation timestamp |

**Primary Key**: `(mrn, patient_location, branch_code)`

**Populated By**: `dk.calculate_patient_branch_distances()` function

**Indexes**:
- `idx_pbd_mrn`: Patient lookup
- `idx_pbd_branch`: Branch lookup
- `idx_pbd_near`: Filter for nearest branch
- `idx_pbd_geo`: GIST index on route_line

#### 5. `dk.patient_geo_clusters`
**Purpose**: DBSCAN clustering results.

| Column | Type | Description |
|--------|------|-------------|
| `cluster_id` | INT PK | Cluster identifier (-1 = noise) |
| `cluster_label` | VARCHAR(100) | Display label (e.g., "Cluster-1") |
| `centroid_lat` | NUMERIC(10,7) | Cluster centroid latitude |
| `centroid_lng` | NUMERIC(10,7) | Cluster centroid longitude |
| `centroid_point` | GEOMETRY(Point, 4326) | Generated geometry |
| `patient_count` | INT | Number of patients in cluster |
| `cluster_radius_km` | NUMERIC(8,3) | 90th percentile radius |
| `dominant_state` | VARCHAR(100) | Most common state |
| `dominant_city` | VARCHAR(100) | Most common city |
| `dominant_zip` | VARCHAR(20) | Most common postcode |
| `total_revenue` | NUMERIC(14,2) | Total patient revenue |
| `avg_revenue_per_patient` | NUMERIC(10,2) | Average revenue |
| `nearest_branch` | VARCHAR(50) | Nearest branch code |
| `distance_to_nearest_branch_km` | NUMERIC(8,3) | Distance to nearest branch |
| `is_underserved` | BOOLEAN | Distance > 10km from branch |
| `computed_at` | TIMESTAMPTZ | Calculation timestamp |

**DBSCAN Parameters**:
- `eps_km`: 5.0 (configurable)
- `min_samples`: 5 (configurable)

#### 6. `dk.branch_overlap_analysis`
**Purpose**: Branch cannibalization metrics.

| Column | Type | Description |
|--------|------|-------------|
| `analysis_id` | SERIAL PK | Auto-increment ID |
| `branch_a` | VARCHAR(50) FK | First branch code |
| `branch_b` | VARCHAR(50) FK | Second branch code |
| `branch_distance_km` | NUMERIC(8,3) | Inter-branch distance |
| `shared_patient_count` | INT | Patients visiting both |
| `shared_patient_pct_of_a` | NUMERIC(5,2) | % of A's patients shared |
| `shared_patient_pct_of_b` | NUMERIC(5,2) | % of B's patients shared |
| `shared_revenue_total` | NUMERIC(14,2) | Total shared revenue |
| `cannibalization_index` | NUMERIC(5,3) | 0-1 index |
| `cannibalization_severity` | VARCHAR(20) | None/Low/Moderate/Severe |
| `computed_at` | TIMESTAMPTZ | Calculation timestamp |

**Cannibalization Index Formula**:
```
index = (pct_of_a + pct_of_b) / 200
```

**Severity Thresholds**:
- None: index < 0.10
- Low: 0.10 ≤ index < 0.25
- Moderate: 0.25 ≤ index < 0.50
- Severe: index ≥ 0.50

**Constraints**:
- Only pairs with inter-branch distance ≤ 50km

#### 7. `dk.geocode_execution_log`
**Purpose**: Batch pipeline run tracking.

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | SERIAL PK | Run identifier |
| `run_type` | VARCHAR(50) | full/incremental/retry/test |
| `status` | VARCHAR(20) | running/completed/failed/cancelled |
| `started_at` | TIMESTAMPTZ | Start time |
| `completed_at` | TIMESTAMPTZ | End time |
| `duration_seconds` | INT | Total duration |
| `records_total` | INT | Total records to process |
| `records_processed` | INT | Actually processed |
| `records_succeeded` | INT | Successful geocodes |
| `records_failed` | INT | Failed geocodes |
| `records_skipped` | INT | Skipped records |
| `source_table` | VARCHAR(100) | Source table name |
| `geocode_provider` | VARCHAR(50) | azure_maps+nominatim |
| `batch_size` | INT | Batch size used |
| `rate_limit_delay_ms` | INT | Delay between batches |
| `error_message` | TEXT | Error if failed |

### Analytical Views (7 Views)

| View Name | Purpose | Key Metrics |
|-----------|---------|-------------|
| `vw_patient_geo_enriched` | Patient + geocode + distance | Demographics, nearest branch, lifetime revenue |
| `vw_branch_patient_summary` | Branch-level metrics | Primary patients, distance distribution, revenue |
| `vw_new_patient_growth_geo` | New patient acquisition | First visit date, cohort month, distance band |
| `vw_catchment_analysis` | Distance band analysis | Patient count, revenue by band, demographics |
| `vw_cannibalization_detail` | Detailed branch pairs | Per-patient multi-branch visits |
| `vw_cannibalization_summary` | Aggregated cannibalization | Severity, alert status, shared metrics |
| `vw_whitespace_opportunity` | Expansion sites | Priority score, estimated annual market |

### Materialized Views (6 MVWs)

| MVW Name | Refresh Schedule | Unique Key |
|----------|------------------|------------|
| `mvw_patient_geo_enriched` | Daily 3:30 AM | mrn |
| `mvw_branch_patient_summary` | Daily 3:30 AM | branch_code |
| `mvw_catchment_analysis` | Daily 3:30 AM | Composite (branch, band, demographics) |
| `mvw_cannibalization_summary` | Daily 3:30 AM | (branch_a, branch_b) |
| `mvw_patient_geo_clusters` | Daily 3:30 AM | cluster_id |
| `mvw_whitespace_opportunity` | Daily 3:30 AM | cluster_id |

**Refresh Function**: `dk.refresh_geo_mvws()` - refreshes all 6 MVWs concurrently

---

## Python Modules Specification

### Module: `branch_geocoding.py`

**Purpose**: Geocode branch addresses using Azure Maps API with Nominatim fallback.

**Location**: `ST-06/python/branch_geocoding.py`

**Class**: `BranchGeocoder`

**Key Methods**:

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `geocode_with_azure_maps(address)` | Address string | `{lat, lng, formatted_address, source, score}` | Azure Maps geocoding |
| `geocode_with_nominatim(address)` | Address string | `{lat, lng, formatted_address, source}` | Nominatim fallback |
| `geocode(address)` | Address string | Result dict or None | Try Azure, fallback to Nominatim |
| `load_branches_from_csv(path)` | CSV path | DataFrame | Load branch addresses |
| `build_address_string(row)` | DataFrame row | String | Build full address from components |
| `update_branch_coordinates(...)` | branch_code, lat, lng | Boolean | Update `dk.branch_master` |
| `log_geocode_execution(...)` | Execution details | Boolean | Log to `dk.branch_geocode_log` |
| `geocode_branches(csv_path)` | CSV path | Stats dict | Full geocoding pipeline |

**CSV Format** (`branch_address.csv`):
```csv
branch_name,address,city,state,zip
Klinik Dr Ko Ampang,"73, Jalan Memanda 1",Ampang,Selangor,68000
```

**Usage**:
```bash
# Run with default CSV (project_root/branch_address.csv)
python branch_geocoding.py

# Custom CSV
python branch_geocoding.py --csv path/to/branches.csv

# Dry run (no DB update)
python branch_geocoding.py --no-update

# Run tests
python branch_geocoding.py --test
```

**Authentication**: Azure Maps Shared Key (subscription-key as query parameter)

---

### Module: `geocoding_pipeline.py`

**Purpose**: Main patient geocoding pipeline with four-level fallback strategy.

**Location**: `ST-06/python/geocoding_pipeline.py`

**Class**: `PatientGeocodingPipeline`

**Four-Level Fallback Strategy**:

| Level | Address Components | Quality Override |
|-------|-------------------|------------------|
| 1 | street + city + state + zip | Determined by API response |
| 2 | street + city | Determined by API response |
| 3 | city + state | Forced to `city` |
| 4 | zip only | Forced to `zip` |

**Key Methods**:

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `geocode_with_azure_maps(address)` | Address string | Result dict or None | Azure Maps geocoding |
| `geocode_with_nominatim(address)` | Address string | Result dict or None | Nominatim with 1s rate limit |
| `geocode_with_fallback(street, city, state, zip)` | Address components | Result dict or None | 4-level fallback |
| `load_patients_for_geocoding(limit, offset)` | Pagination params | DataFrame | Load non-geocoded patients |
| `store_geocode_result(mrn, location, result)` | Patient ID + result | Boolean | Store in `dk.patient_geocode` |
| `create_execution_run(run_type)` | Type string | run_id | Create log entry |
| `log_execution(run_id, status, ...)` | Execution details | Boolean | Update log entry |
| `geocode_patients(limit, update_db, log_errors)` | Control params | Stats dict | Full pipeline execution |

**Rate Limiting**:
- Azure Maps: 5,000 transactions/day (free tier)
- Nominatim: 1 request/second (strict)

**Coordinate Validation**:
- Latitude: 0.5° to 7.5° (Malaysia bounds)
- Longitude: 99.0° to 120.0° (Malaysia bounds)

**Usage**:
```bash
# Run incremental geocoding (skips already geocoded)
python geocoding_pipeline.py

# Limit for testing
python geocoding_pipeline.py --limit 50

# Custom batch size and delay
python geocoding_pipeline.py --batch-size 50 --delay 10

# Dry run (no DB writes)
python geocoding_pipeline.py --no-update

# Run tests
python geocoding_pipeline.py --test
```

---

### Module: `geo_analysis.py`

**Purpose**: DBSCAN clustering, cannibalization detection, whitespace scoring, and map generation.

**Location**: `ST-06/python/geo_analysis.py`

**Class**: `GeoAnalyzer`

**Configuration Constants**:

```python
DEFAULT_EPS_KM = 5.0          # DBSCAN cluster radius
DEFAULT_MIN_SAMPLES = 5       # Minimum patients per cluster
EARTH_RADIUS_KM = 6371.0
KM_PER_DEGREE = 111.32
MAX_CANNIBALIZATION_DISTANCE_KM = 50.0

CANNIBAL_THRESHOLDS = {
    "None": 0.10,
    "Low": 0.25,
    "Moderate": 0.50,
    "Severe": 1.01
}
```

**Key Methods**:

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `run_dbscan_clustering()` | None | (patients_df, clusters_df) | DBSCAN with haversine metric |
| `run_cannibalization_analysis()` | None | overlap_df | Branch pair overlap analysis |
| `analyze_whitespace()` | None | whitespace_df | Top 15 expansion sites |
| `build_patient_origin_map(patients_df)` | DataFrame | HTML path | Map 1: Distance bands |
| `build_branch_catchments_map(branches_df, catchment_df)` | DataFrames | HTML path | Map 2: Catchment circles |
| `build_cluster_map(patients_df, clusters_df)` | DataFrames | HTML path | Map 3: DBSCAN clusters |
| `build_cannibalization_network_map(overlap_df, branches_df)` | DataFrames | HTML path | Map 4: Branch network |
| `build_whitespace_opportunity_map(whitespace_df)` | DataFrame | HTML path | Map 5: Expansion bubbles |
| `build_revenue_heatmap(patients_df)` | DataFrame | HTML path | Map 6: Revenue density |
| `build_new_patient_flow_map(patients_df)` | DataFrame | HTML path | Map 7: Acquisition flow |
| `run_full_analysis()` | None | Results dict | Complete pipeline |
| `generate_all_maps(...)` | All DataFrames | Dict of paths | Generate all 7 maps |

**Whitespace Scoring Formula**:
```
site_priority_score = (patient_count * avg_revenue_per_patient) / distance_to_nearest_branch
```

**Priority Tiers**:
- High: SPS > 100
- Medium: 50 ≤ SPS ≤ 100
- Low: SPS < 50

**Usage**:
```bash
# Run full analysis + generate all maps
python geo_analysis.py

# Generate maps only
python geo_analysis.py --maps

# Run clustering only
python geo_analysis.py --cluster

# Run cannibalization only
python geo_analysis.py --cannibalization

# Custom DBSCAN parameters
python geo_analysis.py --eps-km 3 --min-samples 10

# Run tests
python geo_analysis.py --test
```

**Prerequisite**: Run `SELECT dk.calculate_patient_branch_distances()` before generating Maps 1, 2, 4.

---

### Module: `load_postcode_data.py`

**Purpose**: Load Malaysia postcode reference data from GeoNames.

**Location**: `ST-06/python/load_postcode_data.py`

**Data Source**: `https://download.geonames.org/export/dump/allCountries.zip`

**Process**:
1. Download `allCountries.zip` from GeoNames
2. Extract and parse tab-separated file
3. Filter for Malaysia (country code 'MY')
4. Extract postcode, city, state, lat, lng
5. Insert into `dk.my_postcode_ref`

**Expected Output**: ~2,757 postcodes loaded

**Usage**:
```bash
python load_postcode_data.py
```

---

## SQL Files Specification

### File: `01_postgis_setup.sql`

**Purpose**: Enable PostGIS extension and create core geospatial tables.

**Components**:
1. Enable extensions: `postgis`, `postgis_topology`, `fuzzystrmatch`, `pg_trgm`
2. Create `dk.branch_master` table with geometry column
3. Create `dk.patient_geocode` table with geometry column
4. Create `dk.my_postcode_ref` table with generated geometry
5. Create `dk.patient_branch_distance` table
6. Create `dk.patient_geo_clusters` table
7. Create `dk.branch_overlap_analysis` table
8. Create `dk.geocode_execution_log` table
9. Create triggers for auto-updating geometry columns
10. Create GIST spatial indexes
11. Create initial views: `vw_geocode_quality_summary`, `vw_geocode_execution_status`, `vw_patient_geo_enriched`

**Execution Order**: First (no dependencies)

---

### File: `02_branch_geocoding_tables.sql`

**Purpose**: Add geocoding columns to `branch_master` and create branch geocode log.

**Components**:
1. Add `lat`, `lng`, `geocoded_address`, `geocode_source`, `geocode_timestamp` to `dk.branch_master`
2. Create `dk.branch_geocode_log` table for per-address logging
3. Create `dk.vw_geocode_stats` view for geocoding statistics

**Execution Order**: After `01_postgis_setup.sql`

---

### File: `03_analytical_views.sql`

**Purpose**: Create distance matrix calculation function and 7 analytical views.

**Key Function**: `dk.calculate_patient_branch_distances()`

**Process**:
1. Truncate `dk.patient_branch_distance`
2. Cross-join all patients with all active branches
3. Calculate Haversine distance for each pair
4. Assign distance bands
5. Estimate drive time (road distance ≈ 1.3× straight-line / 30 km/h)
6. Flag nearest branch using `DENSE_RANK()`
7. Flag within catchment
8. Generate line geometry for visualization

**Views Created**:
- `vw_patient_nearest_branch`
- `vw_branch_catchment_summary`
- `vw_distance_band_analysis`
- `vw_patient_multiple_branches`
- `vw_catchment_overlap`
- `vw_patient_geo_enriched` (replaced)
- `vw_branch_patient_summary`
- `vw_new_patient_growth_geo`
- `vw_catchment_analysis`
- `vw_cannibalization_detail`
- `vw_cannibalization_summary`
- `vw_whitespace_opportunity`

**Execution Order**: After `01_postgis_setup.sql` and `02_branch_geocoding_tables.sql`

---

### File: `04_materialized_views.sql`

**Purpose**: Create 6 materialized views for caching and `refresh_geo_mvws()` function.

**MVWs Created**:
1. `mvw_patient_geo_enriched`
2. `mvw_branch_patient_summary`
3. `mvw_catchment_analysis`
4. `mvw_cannibalization_summary`
5. `mvw_patient_geo_clusters`
6. `mvw_whitespace_opportunity`

**Refresh Function**: `dk.refresh_geo_mvws()`
- Refreshes all 6 MVWs in dependency order
- Uses `CONCURRENTLY` where supported
- Returns table with status per MVW

**Execution Order**: After `03_analytical_views.sql`

---

### File: `05_scheduling.sql`

**Purpose**: Create pgAgent jobs for automated scheduling.

**Jobs Created**:

| Job Name | Schedule | Purpose |
|----------|----------|---------|
| ST-06 Daily Geocoding | Daily 00:00 | Incremental patient geocoding |
| ST-06 Daily Geo Analysis | Daily 03:30 | Clustering, cannibalization, whitespace |
| ST-06 Weekly Full Refresh | Sunday 03:00 | Full MVW refresh |

**Helper Functions**:
- `dk.log_geo_job_execution(job_name, status, message)`
- `dk.run_geo_incremental_geocoding()`
- `dk.run_geo_full_analysis()`
- `dk.create_geocoding_batch_file()`
- `dk.create_geo_analysis_batch_file()`
- `dk.trigger_geocoding()`
- `dk.trigger_geo_analysis()`
- `dk.trigger_geo_mvw_refresh()`
- `dk.check_geo_job_failures()`

**Monitoring Views**:
- `dk.vw_geo_job_status`
- `dk.vw_geo_job_history`

**Configuration Variables**:
- `geo.python_path`
- `geo.project_root`
- `geo.pipeline_path`
- `geo.analysis_path`
- `geo.log_dir`
- `geo.scripts_dir`

**Execution Order**: Last (after all other SQL files)

---

## Interactive Maps Specification

### Map 1: Patient Origin by Distance Band

**File**: `ST-06/maps/map_01_patient_origin.html`

**Purpose**: Visualize patient distribution colored by distance to nearest branch.

**Data Required**: `dk.patient_branch_distance` table populated

**Features**:
- Circle markers for patients (sample up to 3,000 per band)
- Color-coded by distance band:
  - `<2km`: #1a9850 (green)
  - `2-5km`: #91cf60 (light green)
  - `5-10km`: #d9ef8b (yellow-green)
  - `10-20km`: #fee08b (yellow)
  - `20km+`: #d73027 (red)
- MarkerCluster for performance
- Popup with patient details (MRN, city, distance, revenue)
- Fullscreen, MiniMap, Measure controls
- Custom legend

**Dependencies**: Requires `patient_branch_distance` table

---

### Map 2: Branch Catchment Areas

**File**: `ST-06/maps/map_02_branch_catchments.html`

**Purpose**: Visualize branch catchment circles with radius.

**Features**:
- Circle markers for branches with catchment radius (default 10km)
- Red fill with 20% opacity
- Hospital icon markers
- Popup with branch details
- Fullscreen, MiniMap, Measure controls

**Dependencies**: Requires `patient_branch_distance` table

---

### Map 3: Patient Clusters (DBSCAN)

**File**: `ST-06/maps/map_03_patient_clusters.html`

**Purpose**: Visualize DBSCAN clustering results with underserved flag.

**Features**:
- Circle markers for cluster centroids
- Size scaled by patient count
- Color-coded:
  - Underserved clusters: Red
  - Served clusters: Color palette rotation
  - Noise (cluster_id = -1): Grey
- Popup with cluster details (patient count, revenue, distance)
- Sample of patient dots (up to 10,000)
- MarkerCluster for performance

**Dependencies**: Requires `patient_geo_clusters` table (from DBSCAN)

---

### Map 4: Cannibalization Network

**File**: `ST-06/maps/map_04_cannibalization_network.html`

**Purpose**: Visualize branch cannibalization relationships.

**Features**:
- Branch markers with hospital icon
- PolyLines connecting branches with Moderate/Severe cannibalization
- Line color by severity:
  - Severe: #E63946 (red), weight 6
  - Moderate: #F4A261 (orange), weight 4
- Popup with shared patients, revenue, severity
- Skips None/Low severity for clarity

**Dependencies**: Requires `branch_overlap_analysis` table with 2+ branches

---

### Map 5: Whitespace Expansion Opportunities

**File**: `ST-06/maps/map_05_whitespace_opportunity.html`

**Purpose**: Visualize top 15 expansion site opportunities.

**Features**:
- Circle markers for expansion sites
- Size scaled by patient count
- Color-coded by priority:
  - High: #52B788 (green)
  - Medium: #FFB703 (yellow)
  - Low: #2D6A9F (blue)
- Popup with site details (patients, revenue, priority score, est. market)
- Only clusters with ≥50 patients

**Dependencies**: Requires DBSCAN clusters

---

### Map 6: Revenue Concentration Heatmap

**File**: `ST-06/maps/map_06_revenue_heatmap.html`

**Purpose**: Visualize revenue density heatmap.

**Features**:
- Dark matter tile layer
- HeatMap plugin with revenue-weighted intensity
- Gradient: Blue → Cyan → Green → Yellow → Red
- Sample up to 5,000 patients with revenue
- Revenue normalized for visualization

**Dependencies**: Requires geocoded patients with revenue data

---

### Map 7: New Patient Acquisition Flow

**File**: `ST-06/maps/map_07_new_patient_flow.html`

**Purpose**: Visualize patient acquisition over time (simulated).

**Features**:
- Patient dots grouped by time period (quarter or revenue quintile)
- Color palette rotation for periods
- Layer control to toggle periods
- MarkerCluster for performance
- Popup with patient details

**Dependencies**: Requires geocoded patients

---

## API & Configuration

### Environment Variables

```bash
# Database Connection
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password

# Azure Maps API (Shared Key auth)
AZURE_MAPS_CLIENT_ID=your_azure_maps_client_id
AZURE_MAPS_PRIMARY_KEY=your_azure_maps_primary_key
AZURE_MAPS_TIMEOUT=30

# Nominatim (fallback)
NOMINATIM_USER_AGENT=healthcare_bi_geocoder/1.0
NOMINATIM_TIMEOUT=30

# Geocoding Settings
GEOCODE_BATCH_SIZE=100
GEOCODE_DELAY_MS=1000
CATCHMENT_RADIUS_KM=10
```

### Azure Maps Authentication

**Method**: Shared Key (subscription-key as query parameter)

**API Endpoint**: `https://atlas.microsoft.com/search/address/json`

**Parameters**:
- `api-version`: 1.0
- `query`: `{address}, Malaysia`
- `limit`: 1
- `countrySet`: MY
- `subscription-key`: `{AZURE_MAPS_PRIMARY_KEY}`

**Rate Limits**: 5,000 transactions/day (free tier)

### Nominatim Fallback

**API Endpoint**: `https://nominatim.openstreetmap.org/search`

**Parameters**:
- `q`: `{address}, Malaysia`
- `format`: json
- `limit`: 1
- `countrycodes`: my

**Rate Limits**: 1 request/second (strict)

**Required Header**: `User-Agent: healthcare_bi_geocoder/1.0`

---

## Data Flow Diagrams

### Geocoding Pipeline Flow

```
Patient Addresses (dk.patient)
        │
        ▼
┌─────────────────────────────────┐
│  Load Non-Geocoded Patients     │
│  (LEFT JOIN patient_geocode)    │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│   4-Level Fallback Strategy     │
│  ┌─────────────────────────┐    │
│  │ Level 1: Full Address   │    │
│  │ (street+city+state+zip) │    │
│  └──────────┬──────────────┘    │
│             ▼                    │
│  ┌─────────────────────────┐    │
│  │ Level 2: Street+City    │    │
│  └──────────┬──────────────┘    │
│             ▼                    │
│  ┌─────────────────────────┐    │
│  │ Level 3: City+State     │    │
│  └──────────┬──────────────┘    │
│             ▼                    │
│  ┌─────────────────────────┐    │
│  │ Level 4: ZIP Only       │    │
│  └──────────┴──────────────┘    │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│   Try Azure Maps API            │
│   (subscription-key auth)       │
└──────────┬──────────────────────┘
           │
   Failed? ├──────────────────────┐
           │                      │
           ▼                      ▼
┌─────────────────────┐  ┌─────────────────┐
│  Nominatim Fallback │  │  Mark Failed    │
│  (1 req/sec limit)  │  │  quality=failed │
└──────────┬──────────┘  └─────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Validate Coordinates           │
│  (Malaysia bounds check)        │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Store in dk.patient_geocode    │
│  with quality level             │
└─────────────────────────────────┘
```

### Analysis Pipeline Flow

```
patient_geocode + branch_master
        │
        ▼
┌─────────────────────────────────┐
│  Calculate Distance Matrix      │
│  (Haversine formula)            │
│  → patient_branch_distance      │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  DBSCAN Clustering              │
│  (scikit-learn, haversine)      │
│  → patient_geo_clusters         │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Cannibalization Analysis       │
│  (shared patients, index)       │
│  → branch_overlap_analysis      │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Whitespace Scoring             │
│  (priority formula)             │
│  → Top 15 sites                 │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Generate 7 Interactive Maps    │
│  (Folium HTML)                  │
│  → ST-06/maps/*.html            │
└─────────────────────────────────┘
```

---

## Implementation Details

### DBSCAN Clustering Algorithm

**Library**: scikit-learn

**Metric**: Haversine (great-circle distance)

**Parameters**:
- `eps`: `eps_km / EARTH_RADIUS_KM` (converted to radians)
- `min_samples`: 5 (configurable)
- `algorithm`: ball_tree

**Process**:
1. Convert coordinates to radians
2. Fit DBSCAN model
3. Assign cluster labels (-1 = noise)
4. Calculate centroid (mean lat/lng)
5. Calculate cluster radius (90th percentile distance to centroid)
6. Identify dominant location (mode of state/city/zip)
7. Flag underserved (distance to nearest branch > 10km)

### Cannibalization Index Calculation

**Formula**:
```python
pct_a = len(shared_patients) / len(branch_a_patients) * 100
pct_b = len(shared_patients) / len(branch_b_patients) * 100
cannibalization_index = (pct_a + pct_b) / 200
```

**Constraints**:
- Only branch pairs with inter-branch distance ≤ 50km
- Requires transaction data with branch names matching `branch_master.city`

### Whitespace Scoring Algorithm

**Formula**:
```python
site_priority_score = (
    patient_count 
    * avg_revenue_per_patient 
    / max(distance_to_nearest_branch_km, 0.1)
)
```

**Filtering**:
- Only clusters with ≥50 patients
- Top 15 sites by score

**Estimated Annual Market**:
```python
est_annual_market = patient_count * avg_revenue * 12
```

---

## Testing Specification

### Test Files

| File | Tests | Passing | Skipped |
|------|-------|---------|---------|
| `test_geocoding.py` | 17 | 14 | 3 |
| `test_geo_analysis.py` | 20 | 20 | 0 |
| **Total** | **37** | **34** | **3** |

### Test Coverage

**Geocoding Tests** (`test_geocoding.py`):
- Azure Maps authentication (Shared Key)
- Nominatim fallback behavior
- Four-level fallback strategy
- Coordinate validation (Malaysia bounds)
- Quality level determination
- Incremental geocoding (skip already geocoded)
- Batch processing with rate limiting
- Error handling and logging

**Geo Analysis Tests** (`test_geo_analysis.py`):
- DBSCAN clustering with haversine metric
- Cluster centroid calculation
- Underserved flag logic
- Cannibalization index calculation
- Severity classification
- Whitespace scoring formula
- Priority tier assignment
- Map generation (all 7 types)
- Edge cases (empty data, single branch, etc.)

### Running Tests

```bash
# Run all tests
cd ST-06/python
pytest . -v

# Run specific test file
pytest test_geocoding.py -v
pytest test_geo_analysis.py -v

# Run specific test
pytest test_geocoding.py::test_azure_auth -v
```

---

## Scheduling & Automation

### pgAgent Jobs

| Job | Schedule | Script | Function |
|-----|----------|--------|----------|
| ST-06 Daily Geocoding | Daily 00:00 | `geocoding_pipeline.py` | Incremental geocoding |
| ST-06 Daily Geo Analysis | Daily 03:30 | `geo_analysis.py --full` | Full analysis + maps |
| ST-06 Weekly Full Refresh | Sunday 03:00 | `refresh_geo_mvws()` | Refresh all MVWs |

### Manual Triggers

```sql
-- Manual geocoding
SELECT dk.trigger_geocoding();

-- Manual geo analysis
SELECT dk.trigger_geo_analysis();

-- Manual MVW refresh
SELECT * FROM dk.trigger_geo_mvw_refresh();

-- Check for failures
SELECT * FROM dk.check_geo_job_failures();
```

### Monitoring Queries

```sql
-- View job status
SELECT * FROM dk.vw_geo_job_status;

-- View job history
SELECT * FROM dk.vw_geo_job_history;

-- Check geocode quality distribution
SELECT geocode_quality, COUNT(*) 
FROM dk.patient_geocode 
GROUP BY geocode_quality;

-- Check distance band distribution
SELECT distance_band, COUNT(DISTINCT mrn) 
FROM dk.patient_branch_distance 
WHERE is_nearest_branch = TRUE
GROUP BY distance_band;
```

---

## Troubleshooting Guide

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Azure Maps 401 Unauthorized | Key sent as header instead of query param | Key must be `subscription-key` query parameter, not header |
| Nominatim rate limit | Exceeding 1 req/sec | Built-in 1s delay between requests |
| `patient_branch_distance` table empty | Distance function not run | Execute `SELECT dk.calculate_patient_branch_distances()` |
| Map 1/2/4 missing data | Distance matrix not populated | Run distance calculation first |
| Map 4 (Cannibalization) empty | <2 branches or no shared patients | Need 2+ branches with transaction data |
| No clusters found | DBSCAN parameters too strict | Lower `eps_km` to 3 or reduce `min_samples` |
| CSV column error | Missing required columns | Ensure CSV has: branch_name, address, city, state, zip |
| Postcode 404 error | GeoNames URL issue | Script uses fallback URL |
| Environment variables not loaded | System env overriding .env | Use `load_dotenv(override=True)` |
| Branch join mismatch | Branch names don't match | Cannibalization joins on `branch_master.city` |

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Verification Queries

```sql
-- Verify PostGIS
SELECT postgis_full_version();

-- Verify tables
SELECT table_name FROM information_schema.tables 
WHERE table_schema='dk' AND table_name IN (
    'branch_master', 'patient_geocode', 'my_postcode_ref',
    'patient_branch_distance', 'patient_geo_clusters', 
    'branch_overlap_analysis', 'geocode_execution_log'
);

-- Verify views
SELECT table_name FROM information_schema.views 
WHERE table_schema='dk' AND table_name LIKE 'vw_%';

-- Verify MVWs
SELECT matviewname FROM pg_matviews 
WHERE schemaname='dk';

-- Verify pgAgent jobs
SELECT jobname FROM pgagent.pga_job 
WHERE jobname LIKE 'ST-06%';

-- Verify maps (bash)
ls ST-06/maps/*.html | wc -l
-- Expected: 7
```

---

## Future Enhancement Opportunities

### 1. Real-Time Geocoding
- **Current**: Batch geocoding with manual/scheduled triggers
- **Enhancement**: Real-time geocoding on patient record creation
- **Implementation**: Database trigger calling Python geocoding service

### 2. Route Optimization
- **Current**: Straight-line (Haversine) distance
- **Enhancement**: Actual road distance via routing API
- **Implementation**: Azure Maps Route API or OSRM

### 3. Travel Time Analysis
- **Current**: Estimated drive time (distance × 1.3 / 30 km/h)
- **Enhancement**: Real traffic-aware travel time
- **Implementation**: Azure Maps Route API with traffic data

### 4. Heatmap Animation
- **Current**: Static maps
- **Enhancement**: Time-series animation of patient acquisition
- **Implementation**: Folium TimestampedGeoJson or Kepler.gl

### 5. Power BI Embedded Maps
- **Current**: Standalone HTML maps
- **Enhancement**: Embed maps in Power BI dashboards
- **Implementation**: Power BI ArcGIS Maps or custom visuals

### 6. Geofencing Alerts
- **Current**: Static catchment analysis
- **Enhancement**: Real-time alerts when patients move outside catchment
- **Implementation**: Database triggers + notification service

### 7. Competitor Analysis
- **Current**: Internal branch network only
- **Enhancement**: Include competitor locations in whitespace analysis
- **Implementation**: Additional data source + overlap analysis

### 8. Predictive Expansion
- **Current**: Historical patient clusters
- **Enhancement**: Predict future demand hotspots
- **Implementation**: Time-series forecasting + spatial interpolation

---

## Appendix: File Structure

```
ST-06/
├── sql/
│   ├── 01_postgis_setup.sql          # PostGIS + core tables (456 lines)
│   ├── 02_branch_geocoding_tables.sql # Branch geocode extensions (94 lines)
│   ├── 03_analytical_views.sql        # 7 analytical views (935 lines)
│   ├── 04_materialized_views.sql      # 6 MVWs + refresh function (465 lines)
│   └── 05_scheduling.sql              # pgAgent jobs (718 lines)
├── python/
│   ├── branch_geocoding.py            # Branch geocoder (791 lines)
│   ├── geocoding_pipeline.py          # Patient geocoder (1167 lines)
│   ├── geo_analysis.py                # Analytics + maps (1500+ lines)
│   ├── load_postcode_data.py          # Postcode loader
│   ├── test_geocoding.py              # Geocoding tests (17 tests)
│   └── test_geo_analysis.py           # Analysis tests (20 tests)
├── maps/
│   ├── map_01_patient_origin.html
│   ├── map_02_branch_catchments.html
│   ├── map_03_patient_clusters.html
│   ├── map_04_cannibalization_network.html
│   ├── map_05_whitespace_opportunity.html
│   ├── map_06_revenue_heatmap.html
│   └── map_07_new_patient_flow.html
└── ST-06_README.md                    # Documentation (708 lines)
```

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-04-04  
**Status**: Complete - No implementation plan needed unless enhancements requested