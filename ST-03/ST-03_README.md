# ST-03: Patient Intelligence

## Overview

ST-03 implements Patient Intelligence Analytics for the Healthcare Analytics Business Intelligence solution. This sub-task creates patient-focused views for D+3 follow-up tracking, risk classification, RFM segmentation, cohort retention analysis, visit frequency distribution, and CLTV predictions.

## Prerequisites

**ST-01 must be completed before ST-03.** ST-03 reuses the database utilities from ST-01:
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

ST-03 SQL views use the actual column names from dk schema tables:

| Actual Table Column | Description | Source Table |
|--------------------|-------------|--------------|
| `dob` | Patient date of birth | dk.patient |
| `city_name` | Patient city | dk.patient |
| `state_name` | Patient state | dk.patient |
| `date` | Transaction date | dk.collection |
| `amount_collected` | Transaction amount | dk.collection |
| `row_number` | Collection row ID (PK) | dk.collection |
| `mrn` | Medical Record Number | dk.patient, dk.collection |

**Note**: Python code aliases `date` → `transaction_date` and `amount_collected` → `amount` for compatibility with lifetimes library.

## Files Created

### SQL Files

| File | Description | Views Created |
|------|-------------|---------------|
| `01_patient_intelligence_views.sql` | Patient analytics views | 8 views |
| `02_materialized_views.sql` | Materialized views with indexes | 7 MVWs + 2 tables |

### Python Files

| File | Description |
|------|-------------|
| `patient_analytics.py` | Patient analytics queries and reports |
| `test_patient_analytics.py` | Test suite for patient_analytics (35 tests) |
| `cltv_model.py` | BG/NBD + Gamma-Gamma CLTV prediction pipeline |
| `test_cltv_model.py` | Test suite for cltv_model (11 tests) |

## Views Reference

### Patient Intelligence Views (01_patient_intelligence_views.sql)

| View | Purpose |
|------|---------|
| `vw_followup_d3` | D+3 callback tracker with patient contact info and status |
| `vw_patient_risk` | Patient risk classification (ACTIVE/AT RISK/HIGH RISK/LOST) |
| `vw_patient_rfm_ntile` | RFM segmentation with NTILE(5) quintile scoring |
| `vw_cohort_retention` | Monthly cohort retention analysis with churn rates |
| `vw_visit_frequency` | Individual patient visit frequency distribution |
| `vw_visit_frequency_summary` | Branch-level visit frequency summaries |
| `vw_patient_dashboard` | Executive patient dashboard KPIs |

### Materialized Views (02_materialized_views.sql)

| Materialized View | Refresh Schedule | Purpose |
|-------------------|------------------|---------|
| `mvw_patient_risk` | Daily 2:00 AM | Patient risk classifications with indexes |
| `mvw_patient_rfm_ntile` | Daily 2:00 AM | RFM scores and segments |
| `mvw_cohort_retention` | Daily 2:00 AM | Cohort retention statistics |
| `mvw_visit_frequency` | Daily 2:00 AM | Visit frequency analysis |
| `mvw_visit_frequency_summary` | Daily 2:00 AM | Branch-level frequency summaries |
| `mvw_patient_dashboard` | Daily 2:00 AM | Executive dashboard data |
| `mvw_patient_ltv_predictions` | Daily 2:00 AM | BG/NBD + Gamma-Gamma CLTV predictions |

### Tables Created

| Table | Purpose |
|-------|---------|
| `dk.patient_ltv_predictions` | Stores Python-generated CLTV predictions |
| `dk.lt_v_model_runs` | Tracks model versions and metadata |

## Risk Classification Logic

### Status Definitions

| Status | Days Since Last Visit | Description |
|--------|----------------------|-------------|
| ACTIVE | 0-21 days | Currently engaged patients |
| AT RISK | 22-45 days | Showing signs of disengagement |
| HIGH RISK | 46-90 days | At risk of being lost |
| LOST | >90 days | No recent activity |

### Status Transition Thresholds

```sql
CASE
    WHEN days_since_visit <= 21 THEN 'ACTIVE'
    WHEN days_since_visit <= 45 THEN 'AT RISK'
    WHEN days_since_visit <= 90 THEN 'HIGH RISK'
    ELSE 'LOST'
END
```

## RFM Segmentation

### NTILE(5) Scoring

| Score | Recency (R) | Frequency (F) | Monetary (M) |
|-------|-------------|---------------|--------------|
| 5 | Most recent | Highest frequency | Highest value |
| 4 | Recent | Frequent | High value |
| 3 | Moderate | Moderate | Moderate |
| 2 | Less recent | Infrequent | Low value |
| 1 | Least recent | Least frequent | Lowest value |

### RFM Segment Mapping

| Segment | R Score | F Score | M Score | Description |
|---------|---------|---------|---------|-------------|
| Champions | 4-5 | 4-5 | 4-5 | Best customers |
| Loyal Customers | 4-5 | 2-3 | 4-5 | Regular high-value |
| Potential Loyalists | 4-5 | 2-3 | 2-3 | Recent but not frequent |
| At Risk | 1-2 | 4-5 | 4-5 | Were valuable, now inactive |
| Hibernating | 1-2 | 1-2 | 4-5 | Used to be valuable |
| Lost | 1-2 | 1-2 | 1-2 | Inactive, low value |

## Cohort Retention Analysis

### Cohort Definition

- **Cohort**: Patients who made their first visit in a given month
- **Cohort Size**: Count of unique patients in the cohort
- **Retention**: Patients with at least one visit in subsequent months
- **Churn**: Patients with no visits in a given month

### Key Metrics

| Metric | Description |
|--------|-------------|
| `retention_rate_pct` | (Active patients / Cohort size) × 100 |
| `churn_rate_pct` | (Churned patients / Cohort size) × 100 |
| `avg_revenue_per_patient` | Cumulative revenue / Active patients |
| `ltv_estimate` | Projected lifetime value for the cohort |

### Retention Benchmarks

| Months Since Signup | Healthy Retention |
|--------------------|------------------|
| M0 (Signup) | 100% |
| M3 | 70-85% |
| M6 | 55-70% |
| M12 | 40-55% |
| M24 | 25-40% |

## Visit Frequency Distribution

### Frequency Segments

| Segment | Visits/Year | Description |
|---------|-------------|-------------|
| Frequent | ≥12 | Weekly or more regular visits |
| Regular | 6-11 | Monthly visits |
| Occasional | 3-5 | Quarterly visits |
| Rare | 1-2 | Infrequent visits |
| One-time | 1 | Single visit only |

### Key Metrics

| Metric | Description |
|--------|-------------|
| `avg_days_between_visits` | Mean days between consecutive visits |
| `std_days_between_visits` | Standard deviation for visit intervals |
| `max_days_between_visits` | Longest gap between visits |
| `visits_per_year` | Annualized visit frequency |

## Patient Lifetime Value (CLTV)

### BG/NBD Model

Uses Beta-Geometric/Negative Binomial Distribution model for transaction frequency.

**Input Features**:

| Parameter | Description |
|-----------|-------------|
| `frequency` | Number of repeat transactions |
| `recency` | Time between first and last transaction (days) |
| `T` | Time since first transaction (days) |
| `monetary_value` | Average transaction value |

**Trained Parameters (Real Data)**:

| Parameter | Value |
|-----------|-------|
| `r` | 1.20 |
| `alpha` | 43.29 |
| `a` | 0.05 |
| `b` | 0.53 |

### Gamma-Gamma Model

Predicts expected transaction value based on:
- Historical transaction values
- Transaction frequency patterns
- Probability of being "alive" (active customer)

**Trained Parameters (Real Data)**:

| Parameter | Value |
|-----------|-------|
| `p` | 3.65 |
| `q` | 0.31 |
| `v` | 3.59 |

### CLTV Predictions

| Prediction | Timeframe |
|------------|-----------|
| `predicted_purchases_next_90d` | Expected transactions in next 90 days |
| `predicted_avg_order_value` | Estimated average transaction value |
| `predicted_clv_12m` | Projected value over 12 months |
| `predicted_clv_24m` | Projected value over 24 months |
| `probability_alive` | Likelihood patient is still active (0-1) |

**Column Names**: Use `predicted_clv_*` (CLV), not `predicted_cltv_*` (CLTV) in queries.

### LTV Segments

Actual tier distribution from pipeline results (2,689 patients):

| Segment | Count | Predicted CLV (24m) Range | Description |
|---------|-------|--------------------------|-------------|
| PREMIUM | 5 | >₱5,000 | Highest value patients |
| HIGH | 27 | ₱3,000-₱5,000 | Above average value |
| MEDIUM | 587 | ₱500-₱3,000 | Moderate value |
| LOW | 2,070 | <₱500 | Lower value |

**Average Statistics (Real Data)**:
- Avg 12m CLV: ₱166.96
- Avg 24m CLV: ₱333.73
- Avg probability alive: 82.9%

**Top PREMIUM Patients**:
| MRN | 24m CLV | Probability Alive |
|-----|---------|-------------------|
| SG0300983 | ₱8,153 | 97.4% |
| SG2400031 | ₱6,125 | 99.8% |
| SG0700305 | ₱5,059 | 99.9% |

## Python Modules

### Python Import Path

ST-03 Python modules import from `ST-01/python/database`:

```python
# In cltv_model.py
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ST-01" / "python"))
from database import DatabaseManager, get_db_manager
```

### PatientAnalyticsManager Class

```python
from ST_03.python.patient_analytics import PatientAnalyticsManager

# Initialize manager
manager = PatientAnalyticsManager()

# Get D+3 follow-up list (callback queue)
followups = manager.get_followup_d3(branch="Branch_A")

# Get patient risk distribution
risk_summary = manager.get_risk_distribution()

# Get patients by risk status
at_risk = manager.get_patient_risk_summary(risk_status="AT RISK")

# Get RFM segmentation
rfm_segments = manager.get_rfm_segmentation()

# Get RFM summary
rfm_summary = manager.get_rfm_summary()

# Get cohort retention
cohorts = manager.get_cohort_retention()
cohort_summary = manager.get_cohort_summary()

# Get visit frequency distribution
freq_dist = manager.get_visit_frequency_distribution()

# Get CLTV predictions
ltv_predictions = manager.get_ltv_predictions()
ltv_summary = manager.get_ltv_summary()

# Get executive dashboard
dashboard = manager.get_executive_dashboard()

# Check data freshness
freshness = manager.check_data_freshness()

# Refresh materialized views
refresh_status = manager.refresh_patient_intelligence()
```

### Generate Patient Report

```python
from ST_03.python.patient_analytics import generate_patient_report

# Generate different report types
executive = generate_patient_report(report_type="executive")
risk = generate_patient_report(report_type="risk")
rfm = generate_patient_report(report_type="rfm")
ltv = generate_patient_report(report_type="ltv")
cohort = generate_patient_report(report_type="cohort")
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

# Run patient intelligence views
\i sql/01_patient_intelligence_views.sql

# Run materialized views
\i sql/02_materialized_views.sql
```

### 3. Install Python Dependencies

```bash
pip install pandas numpy sqlalchemy psycopg2-binary python-dotenv

# Required for CLTV modeling
pip install lifetimes scikit-learn
```

### 4. Test Patient Analytics

```bash
cd python

# Run patient analytics tests (35 tests)
pytest test_patient_analytics.py -v

# Run CLTV model tests (11 tests)
pytest test_cltv_model.py -v
```

### 5. Run Patient Analytics Report

```bash
cd python
python patient_analytics.py
```

### 6. Run CLTV Pipeline

```bash
cd python
python cltv_model.py
```

**Expected Output**:
```
Loading transaction data from dk.collection...
Loaded 46,522 transactions
Preparing RFM features for 2,689 patients...
Training BG/NBD model...
  Parameters: r=1.20, alpha=43.29, a=0.05, b=0.53
Training Gamma-Gamma model...
  Parameters: p=3.65, q=0.31, v=3.59
Predicting CLV for 12 and 24 months...
Saving 2,689 predictions to dk.patient_ltv_predictions...
Refreshing mvw_patient_ltv_predictions...
Pipeline complete!
```

## Scheduling

### Daily Materialized View Refresh

The patient intelligence materialized views can be refreshed daily:

```python
from ST_03.python.patient_analytics import PatientAnalyticsManager

manager = PatientAnalyticsManager()
refresh_status = manager.refresh_patient_intelligence()
print(refresh_status)
```

### Cross-Platform Scheduling (from ST-01)

Use the `detect_os()` function from ST-01 for platform-specific scheduling:
- **Linux/macOS**: pg_cron
- **Windows**: pgAgent or Windows Task Scheduler

## Key Constraints

1. **Patient PK**: `location` (not `mrn` - MRNs can be duplicated)
2. **Collection PK**: `row_number` (auto-increment)
3. **Schema**: All objects in `dk` schema
4. **Source Tables**: `dk.collection`, `dk.patient`
5. **Date Field**: `date` (not `transaction_date`)
6. **Amount Field**: `amount_collected` (not `net_amount`)
7. **Patient DOB**: `dob` (not `date_of_birth`)
8. **Patient Location**: `city_name`, `state_name` (not `city`, `state`)
9. **Environment Variables**: Use `DB_*` (standardized)
10. **Python Imports**: Use `ST-01/python/database`
11. **CLV Column Names**: `predicted_clv_*` (not `predicted_cltv_*`)
12. **Duplicate MRN Handling**: Use `DISTINCT ON (mrn)` in views

## Patient Dashboard KPIs

| Metric | Description | Target |
|--------|-------------|--------|
| Total Patients | Count of unique patients | Track growth |
| Active Patients | Patients with visits in last 21 days | >70% of total |
| At Risk Patients | Patients inactive 22-45 days | <15% of total |
| High Risk Patients | Patients inactive 46-90 days | <10% of total |
| Lost Patients | Patients inactive >90 days | <10% of total |
| Churn Rate | % of patients lost in last 90 days | <5% monthly |
| Avg Visit Frequency | Mean days between visits | <30 days |
| Avg Lifetime Value | Mean patient LTV | >$2,000 |

## Executive Dashboard Insights

### Risk Distribution Health Check

| Status | Target % | Action if Above Target |
|--------|----------|----------------------|
| ACTIVE | >70% | Maintain engagement programs |
| AT RISK | <15% | Trigger retention campaigns |
| HIGH RISK | <10% | Personal outreach |
| LOST | <10% | Win-back campaigns |

### RFM Segment Priorities

| Segment | Priority | Recommended Action |
|---------|----------|-------------------|
| Champions | High | VIP treatment, referrals |
| At Risk | Critical | Retention campaigns |
| Lost | Medium | Win-back offers |
| Hibernating | Medium | Reactivation campaigns |

## Dependencies

- **PostgreSQL 12+** with materialized view support
- **Python 3.9+**
- **pandas, numpy** (data manipulation)
- **sqlalchemy, psycopg2-binary** (database connectivity)
- **lifetimes** (optional, for CLTV modeling)

## Troubleshooting

### Patient Views Return Empty Results

Check source data:
```sql
SELECT COUNT(*) FROM dk.patient;
SELECT COUNT(*) FROM dk.collection;
SELECT MIN(date), MAX(date) FROM dk.collection;
```

### D+3 Follow-Up Shows No Results

Verify patients with visits 3 days ago:
```sql
SELECT COUNT(*) FROM dk.vw_followup_d3
WHERE followup_status = 'DUE FOR CALLBACK';
```

### RFM Scores Look Unusual

Check data distribution:
```sql
SELECT 
    MIN(recency_days), MAX(recency_days),
    MIN(frequency), MAX(frequency),
    MIN(monetary), MAX(monetary)
FROM dk.vw_patient_rfm_ntile;
```

### Cohort Retention Shows 100% Drop

Verify patient linkage:
```sql
SELECT COUNT(DISTINCT mrn) FROM dk.collection;
SELECT COUNT(*) FROM dk.patient;
```

### Materialized View Refresh Fails

Refresh manually:
```sql
SELECT dk.refresh_patient_intelligence_mvws();
```

Or individually:
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_patient_risk;
REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_patient_rfm_ntile;
```

## Next Steps

ST-03 is complete. This provides comprehensive patient intelligence analytics for:
- D+3 follow-up callback scheduling
- Proactive risk management and retention
- Customer segmentation (RFM)
- Cohort-based retention analysis
- CLTV prediction and optimization

The patient intelligence layer integrates with ST-02 (Sales Analytics) to provide complete visibility into patient behavior and revenue contribution.
