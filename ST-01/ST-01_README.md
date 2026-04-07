# ST-01: Data Foundation & Infrastructure

## Overview

ST-01 establishes the core data foundation for the Healthcare Analytics Business Intelligence solution. This sub-task creates the foundational views, materialized views, and Python utilities required for all subsequent sub-tasks.

## Environment Variables

All scripts use standardized `DB_*` environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `postgres` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | `password` |
| `DB_SCHEMA` | Schema name | `dk` |

## Schema Reference

**IMPORTANT**: The SQL views match the actual database schema:

### Patient Table (dk.patient)
| Column | Type | Description |
|--------|------|-------------|
| `mrn` | VARCHAR | Primary key (Medical Record Number) |
| `gender` | VARCHAR | Patient gender |
| `date_of_birth` | DATE | Patient birth date |
| `city` | VARCHAR | City name |
| `state` | VARCHAR | State name |
| `country` | VARCHAR | Country name |
| `address` | TEXT | Full address |

### Collection Table (dk.collection)
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `mrn` | VARCHAR | Foreign key to patient |
| `sale_order_no` | VARCHAR | Order number |
| `transaction_date` | DATE | Transaction date |
| `branch_code` | VARCHAR | Branch identifier |
| `branch_name` | VARCHAR | Branch name |
| `category` | VARCHAR | Product/service category |
| `product_code` | VARCHAR | Product code |
| `net_amount` | NUMERIC | Net transaction amount |
| `gross_amount` | NUMERIC | Gross transaction amount |
| `discount_amount` | NUMERIC | Discount applied |
| `tax_amount` | NUMERIC | Tax amount |
| `is_package` | BOOLEAN | Is package transaction |

### Collection Report Table (dk.collection_report)
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `mrn` | VARCHAR | Foreign key to patient |
| `report_date` | DATE | Report date |
| `status` | VARCHAR | Report status |

## Files Created

### SQL Files

| File | Description | Views Created |
|------|-------------|---------------|
| `01_core_views.sql` | Core database views | 8 views |
| `02_materialized_views.sql` | Materialized views with indexes | 7 materialized views |
| `03_scheduling_views.sql` | pg_cron scheduling setup | N/A (scheduling only) |

### Python Files

| File | Description |
|------|-------------|
| `database.py` | DatabaseManager class, connection utilities, get_db_manager() |
| `setup.py` | Configuration and project setup utilities |

### DatabaseManager Class

The `database.py` module provides:

```python
from ST_01.python.database import DatabaseManager, get_db_manager

# Get singleton instance
db = get_db_manager()

# Execute query (returns DataFrame)
df = db.execute_query("SELECT * FROM dk.patient LIMIT 10")

# Execute with transaction
with db.get_transaction() as conn:
    conn.execute(text("INSERT INTO dk.table VALUES (...)"))

# Refresh materialized view
db.refresh_materialized_view("mvw_patient_enriched")

# Connection string builder
conn_str = get_db_connection_string()
```

## Views Reference

### Core Views (01_core_views.sql)

| View | Purpose |
|------|---------|
| `vw_patient_enriched` | Patient data with calculated fields (age, status, recency) |
| `vw_transaction_flat` | Flattened transaction view with all dimensions |
| `vw_patient_transactions` | Patient-level transaction aggregations |
| `vw_patient_rfm` | RFM segmentation with 11 customer segments |
| `vw_patient_lifetime_value` | Patient LTV predictions and health scores |
| `vw_ml_patient_features` | Feature engineering for ML models |
| `vw_calendar_effects` | Calendar/seasonality analysis |
| `vw_d3_followup_tracker` | D+3 follow-up list for campaigns |

### Materialized Views (02_materialized_views.sql)

| Materialized View | Refresh Schedule | Indexes |
|-------------------|------------------|---------|
| `mvw_patient_enriched` | Daily 1:00 AM | patient_id, city, status |
| `mvw_transaction_flat` | Daily 1:00 AM | collection_id, patient_id, transaction_date |
| `mvw_patient_transactions` | Daily 1:00 AM | patient_id, revenue, transactions |
| `mvw_patient_rfm` | Daily 1:00 AM | patient_id, segment, priority, high_value |
| `mvw_patient_ltv` | Daily 1:00 AM | patient_id, tier, health_score |
| `mvw_calendar_effects` | Daily 1:00 AM | transaction_date, month, season |
| `mvw_d3_followup_list` | Daily 1:00 AM | patient_id, priority, status |

## RFM Segmentation

The RFM view categorizes patients into 11 segments:

1. **Champions** - Best customers in all dimensions
2. **Loyal Customers** - High frequency and monetary
3. **Potential Loyalists** - Recent with moderate activity
4. **New Customers** - Recent but low frequency
5. **Promising** - Moderate activity, low value
6. **Need Attention** - Moderate recency, declining
7. **About to Sleep** - Below average recency
8. **At Risk** - Low recency, were valuable
9. **Cannot Lose Them** - Very valuable but inactive
10. **Hibernating** - Low activity, moderate value
11. **Lost** - Low across all dimensions

## Setup Instructions

### 1. Configure Environment

```bash
# Copy environment template
cp ../../.env.example ../../.env

# Edit .env with your database credentials
```

### 2. Job Scheduling Setup (Optional but Recommended)

Set up automatic refresh **before** creating views. Choose based on your environment:

#### Option A: pg_cron (Linux/macOS)

```sql
-- Check if pg_cron is installed
SELECT * FROM pg_extension WHERE extname = 'pg_cron';

-- Install pg_cron if not present (requires admin privileges)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Verify scheduled jobs after running 03_scheduling_views.sql
SELECT * FROM cron.job;

-- Check job run details
SELECT * FROM cron.job_run_details ORDER by start_time DESC;
```

#### Option B: pgAgent (Windows)

pg_cron is not available on Windows. Use pgAgent instead:

```sql
-- Install pgAgent extension (requires admin privileges)
CREATE EXTENSION IF NOT EXISTS pgagent;

-- Create a job to refresh materialized views daily at 1:00 AM
-- Use pgAdmin or psql to configure:

-- 1. Create the job
SELECT pgagent.pga_job_insert(
    1,                          -- jobclassid
    'daily-mvw-refresh',        -- jobname
    TRUE,                       -- jobenabled
    'Refresh all materialized views daily',  -- jobdesc
    '0 1 * * *',               -- jobschedule (cron format)
    'sql/03_scheduling_views.sql'  -- jobhostagent
);

-- 2. Add a step to call the refresh function
SELECT pgagent.pga_jobstep_insert(
    1,                          -- jstjobid
    'Refresh MVWs',             -- jstname
    TRUE,                       -- jstenabled
    's',                        -- jstkind (sql)
    TRUE,                       -- jstcode
    'SELECT dk.refresh_all_mvws();',  -- jstcode
    ''                          -- jstconnstr
);
```

**Alternative**: Use Windows Task Scheduler to run a batch file:
```batch
@echo off
psql -U your_user -d your_database -c "SELECT dk.refresh_all_mvws();"
```

Schedule this batch file to run daily at 1:00 AM via Task Scheduler.

**Note**: The materialized views are scheduled for daily refresh at 1:00 AM via `03_scheduling_views.sql` (pg_cron) or equivalent pgAgent job.

### 3. Run SQL Scripts

Execute in this order:

```bash
# Connect to PostgreSQL
psql -U your_user -d your_database

# Run core views
\i sql/01_core_views.sql

# Run materialized views
\i sql/02_materialized_views.sql

# Run scheduling setup (optional - requires pg_cron)
\i sql/03_scheduling_views.sql
```

Or from command line:

```bash
psql -U your_user -d your_database -f sql/01_core_views.sql
psql -U your_user -d your_database -f sql/02_materialized_views.sql
psql -U your_user -d your_database -f sql/03_scheduling_views.sql
```

# Install PostGIS
To install PostGIS for PostgreSQL 18 on Windows 11, the most straightforward method is using the Stack Builder utility, which is included by default with the EDB PostgreSQL installer. 
1. Download and Install PostgreSQL 18 
Source: Visit the Official PostgreSQL Windows Downloads page and select the installer for version 18.
Installation: Run the .exe file. Ensure that Stack Builder is selected in the "Select Components" step.
Configuration: Follow the prompts to set your installation directory, data directory, and a super-user password (keep this password safe as you will need it later). 
2. Launch Stack Builder
Once the PostgreSQL installation finishes, a prompt will ask if you want to launch Stack Builder. Check the box and click Finish.
Alternatively, you can open it later by searching for "Stack Builder" in your Windows Start menu.
Select your PostgreSQL 18 installation from the dropdown menu and click Next. 
3. Select and Install PostGIS
Find Extension: Expand the Spatial Extensions category.
Select PostGIS: Choose the latest available PostGIS Bundle (e.g., PostGIS 3.6.2 or 3.7.0dev, depending on the exact minor version available for PG 18).
Download & Run: Stack Builder will download the PostGIS installer. Click Next to run it.
PostGIS Wizard: Accept the license agreement and keep the default components selected. When asked, enter your PostgreSQL super-user password. 
4. Enable PostGIS in your Database 
After the installation is complete, you must manually enable the extension for each database where you want to use spatial features: 
Open pgAdmin 4 (installed with PostgreSQL).
Connect to your server and select your target database.
Open the Query Tool and run the following command:
sql
CREATE EXTENSION postgis;
To verify the installation, run:
sql
SELECT dk.postgis_full_version();


### 4. Install Python Dependencies

```bash
# From project root
cd ../..
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Test Database Connection

```bash
cd python
python database.py
```

### 6. Run Unit Tests

```bash
cd python

# Run all tests (requires live database)
pytest test_database.py -v
```

## Dependencies

- PostgreSQL 12+ with pg_cron extension (Linux/macOS) or pgAgent (Windows)
- Python 3.9+
- Required packages: See `../../requirements.txt`

## Implementation Progress

### Completed

1. **Core Views** (`01_core_views.sql`)
   - 8 analytical views created
   - Fixed duplicate key issues with `DISTINCT ON`
   - Aggregated collection_report to prevent join explosion

2. **Materialized Views** (`02_materialized_views.sql`)
   - 7 materialized views with indexes
   - `refresh_all_mvws()` function for batch refresh
   - Fixed data type casting for PostgreSQL `name` type

3. **Cross-Platform Scheduling** (`03_scheduling_views.sql`)
   - Auto-detects OS (Windows vs Linux/macOS)
   - Configures pg_cron for Linux/macOS
   - Configures pgAgent for Windows
   - Graceful handling when extensions not installed

4. **Python Utilities**
   - `database.py`: Connection management, query execution, data quality checks
   - `setup.py`: Configuration management, path resolution
   - `test_database.py`: Comprehensive test suite with mocking

5. **Test Suite**
   - 40+ unit tests with mocked database
   - 4 integration tests requiring live database
   - Auto-loading of `.env` file for test configuration

## Lessons Learned

### Database Schema Issues

**Problem**: Materialized view creation failed with "duplicate key" errors.

**Root Cause**: 
- Patient table had duplicate `mrn` values
- Collection table had duplicate `row_number` values
- LEFT JOIN with `collection_report` created multiple rows per collection

**Solution**: 
- Added `DISTINCT ON (p.mrn)` to `vw_patient_enriched`
- Added `DISTINCT ON (c.row_number)` to `vw_transaction_flat`
- Created CTE to aggregate `collection_report` before joining

### Data Type Mismatches

**Problem**: `refresh_all_mvws()` function failed with "returned type name does not match expected type text".

**Root Cause**: PostgreSQL's internal `name` type (for `matviewname`) doesn't automatically cast to `TEXT` in RETURN QUERY.

**Solution**: Added explicit `::TEXT` cast: `mvw_record.matviewname::TEXT`

### Cross-Platform Scheduling

**Problem**: pg_cron not available on Windows, pgAgent has complex setup.

**Solution**: 
- Created OS detection function using `dynamic_shared_memory_type` from `pg_settings`
- Separate code paths for pg_cron (Linux/macOS) and pgAgent (Windows)
- Detailed setup instructions for both platforms

### Environment Variable Issues

**Problem**: Connection failures due to trailing spaces in environment variables from `.env` file.

**Root Cause**: Windows shell or text editors adding whitespace.

**Solution**: Added `.strip()` to all `os.getenv()` calls in `database.py`.

### Test Isolation

**Problem**: Integration tests failed with "cursor already closed" error.

**Root Cause**: Using `return_df=False` with `fetchone()` after connection context exits.

**Solution**: Changed to use DataFrame results (`return_df=True`) throughout `check_data_quality()`.

### pgAgent Schedule Format

**Problem**: pgAgent schedule insertion failed with array size constraint violations.

**Root Cause**: 
- `jscminutes` requires exactly 60 boolean elements
- `jschours` requires exactly 24 boolean elements
- Arrays must use boolean format `{t,f}` not integers `{0,1}`

**Solution**: Corrected array sizes and formats:
```sql
-- Minute 0 (Exactly 60 boolean values)
'{t,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f}'
```

## Next Steps

After ST-01 is complete, proceed to **ST-02: Sales & Revenue Analytics**.

## Troubleshooting

### Views Not Found

Ensure you're connected to the correct database and schema:

```sql
SELECT current_database();
SELECT current_schema();
```

### pg_cron Not Available

If pg_cron is not installed, you can manually refresh views:

```sql
SELECT dk.refresh_all_mvws();
```

Or refresh individually:

```sql
REFRESH MATERIALIZED VIEW dk.mvw_patient_enriched;
```

### Python Import Errors

Ensure all dependencies are installed:

```bash
pip install pandas numpy sqlalchemy psycopg2-binary python-dotenv
```
