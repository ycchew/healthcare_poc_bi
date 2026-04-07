# ST-02: Sales & Revenue Analytics

## Overview

ST-02 implements Sales & Revenue Analytics for the Healthcare Analytics Business Intelligence solution. This sub-task creates sales-focused views, forecasting capabilities, and analytics utilities for revenue analysis.

## Prerequisites

**ST-01 must be completed before ST-02.** ST-02 reuses the database utilities from ST-01:
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

ST-02 SQL views use actual columns from `dk.collection`:

| SQL View Field | Source Column | Notes |
|----------------|---------------|-------|
| `transaction_date` | `c.date` | Date of transaction |
| `branch` | `c.branch` | Branch name |
| `total_transactions` | `COUNT(c.row_number)` | Distinct transaction count |
| `total_collected` | `SUM(c.amount_collected)` | Revenue collected |
| `total_discount` | `SUM(c.discount)` | Discounts applied |

**Pre-split Revenue Columns (dk.collection):**

| Category | Standalone Column | Package Column |
|----------|------------------|----------------|
| Consultations | `standalone_sales_consultations` | N/A |
| Services | `standalone_sales_services` | `package_sales_services` |
| Medications | `standalone_sales_medications` | `package_sales_medications` |
| Supplements | `standalone_sales_supplements_*_amount` | `package_sales_supplements_*_amount` |
| Skincare | `standalone_sales_skincare_product_amount` | `package_sales_skincare_product_amount` |
| Other | `standalone_sales_other_product_amount` | `package_sales_other_product_amount` |

## Files Created

### SQL Files

| File | Description | Views Created |
|------|-------------|---------------|
| `01_sales_views.sql` | Sales performance views | 4 views |
| `02_calendar_effects_views.sql` | Festival and calendar analysis | 4 views + 1 table |
| `03_materialized_views.sql` | Materialized views with indexes | 7 MVWs + 2 tables |

### Python Files

| File | Description |
|------|-------------|
| `sales_forecast.py` | Prophet-based 90-day sales forecasting |
| `sales_analytics.py` | Sales analytics queries and reports |

## Views Reference

### Sales Views (01_sales_views.sql)

| View | Purpose |
|------|---------|
| `vw_daily_sales_summary` | Daily revenue with time dimensions, category breakdown, collection metrics |
| `vw_branch_performance` | Branch-level metrics with MoM/YoY growth, rankings, tier classification |
| `vw_product_performance` | Category performance (services, medications, supplements, skincare, other) |
| `vw_monthly_sales_trend` | Time series for forecasting with moving averages |

### Calendar Effects Views (02_calendar_effects_views.sql)

| View | Purpose |
|------|---------|
| `vw_calendar_effects` | Festival period classification (pre, during, post) |
| `vw_festival_performance` | Aggregated performance by festival and period type |
| `vw_promotion_impact` | Baseline comparison, discount tier analysis, anomaly detection |
| `vw_dow_heatmap` | Day-of-week patterns by branch |

### Materialized Views (03_materialized_views.sql)

| Materialized View | Refresh Schedule | Purpose |
|-------------------|------------------|---------|
| `mvw_daily_sales_summary` | Daily 2:00 AM | Daily revenue aggregations |
| `mvw_branch_performance` | Daily 2:00 AM | Branch KPIs and rankings |
| `mvw_product_performance` | Daily 2:00 AM | Category performance |
| `mvw_monthly_sales_trend` | Daily 2:00 AM | Monthly trend data |
| `mvw_calendar_effects` | Daily 2:00 AM | Calendar effects |
| `mvw_promotion_impact` | Daily 2:00 AM | Promotion analysis |
| `mvw_dow_heatmap` | Daily 2:00 AM | Day-of-week patterns |

### Tables Created

| Table | Purpose |
|-------|---------|
| `dk.malaysian_holidays` | Configurable Malaysian festival dates |
| `dk.sales_forecast` | Prophet-generated 90-day forecasts |
| `dk.forecast_accuracy` | Forecast vs actual tracking |

## Malaysian Holidays Configuration

The `dk.malaysian_holidays` table supports configurable festival periods:

| Holiday | Default Pre-Period | Default Post-Period |
|---------|-------------------|---------------------|
| Chinese New Year | 14 days | 7 days |
| Hari Raya | 14 days | 7 days |
| Deepavali | 7 days | 7 days |
| Christmas | 14 days | 7 days |
| Merdeka | 3 days | 1 day |

## Python Modules

### Python Import Path

ST-02 Python modules import from `ST-01/python/database`:

```python
# In sales_forecast.py
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ST-01" / "python"))
from database import DatabaseManager, get_db_manager
```

### SalesForecaster Class

```python
from ST_02.python.sales_forecast import SalesForecaster, run_daily_forecast

# Initialize forecaster
forecaster = SalesForecaster(forecast_days=90)

# Train models and generate forecasts for all branches
forecast_df = forecaster.generate_all_branch_forecasts()

# Save to database
rows_saved = forecaster.save_forecast(forecast_df)

# Get forecast summary
summary = forecaster.get_forecast_summary(days_ahead=30)
```

### SalesAnalyticsManager Class

```python
from ST_02.python.sales_analytics import SalesAnalyticsManager

# Initialize manager
manager = SalesAnalyticsManager()

# Get executive summary (MTD)
summary = manager.get_executive_summary()

# Get branch ranking
ranking = manager.get_branch_ranking(limit=10)

# Get monthly trend
trend = manager.get_monthly_trend(months=12)

# Get festival impact
festival_impact = manager.get_festival_impact(year=2024)

# Check data freshness
freshness = manager.check_data_freshness()
```

## Setup Instructions

### 1. Ensure ST-01 is Complete

```bash
# Verify ST-01 views exist
psql -U your_user -d your_database -c "SELECT * FROM dk.vw_patient_enriched LIMIT 1;"
```

### 2. Run SQL Scripts

Execute in this order:

```bash
# Connect to PostgreSQL
psql -U your_user -d your_database

# Run sales views
\i sql/01_sales_views.sql

# Run calendar effects views
\i sql/02_calendar_effects_views.sql

# Run materialized views
\i sql/03_materialized_views.sql
```

### 3. Install Additional Python Dependencies

```bash
pip install prophet pandas numpy sqlalchemy psycopg2-binary python-dotenv
```

### 4. Test Sales Analytics

```bash
cd python

# Run all tests (requires live database)
pytest test_sales_analytics.py -v
```

### 5. Run Forecasting

```bash
cd python
python sales_forecast.py
```

## Scheduling

### Daily Forecast Generation

The `run_daily_forecast()` function can be scheduled:

```python
from ST_02.python.sales_forecast import run_daily_forecast

result = run_daily_forecast(forecast_days=90)
print(f"Status: {result['status']}")
print(f"Branches: {result['branches_forecasted']}")
print(f"Rows saved: {result['rows_saved']}")
```

### Cross-Platform Scheduling (from ST-01)

Use the `detect_os()` function from ST-01 for platform-specific scheduling:
- **Linux/macOS**: pg_cron
- **Windows**: pgAgent or Windows Task Scheduler

## Key Constraints

1. **Patient PK**: `location` (not `mrn` - MRN has duplicates)
2. **Collection PK**: `row_number` (not `id`)
3. **Schema**: All objects in `dk` schema
4. **Source Tables**: `dk.collection`, `dk.patient`
5. **Date Field**: `date` (not `transaction_date`)
6. **Amount Field**: `amount_collected` (not `net_amount`)
7. **Branch Field**: `branch` (not `branch_code`)
8. **Discount Field**: `discount` (not `discount_amount`)
9. **Environment Variables**: Use `DB_*` (standardized)
10. **Python Imports**: Use `ST-01/python/database`

## Branch Performance Tier Classification

| Tier | Revenue Range | Description |
|------|--------------|-------------|
| Top | Revenue > 80th percentile | Highest performing branches |
| High | Revenue > 60th percentile | Strong performers |
| Medium | Revenue > 40th percentile | Average performers |
| Low | Revenue ≤ 40th percentile | Needs attention |

## Growth Status Classification

| Status | MoM Growth | YoY Growth |
|--------|-----------|------------|
| Growing | > 10% | > 10% |
| Stable | -10% to 10% | -10% to 10% |
| Declining | < -10% | < -10% |

## Promotion Effectiveness

| Tier | Discount Range | Expected Lift |
|------|---------------|---------------|
| None | 0% | Baseline |
| Low | 1-5% | 5-15% |
| Medium | 5-15% | 15-30% |
| High | 15-30% | 30-50% |
| Aggressive | > 30% | Variable |

## Lessons Learned

### Cross-Module Imports with Hyphens

**Problem**: Import statements fail when module names contain hyphens (e.g., `ST-01`).

**Solution**: Use `importlib.util` for dynamic imports:
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

### Prophet Type Stubs

**Problem**: Pyright reports type errors for Prophet parameters (`yearly_seasonality`, `weekly_seasonality`).

**Root Cause**: Prophet's type stubs incorrectly specify these as `str` when they actually accept `int` and `bool`.

**Solution**: Add `# pyright: ignore[reportArgumentType]` comments to suppress false positives.

### Date Arithmetic in Pandas

**Problem**: Subtracting date objects doesn't have `.dt.days` accessor.

**Solution**: Use `.apply(lambda x: (x - today).days)` for element-wise date difference calculation.

### Forecast Return Types

**Problem**: Pyright reports return type mismatch for DataFrame operations.

**Solution**: Add `# pyright: ignore[reportReturnType]` or `# type: ignore[return-value]` comments where type inference fails.

## Dependencies

- **PostgreSQL 12+** with materialized view support
- **Python 3.9+**
- **Prophet** (for forecasting)
- **pandas, numpy** (data manipulation)
- **sqlalchemy, psycopg2-binary** (database connectivity)

## Troubleshooting

### Sales Views Return Empty Results

Check source data:
```sql
SELECT COUNT(*) FROM dk.collection;
SELECT COUNT(*) FROM dk.collection_report;
SELECT MIN(date), MAX(date) FROM dk.collection;
```

### Prophet Fails to Train

Ensure sufficient historical data:
- Minimum 30 days of data per branch
- Prophet requires at least 2 full seasonal cycles for best results

### Materialized View Refresh Fails

Refresh manually:
```sql
SELECT dk.refresh_sales_mvws();
```

Or individually:
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_daily_sales_summary;
```

## Next Steps

After ST-02 is complete, proceed to **ST-03** (next sub-task in the project plan).