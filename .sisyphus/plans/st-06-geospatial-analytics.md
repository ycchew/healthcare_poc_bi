# ST-06: Geospatial Analytics

## TL;DR

> **Quick Summary**: ✅ **COMPLETE** - Comprehensive geospatial analytics for Healthcare BI using PostGIS, Azure Maps API with Nominatim fallback, DBSCAN clustering, and cannibalization analysis. Created 7 SQL views, 6 materialized views, 2 Python pipelines (geocoding + analysis), and 7 interactive Folium maps.
> 
> **Deliverables**:
> - ✅ 5 SQL files (PostGIS setup, geocoding views, analytical views, MVWs, scheduling)
> - ✅ 6 Python modules (geocoding pipeline, geo analysis, tests)
> - ✅ 7 interactive Folium HTML maps
> - ✅ pgAgent scheduling for Windows
> 
> **Estimated Effort**: Large (8-10 hours)
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: PostGIS Setup → Branch Geocoding → Patient Geocoding → Distance Matrix → DBSCAN → Cannibalization → Maps
> **Status**: All 15 tasks + Final Wave (F1-F4) COMPLETE

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle` ✅ **APPROVE**
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [15/15] | Must NOT Have [8/8] | Tasks [15/15] | VERDICT: APPROVE`

- [x] F2. **Code Quality Review** — `unspecified-high` ✅ **PASS**
  Run `tsc --noEmit` + linter + `pytest`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, print statements in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS] | Lint [PASS] | Tests [34 pass/3 skip] | Files [6 clean/0 issues] | VERDICT: PASS`

- [x] F3. **End-to-End Pipeline Test** — `unspecified-high` ✅ **PASS**
  Start from clean state. Execute geocoding pipeline on sample patients. Run DBSCAN clustering. Generate one Folium map. Verify all outputs. Test error handling with invalid addresses.
  Output: `Pipeline [PASS] | Maps [7/7] | Error Handling [PASS] | VERDICT: PASS`

- [x] F4. **Map Rendering Verification** — `unspecified-high` ✅ **PASS**
  Use Playwright to open all 7 Folium maps in browser. Verify each renders without JavaScript errors. Capture screenshots. Verify interactive elements (zoom, popups) work.
  Output: `Maps Rendered [7/7] | JS Errors [0] | Screenshots [7] | VERDICT: PASS`

---

## Commit Strategy

- **1**: `feat(st-06): Add PostGIS extension and core geospatial tables` — 01_postgis_setup.sql
- **2**: `feat(st-06): Add Malaysia postcode reference data loader` — load_postcode_data.py
- **3**: `feat(st-06): Add branch geocoding pipeline` — branch_geocoding.py
- **4**: `feat(st-06): Add patient geocoding pipeline with Azure+Nominatim fallback` — geocoding_pipeline.py
- **5**: `feat(st-06): Add patient-branch distance matrix calculation` — 03_analytical_views.sql (distance section)
- **6**: `feat(st-06): Add DBSCAN clustering for patient demand analysis` — geo_analysis.py (DBSCAN)
- **7**: `feat(st-06): Add cannibalization detection algorithm` — geo_analysis.py (cannibalization)
- **8**: `feat(st-06): Add whitespace site scoring for expansion planning` — geo_analysis.py (whitespace)
- **9**: `feat(st-06): Add 7 analytical views for Power BI` — 03_analytical_views.sql
- **10**: `feat(st-06): Add 6 materialized views with refresh function` — 04_materialized_views.sql
- **11**: `feat(st-06): Add 7 interactive Folium maps` — maps/*.html, geo_analysis.py (maps)
- **12**: `feat(st-06): Add pgAgent scheduling for geospatial pipeline` — 05_scheduling.sql
- **13**: `feat(st-06): Add comprehensive test suite` — test_*.py
- **14**: `docs(st-06): Add complete README documentation` — README.md

---

## Success Criteria

### Verification Commands
```bash
# Verify PostGIS
psql -c "SELECT postgis_full_version();"

# Verify tables
psql -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='dk' AND table_name LIKE '%geo%';"

# Run geocoding pipeline (sample)
cd ST-06/python && python geocoding_pipeline.py --sample --limit 100

# Run geo analysis
cd ST-06/python && python geo_analysis.py

# Verify MVW refresh
psql -c "SELECT dk.refresh_geo_mvws();"

# Run tests
cd ST-06/python && pytest . -v

# Check maps exist
ls ST-06/maps/*.html | wc -l  # Should be 7
```

### Final Checklist
- [x] All "Must Have" present (15 items)
- [x] All "Must NOT Have" absent (8 items)
- [x] All tests pass
- [x] All 7 maps render correctly
- [x] MVW refresh works with CONCURRENTLY
- [x] pgAgent jobs scheduled
- [x] Documentation complete in README.md

  **What to do**:
  Create 7 analytical views for Power BI:
  1. `vw_patient_geo_enriched` - Patient + geocode + distance
  2. `vw_branch_patient_summary` - Branch-level patient metrics
  3. `vw_new_patient_growth_geo` - Geographic new patient acquisition
  4. `vw_catchment_analysis` - Distance band analysis by branch
  5. `vw_cannibalization_detail` - Detailed branch pair analysis
  6. `vw_cannibalization_summary` - Aggregated cannibalization metrics
  7. `vw_whitespace_opportunity` - Expansion site recommendations

  **Must NOT do**:
  - Do NOT include patient PII (names, full addresses)
  - Do NOT create more than 7 views

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 12
  - **Blocked By**: Task 7, 8, 9, 10

  **References**:
  - `docs/source/Geospatial Strategy/geo_02_analytical_views.sql` - Reference views
  - `ST-04/sql/01_product_performance_views.sql` - Pattern for analytical views

  **Acceptance Criteria**:
  - [x] All 7 views created successfully
  - [x] Views return data without errors
  - [x] Views follow naming convention
  - [x] No PII columns exposed

  **QA Scenarios**:
  ```
  Scenario: Verify all views exist
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT table_name FROM information_schema.views WHERE table_schema='dk' AND table_name LIKE 'vw_%geo%';"
    Expected Result: 7 geospatial view names returned
    Evidence: .sisyphus/evidence/task-11-views-exist.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add 7 analytical views for Power BI`
  - Files: `ST-06/sql/03_analytical_views.sql`

---

- [x] 12. Six Materialized Views

  **What to do**:
  Create 6 materialized views with unique indexes for CONCURRENTLY refresh:
  1. `mvw_patient_geo_enriched` - Cached patient geo data
  2. `mvw_branch_patient_summary` - Cached branch metrics
  3. `mvw_catchment_analysis` - Cached catchment stats
  4. `mvw_cannibalization_summary` - Cached cannibalization
  5. `mvw_patient_geo_clusters` - Cached cluster data
  6. `mvw_whitespace_opportunity` - Cached expansion sites

  Create refresh function: `dk.refresh_geo_mvws()`

  **Must NOT do**:
  - Do NOT create MVWs without unique indexes
  - Do NOT create more than 6 MVWs

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 14
  - **Blocked By**: Task 11

  **References**:
  - `ST-05/sql/03_materialized_views.sql` - MVW patterns with indexes
  - Use `DISTINCT ON` for unique composite indexes

  **Acceptance Criteria**:
  - [x] All 6 MVWs created
  - [x] Unique indexes on each MVW
  - [x] Refresh function created
  - [x] CONCURRENTLY refresh works

  **QA Scenarios**:
  ```
  Scenario: Verify MVW refresh
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT dk.refresh_geo_mvws();"
    Expected Result: Returns success, all MVWs refreshed
    Evidence: .sisyphus/evidence/task-12-mvw-refresh.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add 6 materialized views with refresh function`
  - Files: `ST-06/sql/04_materialized_views.sql`

---

- [x] 13. Seven Interactive Folium Maps

  **What to do**:
  Create 7 interactive HTML maps using Folium:
  1. `map_01_patient_origin.html` - Patient dots colored by distance band
  2. `map_02_branch_catchments.html` - Branch circles with catchment radius
  3. `map_03_patient_clusters.html` - DBSCAN clusters with centroids
  4. `map_04_cannibalization_network.html` - Branch network diagram
  5. `map_05_whitespace_opportunity.html` - Expansion site bubbles
  6. `map_06_revenue_heatmap.html` - Revenue concentration heatmap
  7. `map_07_new_patient_flow.html` - New patient acquisition animated

  Save to `ST-06/maps/` directory

  **Must NOT do**:
  - Do NOT use static matplotlib maps (Folium only)
  - Do NOT create more than 7 maps

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 8, 10

  **References**:
  - `docs/source/Geospatial Strategy/geo_02_geo_analysis.py` - Folium map examples
  - Folium docs: https://python-visualization.github.io/folium/

  **Acceptance Criteria**:
  - [x] All 7 maps generated
  - [x] Maps render correctly in browser
  - [x] Interactive features work (zoom, popups)
  - [x] Maps saved to ST-06/maps/

  **QA Scenarios**:
  ```
  Scenario: Verify map generation
    Tool: Bash (python)
    Steps:
      1. cd ST-06/python && python geo_analysis.py --generate-maps
      2. ls -la ../maps/*.html | wc -l
    Expected Result: Returns 7 HTML files
    Evidence: .sisyphus/evidence/task-13-map-count.txt

  Scenario: Verify map renders
    Tool: Playwright
    Steps:
      1. Open ST-06/maps/map_01_patient_origin.html
      2. Wait for map tiles to load
      3. Take screenshot
    Expected Result: Map displays with patient dots and branch markers
    Evidence: .sisyphus/evidence/task-13-map-screenshot.png
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add 7 interactive Folium maps`
  - Files: `ST-06/maps/*.html`, `ST-06/python/geo_analysis.py` (map section)

---

- [x] 14. pgAgent Scheduling Setup

  **What to do**:
  - Create pgAgent jobs for Windows:
    - Daily geocoding: 00:00 AM (incremental)
    - Daily geo analysis: 03:30 AM (after ML pipeline)
    - Weekly full refresh: Sunday 03:00 AM
  - Create monitoring views and functions
  - Document job verification queries

  **Must NOT do**:
  - Do NOT use pg_cron (Windows uses pgAgent)
  - Do NOT schedule overlapping jobs

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 12

  **References**:
  - `ST-05/sql/04_scheduling.sql` - pgAgent job patterns
  - pgAgent docs: https://www.pgadmin.org/docs/pgadmin4/latest/pgagent.html

  **Acceptance Criteria**:
  - [x] pgAgent jobs created
  - [x] Jobs verified in pgagent.pga_job
  - [x] Monitoring views created
  - [x] Manual trigger functions work

  **QA Scenarios**:
  ```
  Scenario: Verify pgAgent jobs
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT jobname FROM pgagent.pga_job WHERE jobname LIKE 'ST-06%';"
    Expected Result: 3 job names returned
    Evidence: .sisyphus/evidence/task-14-pgagent-jobs.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add pgAgent scheduling for geospatial pipeline`
  - Files: `ST-06/sql/05_scheduling.sql`

---

- [x] 15. Test Suite

  **What to do**:
  - Create `test_geocoding.py` with tests:
    - Azure Maps authentication test
    - Nominatim fallback test
    - Four-level fallback test
    - Incremental geocoding test
    - Quality level assignment test
  - Create `test_geo_analysis.py` with tests:
    - DBSCAN clustering test
    - Cannibalization index test
    - Whitespace scoring test
    - Folium map generation test
  - Tests should gracefully skip if database objects missing
  - Tests should use real database (not mocks)

  **Must NOT do**:
  - Do NOT mock database calls (use real test data)
  - Do NOT skip all tests without reason

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4
  - **Blocks**: F1-F4
  - **Blocked By**: Task 6, 8, 9, 10

  **References**:
  - `ST-05/python/test_ml_pipeline.py` - Test patterns
  - `ST-05/python/test_dynamic_pricing.py` - Test patterns

  **Acceptance Criteria**:
  - [x] test_geocoding.py created with >= 5 tests
  - [x] test_geo_analysis.py created with >= 5 tests
  - [x] All tests pass
  - [x] Tests gracefully skip if objects missing

  **QA Scenarios**:
  ```
  Scenario: Run test suite
    Tool: Bash (pytest)
    Steps:
      1. cd ST-06/python && pytest . -v
    Expected Result: All tests pass or skip gracefully
    Evidence: .sisyphus/evidence/task-15-test-results.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add comprehensive test suite`
  - Files: `ST-06/python/test_geocoding.py`, `ST-06/python/test_geo_analysis.py`

---

  **What to do**:
  - Implement DBSCAN clustering in `geo_analysis.py`
  - Use scikit-learn DBSCAN with configurable eps_km (default 5km)
  - Handle noise points (cluster_id = -1)
  - Calculate cluster centroids
  - Flag underserved clusters (distance to nearest branch > 10km)
  - Store results in `dk.patient_geo_clusters`
  - Create cluster visualization

  **Must NOT do**:
  - Do NOT use fixed eps value without tuning guidance
  - Do NOT exclude noise points from analysis

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 10, 13
  - **Blocked By**: Task 7

  **References**:
  - `docs/source/Geospatial Strategy/geo_02_geo_analysis.py` - DBSCAN implementation
  - scikit-learn DBSCAN docs

  **Acceptance Criteria**:
  - [x] DBSCAN clustering runs successfully
  - [x] Clusters identified with centroids
  - [x] is_underserved flag calculated
  - [x] Noise points handled correctly

  **QA Scenarios**:
  ```
  Scenario: Verify clustering results
    Tool: Bash (python)
    Steps:
      1. python -c "from geo_analysis import GeoAnalyzer; a = GeoAnalyzer(); clusters = a.run_dbscan_clustering(); print(f'Found {len(clusters)} clusters')"
    Expected Result: Returns cluster count > 0
    Evidence: .sisyphus/evidence/task-8-dbscan-results.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add DBSCAN clustering for patient demand analysis`
  - Files: `ST-06/python/geo_analysis.py` (DBSCAN section)

---

- [x] 9. Cannibalization Detection Algorithm

  **What to do**:
  - Calculate shared patient count between all branch pairs
  - Compute cannibalization index: shared_patients / min(patients_a, patients_b)
  - Classify severity: None, Low, Moderate, Severe
  - Consider inter-branch distance in analysis
  - Store results in `dk.branch_overlap_analysis`
  - Create network diagram data

  **Must NOT do**:
  - Do NOT flag distant branches (>50km) as cannibalizing
  - Do NOT calculate index without considering distance

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 10
  - **Blocked By**: Task 5, 7

  **References**:
  - `docs/source/Geospatial Strategy/geo_01_postgis_setup.sql` - branch_overlap_analysis table

  **Acceptance Criteria**:
  - [x] Shared patient counts calculated for all pairs
  - [x] Cannibalization index computed
  - [x] Severity classification applied
  - [x] Results stored in analysis table

  **QA Scenarios**:
  ```
  Scenario: Verify cannibalization analysis
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT branch_a, branch_b, shared_patients, cannibalization_index, severity FROM dk.branch_overlap_analysis ORDER BY cannibalization_index DESC LIMIT 10;"
    Expected Result: Valid indices and severity classifications
    Evidence: .sisyphus/evidence/task-9-cannibalization.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add cannibalization detection algorithm`
  - Files: `ST-06/python/geo_analysis.py` (cannibalization section)

---

- [x] 10. Whitespace Site Scoring

  **What to do**:
  - Calculate Site Priority Score for expansion planning
  - Formula: cluster_patient_count * avg_revenue / distance_to_nearest_branch
  - Score whitespace clusters (not served by existing branch)
  - Rank top 15 expansion sites
  - Create expansion_priority tiers (High/Medium/Low)
  - Store results with cluster metadata

  **Must NOT do**:
  - Do NOT recommend sites with <50 patients
  - Do NOT exclude served clusters from analysis

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 13
  - **Blocked By**: Task 8, 9

  **References**:
  - `docs/source/Geospatial Strategy/geo_02_geo_analysis.py` - whitespace analysis

  **Acceptance Criteria**:
  - [x] Site Priority Score calculated for all clusters
  - [x] Top 15 sites identified
  - [x] Priority tiers assigned
  - [x] Revenue potential estimated

  **QA Scenarios**:
  ```
  Scenario: Verify whitespace scoring
    Tool: Bash (python)
    Steps:
      1. python -c "from geo_analysis import GeoAnalyzer; a = GeoAnalyzer(); sites = a.analyze_whitespace(); print(f'Top site: {sites.iloc[0].to_dict()}')"
    Expected Result: Returns top site with priority_score, patient_count, est_revenue
    Evidence: .sisyphus/evidence/task-10-whitespace.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add whitespace site scoring for expansion planning`
  - Files: `ST-06/python/geo_analysis.py` (whitespace section)

---

  **What to do**:
  - Create loader for user-provided branch CSV data
  - Geocode branch addresses using Azure Maps API
  - Store results in `dk.branch_master` with quality flags
  - Create fallback to Nominatim if Azure Maps fails

  **Must NOT do**:
  - Do NOT commit branch CSV to git (user provides separately)
  - Do NOT skip failed geocodes (mark quality='failed')

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 7, 9
  - **Blocked By**: Task 1

  **References**:
  - `ST-01/python/database.py` - DatabaseManager pattern
  - Azure Maps API: https://learn.microsoft.com/en-us/rest/api/maps/search/get-geocoding

  **Acceptance Criteria**:
  - [x] Branch CSV loaded successfully
  - [x] All branches geocoded with quality assessment
  - [x] Geometry points created for each branch
  - [x] Azure Maps API integration tested

  **QA Scenarios**:
  ```
  Scenario: Verify branch geocoding
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT branch_name, latitude, longitude, geocode_quality FROM dk.branch_master WHERE latitude IS NOT NULL;"
    Expected Result: All branches have lat/lng with quality='exact' or 'city'
    Evidence: .sisyphus/evidence/task-5-branch-geocode.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add branch geocoding pipeline`
  - Files: `ST-06/python/branch_geocoding.py`

---

- [x] 6. Patient Geocoding Pipeline

  **What to do**:
  - Create `geocoding_pipeline.py` with Azure Maps integration
  - Implement four-level fallback: Full → Street+City → City+State → ZIP
  - Use subscription-key authentication for Azure Maps
  - Implement Nominatim fallback for rate limits
  - Incremental geocoding (skip already geocoded patients)
  - Store quality level: exact, street, city, state, zip, failed
  - Batch processing with configurable delay

  **Must NOT do**:
  - Do NOT geocode patients with NULL/empty addresses
  - Do NOT exceed Azure Maps rate limits (no throttling bypass)
  - Do NOT store full addresses in geocode table (MRN only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 7
  - **Blocked By**: Task 2, 4

  **References**:
  - `docs/source/Geospatial Strategy/geo_01_geocoding_pipeline.py` - Reference implementation
  - Azure Maps REST API docs
  - Nominatim API docs: https://nominatim.org/release-docs/develop/api/Search/

  **Acceptance Criteria**:
  - [x] Azure Maps API authentication working
  - [x] Nominatim fallback functional
  - [x] Four-level fallback implemented
  - [x] Incremental geocoding skips existing records
  - [x] Quality levels assigned correctly
  - [x] >80% geocoding success rate

  **QA Scenarios**:
  ```
  Scenario: Test Azure Maps geocoding
    Tool: Bash (python)
    Steps:
      1. cd ST-06/python && python -c "from geocoding_pipeline import GeocodingPipeline; p = GeocodingPipeline(); print(p.test_azure_auth())"
    Expected Result: Returns True (authentication successful)
    Evidence: .sisyphus/evidence/task-6-azure-auth.txt

  Scenario: Run sample geocoding
    Tool: Bash (python)
    Steps:
      1. python geocoding_pipeline.py --sample --limit 10
    Expected Result: Geocodes 10 patients, shows quality distribution
    Evidence: .sisyphus/evidence/task-6-sample-geocode.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add patient geocoding pipeline with Azure+Nominatim fallback`
  - Files: `ST-06/python/geocoding_pipeline.py`

---

- [x] 7. Distance Matrix Calculation

  **What to do**:
  - Calculate Haversine distance between all patients and branches
  - Store in `dk.patient_branch_distance` table
  - Add distance bands: <2km, 2-5km, 5-10km, 10-20km, 20km+
  - Flag nearest branch for each patient
  - Flag patients within catchment radius (default 10km)
  - Estimate drive time (rough approximation)

  **Must NOT do**:
  - Do NOT use routing APIs (Google Directions, etc.)
  - Do NOT calculate driving distance (Haversine only)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 8, 9, 10
  - **Blocked By**: Task 5, 6

  **References**:
  - `docs/source/Geospatial Strategy/geo_01_postgis_setup.sql` - patient_branch_distance table
  - Haversine formula implementation

  **Acceptance Criteria**:
  - [x] Distance matrix populated for all patient-branch pairs
  - [x] Distance bands calculated correctly
  - [x] Nearest branch flagged for each patient
  - [x] Catchment flags set appropriately

  **QA Scenarios**:
  ```
  Scenario: Verify distance calculations
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT distance_km, distance_band, is_nearest_branch FROM dk.patient_branch_distance LIMIT 10;"
    Expected Result: Valid distances, correct band classification, nearest flag set
    Evidence: .sisyphus/evidence/task-7-distance-matrix.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add patient-branch distance matrix calculation`
  - Files: `ST-06/sql/03_analytical_views.sql` (distance calculation)

---

### Original Request
Implement ST-06 Geospatial Analytics as part of the Healthcare BI solution. Convert raw patient addresses into geographic intelligence for catchment analysis, cannibalization detection, and expansion whitespace identification.

### Interview Summary
**Key Decisions**:
- **Geocoding**: Azure Maps API with Nominatim fallback (subscription-key authentication)
- **Strategy**: Incremental geocoding for daily runs (batch for initial load)
- **Structure**: Standard ST-06 directory structure following ST-05 patterns
- **Branch Data**: User will provide CSV with branch addresses
- **Postcode Data**: Download from public source (GitHub malaysia-postcodes)

### Metis Review
**Identified Gaps** (addressed):
- Azure Maps authentication: Use subscription-key in header
- Branch master population: User provides CSV seed data
- Postcode fallback: Download from GitHub public source
- Address quality: Pre-analysis query included
- DBSCAN parameters: Default eps=5km, min_samples=5 with tuning guidance
- Map output: ST-06/maps/ directory
- MVW refresh: Daily at 3:30 AM (after ML pipeline)

**Guardrails Applied**:
- No real-time geocoding API endpoint
- No Google Maps integration (Azure Maps only)
- No pg_cron (Windows uses pgAgent)
- No routing/directions (Haversine only)
- Exactly 7 maps, exactly 6 MVWs

---

## Work Objectives

### Core Objective
Build a complete geospatial analytics pipeline that geocodes patient addresses, calculates branch distances, identifies geographic demand clusters, detects branch cannibalization, and scores expansion whitespace opportunities.

### Concrete Deliverables
- `ST-06/sql/01_postgis_setup.sql` - PostGIS extension, tables, indexes, triggers
- `ST-06/sql/02_geocoding_views.sql` - Geocoding quality and status views
- `ST-06/sql/03_analytical_views.sql` - 7 analytical views for Power BI
- `ST-06/sql/04_materialized_views.sql` - 6 MVWs with refresh function
- `ST-06/sql/05_scheduling.sql` - pgAgent jobs for Windows
- `ST-06/python/geocoding_pipeline.py` - Azure Maps + Nominatim fallback
- `ST-06/python/geo_analysis.py` - DBSCAN clustering, cannibalization, Folium maps
- `ST-06/python/test_geocoding.py` - pytest tests for geocoding pipeline
- `ST-06/python/test_geo_analysis.py` - pytest tests for analysis
- `ST-06/maps/*.html` - 7 interactive Folium maps
- `ST-06/README.md` - Complete documentation

### Definition of Done
- [x] PostGIS extension enabled and verified
- [x] Branch master table populated with geocoded addresses
- [x] Patient geocoding pipeline incremental (daily) with >80% success rate
- [x] Distance matrix computed for all patient-branch pairs
- [x] DBSCAN clustering identifies demand clusters with is_underserved flag
- [x] Cannibalization index calculated for all branch pairs
- [x] Whitespace scoring generates top 15 expansion sites
- [x] 7 Folium maps render correctly in browser
- [x] All 6 MVWs refresh successfully with CONCURRENTLY
- [x] pgAgent jobs scheduled and executing
- [x] All tests passing (geocoding + analysis)

### Must Have
- Azure Maps API integration with subscription-key authentication
- Nominatim fallback for rate limit handling
- Four-level geocoding: Full → Street+City → City+State → ZIP
- PostGIS geometry columns with GIST indexes
- Patient-branch distance matrix (Haversine formula)
- DBSCAN clustering with configurable parameters
- Cannibalization index (shared patient percentage)
- Whitespace site priority scoring
- 7 interactive Folium maps
- 6 Power BI materialized views
- Incremental geocoding pipeline
- pgAgent scheduling for Windows

### Must NOT Have (Guardrails)
- Real-time geocoding API endpoint
- Google Maps API integration
- pg_cron scheduling (Windows uses pgAgent)
- Routing/driving directions (straight-line only)
- Territory optimization algorithms
- Patient movement tracking
- More than 7 maps
- More than 6 MVWs

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (PostGIS needed)
- **Automated tests**: YES (Tests-after pattern)
- **Framework**: pytest with real database
- **Agent QA**: Playwright for map verification, Bash for SQL/CLI

### QA Policy
Every task includes agent-executed QA scenarios:
- **SQL**: Execute queries via Bash (psql), verify row counts, check indexes
- **Python**: Run pytest, verify test output
- **Maps**: Playwright opens HTML files, verifies map renders, captures screenshot
- **Pipeline**: Bash triggers pipeline, verifies execution log
- **MVWs**: SQL refresh and verify CONCURRENTLY works

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - SQL Setup):
├── Task 1: PostGIS extension and branch_master table
├── Task 2: Patient geocode tables and indexes
├── Task 3: Geocoding quality views
└── Task 4: Malaysia postcode reference data

Wave 2 (Geocoding Pipeline):
├── Task 5: Branch geocoding pipeline and seed data
└── Task 6: Patient geocoding pipeline (Azure + Nominatim)

Wave 3 (Analytics & Clustering):
├── Task 7: Distance matrix calculation
├── Task 8: DBSCAN clustering implementation
├── Task 9: Cannibalization detection algorithm
└── Task 10: Whitespace site scoring

Wave 4 (Views, Maps & Scheduling):
├── Task 11: 7 analytical SQL views
├── Task 12: 6 materialized views with indexes
├── Task 13: 7 Folium interactive maps
├── Task 14: pgAgent scheduling setup
└── Task 15: Test suite (geocoding + analysis)

Wave FINAL (Review & Verification):
├── Task F1: Plan compliance audit
├── Task F2: Code quality review
├── Task F3: End-to-end pipeline test
└── Task F4: Map rendering verification

Critical Path: Task 1 → Task 5 → Task 6 → Task 7 → Task 8 → Task 9 → Task 10 → Task 13 → F1-F4
Parallel Speedup: ~40% faster than sequential
Max Concurrent: 4 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|------------|--------|
| 1 | - | 2, 3, 5 |
| 2 | 1 | 6 |
| 3 | 1 | - |
| 4 | - | 6 |
| 5 | 1 | 7, 9 |
| 6 | 2, 4 | 7 |
| 7 | 5, 6 | 8, 9, 10 |
| 8 | 7 | 10, 13 |
| 9 | 5, 7 | 10 |
| 10 | 8, 9 | 13 |
| 11 | 7, 8, 9, 10 | 12 |
| 12 | 11 | 14 |
| 13 | 8, 10 | - |
| 14 | 12 | - |
| 15 | 6, 8, 9, 10 | F1-F4 |

### Agent Dispatch Summary

- **Wave 1**: 4 tasks → `quick` (SQL setup)
- **Wave 2**: 2 tasks → `quick` (Python pipelines)
- **Wave 3**: 4 tasks → `unspecified-high` (analytics algorithms)
- **Wave 4**: 5 tasks → `visual-engineering` (maps), `quick` (views, scheduling)
- **Wave FINAL**: 4 tasks → `oracle`, `unspecified-high`

---

## TODOs

- [x] 1. PostGIS Extension and Core Tables

  **What to do**:
  - Enable PostGIS extension: `CREATE EXTENSION IF NOT EXISTS postgis;`
  - Create `dk.branch_master` table with lat/lng and geometry columns
  - Create `dk.patient_geocode` table for geocoding results
  - Create `dk.my_postcode_ref` table for postcode fallback
  - Create `dk.patient_branch_distance` table for distance matrix
  - Add auto-update triggers for geometry columns
  - Create GIST spatial indexes

  **Must NOT do**:
  - Do NOT create tables outside dk schema
  - Do NOT skip index creation (performance critical)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - Reason: SQL setup task with standard patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2, 3, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 2, 5
  - **Blocked By**: None

  **References**:
  - `ST-01/sql/02_materialized_views.sql` - Pattern for table creation with indexes
  - `docs/source/Geospatial Strategy/geo_01_postgis_setup.sql` - Reference table structure
  - PostGIS docs: https://postgis.net/documentation/

  **Acceptance Criteria**:
  - [x] PostGIS extension enabled
  - [x] `SELECT postgis_full_version()` returns version info
  - [x] All 5 tables created in dk schema
  - [x] GIST indexes created on geometry columns
  - [x] Auto-update triggers functional

  **QA Scenarios**:
  ```
  Scenario: Verify PostGIS installation
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT postgis_full_version();"
    Expected Result: Returns PostGIS version string (e.g., "3.4.0")
    Evidence: .sisyphus/evidence/task-1-postgis-version.txt

  Scenario: Verify table creation
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT table_name FROM information_schema.tables WHERE table_schema='dk' AND table_name IN ('branch_master','patient_geocode','my_postcode_ref','patient_branch_distance','patient_geo_clusters');"
    Expected Result: All 5 table names returned
    Evidence: .sisyphus/evidence/task-1-tables-created.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add PostGIS extension and core geospatial tables`
  - Files: `ST-06/sql/01_postgis_setup.sql`

---

- [x] 2. Patient Geocode Tables and Indexes

  **What to do**:
  - Create `dk.patient_geo_clusters` table for DBSCAN results
  - Create `dk.branch_overlap_analysis` table for cannibalization
  - Create `dk.geocode_execution_log` table for pipeline tracking
  - Add composite unique indexes for CONCURRENTLY refresh
  - Create foreign key references to dk.patient

  **Must NOT do**:
  - Do NOT create indexes on nullable geometry columns before data exists

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 1, 3, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 6
  - **Blocked By**: Task 1

  **References**:
  - `ST-05/sql/03_materialized_views.sql` - Pattern for unique indexes

  **Acceptance Criteria**:
  - [x] All 3 additional tables created
  - [x] Composite unique indexes on cluster_id, branch pairs
  - [x] Foreign key constraints defined

  **QA Scenarios**:
  ```
  Scenario: Verify cluster table structure
    Tool: Bash (psql)
    Steps:
      1. psql -c "\d dk.patient_geo_clusters"
    Expected Result: Shows columns: cluster_id, centroid_lat, centroid_lng, patient_count, etc.
    Evidence: .sisyphus/evidence/task-2-cluster-table.txt
  ```

  **Commit**: YES (groups with Task 1)

---

- [x] 3. Geocoding Quality Views

  **What to do**:
  - Create `dk.vw_geocode_quality_summary` - summary stats by quality level
  - Create `dk.vw_geocode_execution_status` - pipeline execution tracking
  - Create `dk.vw_patient_geo_enriched` - patient + geocode join

  **Must NOT do**:
  - Do NOT include PII (phone, full address) in views

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 1, 2, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `ST-01/sql/01_core_views.sql` - Pattern for quality views

  **Acceptance Criteria**:
  - [x] 3 views created successfully
  - [x] Views return data without errors
  - [x] No PII columns exposed

  **QA Scenarios**:
  ```
  Scenario: Verify geocode quality view
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT * FROM dk.vw_geocode_quality_summary;"
    Expected Result: Returns quality levels (exact, city, state, zip, failed) with counts
    Evidence: .sisyphus/evidence/task-3-quality-view.txt
  ```

  **Commit**: YES (groups with Task 1, 2)

---

- [x] 4. Malaysia Postcode Reference Data

  **What to do**:
  - Download Malaysia postcode data from public GitHub source
  - Create loader script to populate `dk.my_postcode_ref`
  - Columns: postcode, city, state, latitude, longitude
  - Validate coordinate ranges (lat: 1-7, lng: 99-120)

  **Must NOT do**:
  - Do NOT commit raw postcode data to git
  - Do NOT hardcode download URLs in production code

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 1, 2, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 6
  - **Blocked By**: None

  **References**:
  - `docs/source/Geospatial Strategy/geo_01_postgis_setup.sql` - my_postcode_ref structure
  - GitHub: https://github.com/metalix2/malaysia-postcodes (or similar public source)

  **Acceptance Criteria**:
  - [x] Postcode reference table populated with ~2,800 records
  - [x] All coordinates within Malaysia bounds
  - [x] No NULL values in critical columns

  **QA Scenarios**:
  ```
  Scenario: Verify postcode data loaded
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT COUNT(*) as count FROM dk.my_postcode_ref;"
    Expected Result: count > 2000
    Evidence: .sisyphus/evidence/task-4-postcode-count.txt

  Scenario: Verify coordinate bounds
    Tool: Bash (psql)
    Steps:
      1. psql -c "SELECT MIN(latitude), MAX(latitude), MIN(longitude), MAX(longitude) FROM dk.my_postcode_ref;"
    Expected Result: lat in [1,7], lng in [99,120]
    Evidence: .sisyphus/evidence/task-4-postcode-bounds.txt
  ```

  **Commit**: YES
  - Message: `feat(st-06): Add Malaysia postcode reference data loader`
  - Files: `ST-06/python/load_postcode_data.py`

---
