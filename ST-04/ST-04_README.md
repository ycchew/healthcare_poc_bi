# ST-04: Product & Package Performance Analytics

## Overview

ST-04 implements Product & Package Performance Analytics for the Healthcare Analytics Business Intelligence solution. This sub-task creates product category views, package analytics, payment behavior analysis, and Python utilities for reporting.

## Prerequisites

**ST-01 must be completed before ST-04.** ST-04 reuses the database utilities from ST-01:
- `ST-01/python/database.py` - DatabaseManager, get_db_manager
- Environment variables: `DB_*` (see `.env.example`)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `postgres` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | `password` |

## Schema Field Mappings

ST-04 SQL views use actual columns from `dk.collection`:

| SQL View Field | Source Column | Notes |
|----------------|---------------|-------|
| `date` | `c.date` | Date of transaction |
| `branch` | `c.branch` | Branch name |
| `mrn` | `c.mrn` | Patient MRN (not unique) |
| `amount_collected` | `c.amount_collected` | Revenue collected |
| `patient_outstanding_amount` | `c.patient_outstanding_amount` | Outstanding balance |

**Pre-split Revenue Columns (dk.collection):**

| Category | Standalone Column | Package Column |
|----------|------------------|----------------|
| Consultations | `standalone_sales_consultations` | N/A |
| Services | `standalone_sales_services` | `package_sales_services` |
| Medications | `standalone_sales_medications` | `package_sales_medications` |
| Supplements RM5 | `standalone_sales_supplements_supplement_rm5_amount` | `package_sales_supplements_supplement_rm5_amount` |
| Supplements RM5 Unit | `standalone_sales_supplements_supplement_rm5_unit` | `package_sales_supplements_supplement_rm5_unit` |
| Skincare | `standalone_sales_skincare_product_amount` | `package_sales_skincare_product_amount` |
| Skincare Unit | `standalone_sales_skincare_product_unit` | `package_sales_skincare_product_unit` |
| Other | `standalone_sales_other_product_amount` | `package_sales_other_product_amount` |

**Offset Columns (Payment Mode Analysis):**

| Column | Payment Mode |
|--------|--------------|
| `offset_package_balance` | PACKAGE_REDEMPTION |
| `offset_deposit_loyalty` | LOYALTY_DEPOSIT |
| `offset_deposit_on_behalf` | ON_BEHALF |
| `offset_deposit_open` | OPEN_DEPOSIT |
| (none of above) | DIRECT_PAYMENT |

**Note:** Columns with `_rm` suffix exist ONLY in `dk.collection_report`, NOT in `dk.collection`.

## Files Created

### SQL Files

| File | Description | Views Created |
|------|-------------|---------------|
| `01_product_performance_views.sql` | Product category performance views | 5 views |
| `02_package_analytics_views.sql` | Package composition and redemption analysis | 4 views |
| `03_payment_behavior_views.sql` | Payment mode and affordability stress | 4 views |
| `04_materialized_views.sql` | Materialized views with indexes | 7 MVWs + 1 function |

### Python Files

| File | Description |
|------|-------------|
| `product_analytics.py` | ProductAnalyticsManager class with 17 methods |
| `test_product_analytics.py` | 40 unit + integration tests |

## Views Reference

### Product Performance Views (01_product_performance_views.sql)

| View | Purpose |
|------|---------|
| `vw_skincare_monthly` | Skincare revenue by branch/channel/month with unit counts |
| `vw_supplements_monthly` | RM5 supplements breakdown (amount + units) |
| `vw_medications_monthly` | Medications: standalone vs package split |
| `vw_services_monthly` | Services and consultations by branch/month |
| `vw_category_mix` | Category revenue share per branch/month |

### Package Analytics Views (02_package_analytics_views.sql)

| View | Purpose |
|------|---------|
| `vw_package_composition` | Package breakdown by category (services/skincare/meds/supplements) |
| `vw_package_redemption` | Patient redemption rates with status classification |
| `vw_package_addon` | Standalone spend during package visits |
| `vw_package_conversion_demographics` | Package buyer demographics analysis |

### Payment Behavior Views (03_payment_behavior_views.sql)

| View | Purpose |
|------|---------|
| `vw_payment_mode_distribution` | Payment mode by demographics (race, age_band, gender) |
| `vw_affordability_stress` | Patient financial stress analysis (stress_ratio, stress_level) |
| `vw_payment_preference_by_stress` | Package vs standalone preference by stress level |
| `vw_stressed_buyers` | High outstanding patients who are still buying |

### Materialized Views (04_materialized_views.sql)

| Materialized View | Refresh Schedule | Purpose |
|-------------------|------------------|---------|
| `mvw_skincare_monthly` | Daily 2:00 AM | Skincare performance data |
| `mvw_package_composition` | Daily 2:00 AM | Package composition breakdown |
| `mvw_package_conversion_demo` | Daily 2:00 AM | Package conversion demographics |
| `mvw_payment_mode_dist` | Daily 2:00 AM | Payment mode distribution |
| `mvw_affordability_stress` | Daily 2:00 AM | Affordability stress analysis |
| `mvw_product_category_mix` | Daily 2:00 AM | Category revenue mix |
| `mvw_stressed_buyers` | Daily 2:00 AM | Stressed buyers list |

## Python Modules

### Python Import Path

ST-04 Python modules import from `ST-01/python/database` using `importlib.util`:

```python
import importlib.util
from pathlib import Path

db_path = Path(__file__).parent.parent.parent / "ST-01" / "python" / "database.py"
spec = importlib.util.spec_from_file_location("database", db_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load database module from {db_path}")
database_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database_module)
DatabaseManager = database_module.DatabaseManager
get_db_manager = database_module.get_db_manager
```

### ProductAnalyticsManager Class

```python
from ST_04.python.product_analytics import ProductAnalyticsManager

# Initialize manager
manager = ProductAnalyticsManager()

# Product Performance
skincare = manager.get_skincare_performance(months=6)
supplements = manager.get_supplements_breakdown(months=6)
medications = manager.get_medications_performance(months=6)
services = manager.get_services_performance(months=6)
category_mix = manager.get_category_mix(months=6)

# Package Analytics
composition = manager.get_package_composition(months=6)
redemption = manager.get_redemption_rates(limit=100)
addon = manager.get_addon_analysis(months=6)
conversion = manager.get_package_conversion_demographics()

# Payment Behavior
payment_dist = manager.get_payment_mode_distribution()
stress = manager.get_affordability_stress(limit=100)
preference = manager.get_payment_preference_by_stress()
stressed_buyers = manager.get_stressed_buyers()

# Utility
freshness = manager.check_data_freshness()
manager.refresh_product_mvws()
report = manager.generate_product_report(report_type='executive')
```

### Convenience Function

```python
from ST_04.python.product_analytics import run_product_report

# Generate report (creates its own manager)
report = run_product_report(report_type='executive', months=6)
```

## Setup Instructions

### 1. Ensure ST-01 is Complete

```bash
# Verify ST-01 views exist
psql -U your_user -d your_database -c "SELECT * FROM dk.vw_patient_enriched LIMIT 1;"
```

### 2. Run SQL Scripts (Correct Order)

Execute in this order accounting for dependencies:

```bash
# Step 1: Product Performance Views (no dependencies)
psql -U postgres -d postgres -f "ST-04/sql/01_product_performance_views.sql"

# Step 2: Payment Behavior Views (no dependencies)
psql -U postgres -d postgres -f "ST-04/sql/03_payment_behavior_views.sql"

# Step 3: Package Analytics Views (depends on vw_affordability_stress from Step 2)
psql -U postgres -d postgres -f "ST-04/sql/02_package_analytics_views.sql"

# Step 4: Materialized Views (depends on all views above)
psql -U postgres -d postgres -f "ST-04/sql/04_materialized_views.sql"
```

### 3. Refresh Materialized Views

```sql
SELECT dk.refresh_product_mvws();
```

### 4. Install Python Dependencies

```bash
pip install pandas numpy sqlalchemy psycopg2-binary python-dotenv pytest
```

### 5. Run Tests

```bash
cd ST-04/python

# Unit tests only (no database required)
pytest test_product_analytics.py -v -m "not integration"

# Integration tests (requires database + MVWs)
pytest test_product_analytics.py -v -m integration
```

## Key Constraints

1. **Patient PK**: `location` (not `mrn` - MRN has duplicates)
2. **Collection PK**: `row_number` (not `id`)
3. **Schema**: All objects in `dk` schema
4. **Source Tables**: `dk.collection`, `dk.patient`, `dk.collection_report`
5. **Date Field**: `date` (not `transaction_date`)
6. **Amount Field**: `amount_collected` (not `net_amount`)
7. **Branch Field**: `branch` (not `branch_code`)
8. **No `_rm` suffix**: `dk.collection` columns don't have `_rm` suffix (only in `dk.collection_report`)
9. **Environment Variables**: Use `DB_*` with `.strip()` (standardized)
10. **Python Imports**: Use `importlib.util` for cross-module imports (handles hyphens)

## Stress Level Classification

| Level | Stress Ratio | Description |
|-------|--------------|-------------|
| CRITICAL | ≥ 3.0 | Outstanding ≥ 3x monthly spend |
| HIGH | ≥ 2.0 | Outstanding ≥ 2x monthly spend |
| MEDIUM | ≥ 1.0 | Outstanding ≥ monthly spend |
| LOW | < 1.0 | Outstanding < monthly spend |

**Stress Ratio Formula**: `avg_outstanding / avg_monthly_spend`

## Payment Mode Classification

| Mode | Condition | Description |
|------|-----------|-------------|
| PACKAGE_REDEMPTION | `offset_package_balance > 0` | Package credit used |
| LOYALTY_DEPOSIT | `offset_deposit_loyalty > 0` | Loyalty program deposit |
| ON_BEHALF | `offset_deposit_on_behalf > 0` | Payment by third party |
| OPEN_DEPOSIT | `offset_deposit_open > 0` | Open deposit account |
| DIRECT_PAYMENT | none of above | Direct cash/card payment |

## Lessons Learned

### Column Suffix Confusion

**Problem**: Initial implementation used `_rm` suffix columns (e.g., `standalone_sales_consultations_rm`).

**Root Cause**: `dk.collection_report` has `_rm` suffix columns, but `dk.collection` does not.

**Solution**: All views must use columns from `dk.collection` without `_rm` suffix:
- `standalone_sales_consultations` (not `standalone_sales_consultations_rm`)
- `standalone_sales_services` (not `standalone_sales_services_rm`)

### Ambiguous Column References

**Problem**: `stress_level` ambiguous when joining multiple views with same column name.

**Solution**: Always prefix column names with alias in SELECT/GROUP BY/ORDER BY:
```sql
SELECT sap.stress_level  -- not just stress_level
FROM stress_and_preference sap
JOIN dk.vw_affordability_stress vs ON vs.mrn = sap.mrn
GROUP BY sap.stress_level
ORDER BY sap.stress_level
```

### PostgreSQL Date Arithmetic

**Problem**: `EXTRACT(DAY FROM (CURRENT_DATE - MAX(c.date)))` fails.

**Root Cause**: PostgreSQL date subtraction returns integer directly, not interval.

**Solution**: Use direct cast:
```sql
(CURRENT_DATE - MAX(c.date))::INTEGER AS days_since_visit
```

### Unique Index on Non-Unique Data

**Problem**: Cannot create unique index on `mrn` alone in `vw_affordability_stress`.

**Root Cause**: Same MRN can appear at multiple branches (patient visits different locations).

**Solution**: Use `DISTINCT ON (mrn, branch)` in view, and composite unique index:
```sql
-- In view
SELECT DISTINCT ON (mrn, branch) ...
ORDER BY mrn, branch, stress_ratio DESC;

-- In MVW
CREATE UNIQUE INDEX idx_mvw_afford_stress_mrn_branch ON dk.mvw_affordability_stress (mrn, branch);
```

### Missing Columns in Views

**Problem**: Python method expects `patient_name` but SQL view doesn't have it.

**Root Cause**: `patient_name` is in `dk.collection_report`, not `dk.collection` or `dk.patient`.

**Solution**: Use LATERAL join to fetch from `dk.collection_report`:
```sql
LEFT JOIN LATERAL (
    SELECT patient_name 
    FROM dk.collection_report cr2 
    WHERE cr2.mrn = as_view.mrn 
    ORDER BY cr2.csv_date DESC 
    LIMIT 1
) cr ON true
```

### Wrong Column Names

**Problem**: Using `current_outstanding` when view has `avg_outstanding`.

**Solution**: Check view schema before using column names. `vw_affordability_stress` has:
- `avg_outstanding` (average outstanding balance)
- NOT `current_outstanding`

## View Dependencies Graph

```
01_product_performance_views.sql (no dependencies)
    vw_skincare_monthly
    vw_supplements_monthly
    vw_medications_monthly
    vw_services_monthly
    vw_category_mix

03_payment_behavior_views.sql (no dependencies)
    vw_payment_mode_distribution
    vw_affordability_stress ← referenced by vw_package_conversion_demographics
    vw_payment_preference_by_stress
    vw_stressed_buyers

02_package_analytics_views.sql (depends on vw_affordability_stress)
    vw_package_composition
    vw_package_redemption
    vw_package_addon
    vw_package_conversion_demographics ← JOINs vw_affordability_stress

04_materialized_views.sql (depends on all views)
    mvw_skincare_monthly ← vw_skincare_monthly
    mvw_package_composition ← vw_package_composition
    mvw_package_conversion_demo ← vw_package_conversion_demographics
    mvw_payment_mode_dist ← vw_payment_mode_distribution
    mvw_affordability_stress ← vw_affordability_stress
    mvw_product_category_mix ← vw_category_mix
    mvw_stressed_buyers ← vw_stressed_buyers
```

## Troubleshooting

### Views Return Empty Results

Check source data:
```sql
SELECT COUNT(*) FROM dk.collection;
SELECT COUNT(*) FROM dk.patient;
SELECT MIN(date), MAX(date) FROM dk.collection;
```

### Materialized View Refresh Fails

Refresh manually:
```sql
SELECT dk.refresh_product_mvws();
```

Or individually:
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_skincare_monthly;
```

### Unique Index Creation Fails

Ensure view has `DISTINCT ON` for the index columns:
```sql
SELECT DISTINCT ON (mrn, branch) ...  -- enables UNIQUE INDEX on (mrn, branch)
```

### Python Tests Fail

1. Check database connection: ensure `.env` has all `DB_*` variables
2. Check MVWs exist: `SELECT * FROM dk.mvw_skincare_monthly LIMIT 1;`
3. Run unit tests first: `pytest -m "not integration"`

## Dependencies

- **PostgreSQL 12+** with materialized view support
- **Python 3.9+**
- **pandas, numpy** (data manipulation)
- **sqlalchemy, psycopg2-binary** (database connectivity)
- **pytest** (testing)

## Next Steps

After ST-04 is complete, proceed to **ST-05** (next sub-task in the project plan).