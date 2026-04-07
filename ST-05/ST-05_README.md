# ST-05: AI/ML Predictive Engine

## Overview

ST-05 implements an AI/ML Predictive Engine with four XGBoost models that score every patient daily, enabling personalized outreach through Power BI dashboards.

**Architecture:** SQL-first feature engineering with materialized views for caching, Python-based XGBoost training with SHAP interpretability, and dynamic pricing/A/B testing frameworks. Daily incremental scoring at 3 AM with weekly full retrain on Sundays.

**Tech Stack:** PostgreSQL 12+, Python 3.10+, XGBoost 1.7+, scikit-learn 1.2+, SHAP 0.41+, pandas 1.5+, pgAgent for Windows scheduling

---

## Model Architecture

### Four ML Models

| Model | Purpose | Output | Action Mapping |
|-------|---------|--------|----------------|
| **Churn Risk** | Predict patients likely to churn (>180 days inactive) | Probability 0-1 | Low (<0.3), Medium (0.3-0.6), High (>0.6) |
| **Package Upsell** | Predict patients likely to upgrade to packages | Probability 0-1 | Low (<0.4), Warm (0.4-0.7), Hot (>0.7) |
| **NBT (Next Best Treatment)** | Predict category preferences (skincare focus) | Probability 0-1 | Top recommendation: Skincare/Services/Medications/Supplements |
| **Promo Elasticity** | Predict price sensitivity | Probability 0-1 | Organic Loyal (<0.5), Promo-Driven (>0.5) |

### 30+ engineered features including:
- **Recency**: days since last visit, recency bands
- **Frequency**: 30d/90d/12m visit counts, average gap days
- **Monetary**: total revenue, avg/max/std transaction values
- **Tenure**: days/months as customer, cohort month
- **Category Mix**: skincare/services/medications/supplements share
- **Package Behavior**: package revenue ratio, visit ratio
- **Promo Behavior**: discount dependency, average discount %, frequency
- **Financial Stress**: outstanding ratio, stress level
- **RFM Scores**: R/F/M quintiles, segment classification
- **Visit Pattern**: consistency score, preferred branch/channel

---

## File Structure

```
ST-05/
├── sql/
│   ├── 01_ml_features_views.sql      # vw_ml_patient_features, vw_patient_labels
│   ├── 02_dynamic_pricing_views.sql  # vw_dynamic_pricing, vw_ab_assignment
│   ├── 03_materialized_views.sql     # Tables, MVWs, refresh functions
│   └── 04_scheduling.sql             # pgAgent job definitions
├── python/
│   ├── ml_pipeline.py                # XGBoost training, inference, SHAP
│   ├── dynamic_pricing.py            # Pricing engine logic
│   ├── test_ml_features.py           # Feature view tests
│   ├── test_ml_pipeline.py           # Model training/inference tests
│   ├── test_dynamic_pricing.py       # Pricing logic tests
│   └── test_ab_testing.py            # A/B testing tests
└── logs/                             # Execution logs (auto-created)
```

---

## Installation

### Prerequisites

1. **PostgreSQL 12+** with pgAgent extension
2. **Python 3.10+** with pip
3. **ST-01, ST-02, ST-03** infrastructure completed

### Step 1: Install Python Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- xgboost>=1.7.0
- scikit-learn>=1.2.0
- shap>=0.44.0
- pandas>=1.5.0
- numpy>=1.20.0
- scipy>=1.7.0 (for A/B testing)
- sqlalchemy>=1.4.0
- pytest>=7.0.0 (for testing)

### Step 2: Configure Environment Variables

Ensure your `.env` file contains:

```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database
DB_USER=your_username
DB_PASSWORD=your_password
DB_SCHEMA=dk
```

### Step 3: Execute SQL Scripts

Run SQL files in **exact order**:

```bash
# 1. Feature engineering views
psql -U %DB_USER% -d %DB_NAME% -f ST-05/sql/01_ml_features_views.sql

# 2. Dynamic pricing views
psql -U %DB_USER% -d %DB_NAME% -f ST-05/sql/02_dynamic_pricing_views.sql

# 3. Materialized views and tables
psql -U %DB_USER% -d %DB_NAME% -f ST-05/sql/03_materialized_views.sql

# 4. pgAgent scheduling (optional, Windows only)
psql -U %DB_USER% -d %DB_NAME% -f ST-05/sql/04_scheduling.sql
```

---

## Usage Instructions

### Python Modules

#### 1. ML Pipeline (ml_pipeline.py)

**Daily Incremental Scoring** (runs in 3-5 minutes):
```bash
cd ST-05/python
# You need to run a full retrain first to populate the table:
python ml_pipeline.py --mode=retrain
python ml_pipeline.py --mode=incremental
```

**Weekly Full Retrain** (runs in 15-30 minutes, recommended for Sundays):
```bash
python ml_pipeline.py --mode=retrain
```

**Custom Model Version**:
```bash
python ml_pipeline.py --mode=retrain --model-version="20260401_v2"
```

**Command-Line Options**:
- `--mode`: `incremental` (daily scoring) or `retrain` (full retrain)
- `--model-version`: Custom version string (default: timestamp)
- `--forecast-days`: Days to forecast (default: 90)

**Programmatic Usage**:
```python
from ST_01.python.database import get_db_manager
from ST_05.python.ml_pipeline import MLPipeline

# Initialize
db = get_db_manager()
pipeline = MLPipeline(db_manager=db, forecast_days=90)

# Load data
df = pipeline.load_features_and_labels()
train_df, val_df = pipeline.prepare_train_validation_split(df)

# Train all models
pipeline.train_all_models(train_df)

# Compute SHAP values
shap_df = pipeline.compute_shap_values(val_df, model_type='churn')

# Generate predictions
predictions = pipeline.generate_predictions(val_df)

# Save to database
rows_saved = pipeline.save_predictions_to_db(predictions)
```

#### 2. Dynamic Pricing (dynamic_pricing.py)

**Generate All Offers**:
```bash
cd ST-05/python
python dynamic_pricing.py --mode=generate
```

**View Statistics**:
```bash
python dynamic_pricing.py --mode=stats
```

**Get Specific Patient Offer**:
```bash
python dynamic_pricing.py --mrn="PATIENT123"
```

**Filter by Priority** (urgent offers first):
```bash
python dynamic_pricing.py --min-priority=70
```

**Filter by Offer Type**:
```bash
python dynamic_pricing.py --offer-type=discount
```

**Save Offers to Database**:
```bash
python dynamic_pricing.py --save
```

**Command-Line Options**:
- `--mode`: `generate` (create all offers) or `stats` (show statistics)
- `--mrn`: Get offer for specific patient
- `--min-priority`: Filter by minimum priority score (0-100)
- `--offer-type`: Filter by type (discount, bundle, retention, vip_perk, win_back, welcome, standard)
- `--save`: Save offers to database

**Programmatic Usage**:
```python
from ST_01.python.database import get_db_manager
from ST_05.python.dynamic_pricing import PricingEngine

# Initialize
db = get_db_manager()
engine = PricingEngine(db_manager=db)

# Get patient scores
scores = engine.get_patient_scores("PATIENT123")

# Generate offer
offer = engine.get_patient_offer("PATIENT123")
print(f"Offer Type: {offer.offer_type}")
print(f"Discount: {offer.discount_pct}%")
print(f"Max Discount Cap: RM {offer.max_discount_cap}")

# Generate all offers
all_offers = engine.generate_all_offers()

# Filter by priority
urgent_offers = engine.get_offers_by_priority(min_priority=70)

# Filter by type
discount_offers = engine.get_offers_by_type("discount")
```

---

## Configuration Details

### Model Hyperparameters (XGBoost)

```python
XGB_PARAMS = {
    'n_estimators': 100,
    'max_depth': 6,
    'learning_rate': 0.1,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'objective': 'binary:logistic',
    'eval_metric': 'auc',
    'random_state': 42
}
```

### Calibration Method

- **Isotonic Regression**: Ensures predicted probabilities are well-calibrated
- **3-Fold CV**: Used for calibration (sklearn 1.8+ compatible)

### Action Thresholds

| Model | Threshold 1 | Threshold 2 | Bands/Actions |
|-------|-------------|-------------|---------------|
| **Churn** | 0.3 | 0.6 | Low, Medium, High |
| **Upsell** | 0.4 | 0.7 | Low, Warm, Hot |
| **Promo** | 0.5 | - | Organic Loyal, Promo-Driven |

### Discount Caps by Value Tier

| Value Tier | Max Discount (RM) |
|------------|-------------------|
| Premium | 500 |
| High | 300 |
| Medium | 150 |
| Low | 100 |

### Discount Percentages by Offer Type

| Offer Type | Discount Range | Trigger Condition |
|------------|----------------|-------------------|
| discount | 5-25% | promo_elastic_prob > 0.7 |
| bundle | 15% | pkg_upsell_prob > 0.6 |
| retention | 15-20% | churn_probability > 0.7 |
| vip_perk | 10% | Champions/Loyal Customers |
| win_back | 15% | At Risk/Cannot Lose Them |
| welcome | 10% | New Customers |
| standard | 5% | Default |

---

## SQL Tables

### Output Tables

#### dk.dynamic_pricing_offers
Persisted personalized offers generated by the Python pricing engine.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Auto-incrementing primary key |
| mrn | VARCHAR(50) | Patient ID |
| offer_type | VARCHAR(20) | Type (discount/bundle/retention/vip_perk/win_back/welcome/standard) |
| discount_pct | INTEGER | Discount percentage (5-25) |
| max_discount_rm | NUMERIC(10,2) | Maximum discount cap in RM |
| offer_priority | INTEGER | Priority score (0-100, higher = more urgent) |
| recommended_action | TEXT | Recommended outreach action |
| promo_elastic_prob | FLOAT | Promo elasticity probability |
| pkg_upsell_prob | FLOAT | Package upsell probability |
| churn_probability | FLOAT | Churn probability |
| value_tier | VARCHAR(20) | Patient value tier |
| rfm_segment | VARCHAR(50) | RFM segment |
| generated_at | TIMESTAMP | When offer was generated |
| created_at | TIMESTAMP | When record was inserted |

#### dk.ml_predictions
Stores all 4 model predictions per patient.

| Column | Type | Description |
|--------|------|-------------|
| mrn | VARCHAR(50) | Patient ID (Primary Key) |
| prediction_date | DATE | Date of prediction |
| churn_probability | FLOAT | Churn risk score |
| churn_risk_band | VARCHAR(20) | Low/Medium/High |
| pkg_upsell_prob | FLOAT | Package upsell probability |
| upsell_action | VARCHAR(20) | Low/Warm/Hot |
| rec_skincare_prob | FLOAT | Skincare purchase probability |
| rec_services_prob | FLOAT | Services purchase probability |
| rec_medications_prob | FLOAT | Medications purchase probability |
| rec_supplements_prob | FLOAT | Supplements purchase probability |
| top_recommendation | VARCHAR(50) | Primary recommendation |
| promo_elastic_prob | FLOAT | Promo elasticity score |
| promo_segment | VARCHAR(50) | Organic Loyal/Promo-Driven |
| top_feature_1 | VARCHAR(100) | Top SHAP feature |
| top_feature_2 | VARCHAR(100) | Second SHAP feature |
| shap_contribution | FLOAT | SHAP contribution value |
| model_version | VARCHAR(50) | Model version ID |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### dk.model_metadata
Model versions, metrics, and hyperparameters.

| Column | Type | Description |
|--------|------|-------------|
| model_name | VARCHAR(50) | Model type (churn/upsell/nbt/promo) |
| model_version | VARCHAR(50) | Version string |
| train_date | TIMESTAMP | Training timestamp |
| train_end_date | DATE | End date of training data |
| auc_roc | FLOAT | AUC-ROC metric |
| avg_precision | FLOAT | Average precision score |
| positive_samples | INTEGER | Positive class count |
| negative_samples | INTEGER | Negative class count |
| parameters | JSONB | Hyperparameters |
| feature_importance | JSONB | SHAP-based feature importance |
| model_artifact_path | VARCHAR(255) | Optional model file path |
| calibration_method | VARCHAR(50) | Calibration method (isotonic) |

#### dk.ab_results
A/B test statistical results.

| Column | Type | Description |
|--------|------|-------------|
| experiment_name | VARCHAR(100) | Experiment identifier |
| analysis_date | DATE | Analysis date |
| group_a_patients | INTEGER | Control group size |
| group_a_conversions | INTEGER | Control conversions |
| group_a_revenue | NUMERIC(15,2) | Control revenue |
| group_a_conversion_rate | FLOAT | Control conversion rate |
| group_b_patients | INTEGER | Treatment group size |
| group_b_conversions | INTEGER | Treatment conversions |
| group_b_revenue | NUMERIC(15,2) | Treatment revenue |
| group_b_conversion_rate | FLOAT | Treatment conversion rate |
| chi2_statistic | FLOAT | Chi-square statistic |
| p_value | FLOAT | P-value |
| is_significant | BOOLEAN | Significant at α=0.05 |
| relative_lift_pct | FLOAT | Relative lift percentage |
| absolute_lift_pct | FLOAT | Absolute lift percentage |
| confidence_interval_lower | FLOAT | CI lower bound |
| confidence_interval_upper | FLOAT | CI upper bound |

### Materialized Views

#### dk.mvw_ml_patient_features
Cached ML features for fast model training. Refresh daily at 2:00 AM.

#### dk.mvw_ml_predictions
Cached predictions for Power BI with patient context. Refresh after ML pipeline.

#### dk.mvw_dynamic_pricing
Cached dynamic pricing offers. Refresh daily at 2:30 AM.

---

## Scheduling Setup (pgAgent for Windows)

### Prerequisites

1. **Install pgAgent** from https://www.pgadmin.org/download/pgagent-archives/
2. **Verify service running**: Open `services.msc` → "pgAgent" status should be "Running"

### Step 1: Set Environment Variables

Open **System Properties** → **Environment Variables** → **System variables**:

| Variable Name | Value |
|---------------|-------|
| PYTHON_PATH | `C:\Python310\python.exe` (adjust to your Python path) |
| ML_PIPELINE_PATH | `D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py` |

**Restart pgAgent service** after setting variables.

### Step 2: Execute Scheduling SQL

```bash
psql -U %DB_USER% -d %DB_NAME% -f ST-05/sql/04_scheduling.sql
```

### Jobs Created

| Job Name | Schedule | Purpose | Duration |
|----------|----------|---------|----------|
| **ST-05 Daily Incremental Scoring** | Daily at 3:00 AM | Score all patients | 3-5 min |
| **ST-05 Weekly Full Retrain** | Sunday at 2:00 AM | Retrain all 4 models | 15-30 min |

### Verification Queries

```sql
-- List all ST-05 jobs
SELECT * FROM pgagent.pga_job WHERE jobname LIKE 'ST-05%';

-- List schedules
SELECT j.jobname, s.schname, s.schstart, s.schdays 
FROM pgagent.pga_schedule s 
JOIN pgagent.pga_job j ON s.schjobid = j.jobid 
WHERE j.jobname LIKE 'ST-05%';

-- Check execution history
SELECT * FROM dk.vw_ml_job_execution_summary;

-- Check for failures (last 24 hours)
SELECT * FROM dk.check_ml_job_failures();

-- Manual test execution
SELECT dk.trigger_incremental_scoring();
SELECT dk.trigger_full_retrain();
```

### Monitoring Views

| View | Purpose |
|------|---------|
| `dk.vw_ml_job_execution_summary` | Aggregated stats by job and status |
| `dk.vw_ml_job_latest_status` | Latest execution status for each job |
| `dk.ml_job_execution_log` | Raw execution log table |

### Helper Functions

| Function | Purpose |
|----------|---------|
| `dk.run_ml_incremental_scoring()` | Wrapper for daily scoring |
| `dk.run_ml_full_retrain()` | Wrapper for weekly retrain |
| `dk.check_ml_job_failures()` | Returns failed jobs for alerting |
| `dk.trigger_incremental_scoring()` | Manual trigger for testing |
| `dk.trigger_full_retrain()` | Manual trigger for testing |

---

## Troubleshooting

### Common Issues

#### 1. SQL View Errors

**Error**: "relation 'dk.vw_ml_patient_features' does not exist"
- **Solution**: Execute `01_ml_features_views.sql` first
- Verify: `SELECT * FROM information_schema.tables WHERE table_schema='dk' AND table_name='vw_ml_patient_features';`

**Error**: "COALESCE types integer and boolean cannot be matched"
- **Solution**: Check boolean vs integer type mismatch. Use `1/0` instead of `TRUE/FALSE` in PostgreSQL views.

**Error**: "column 'has_package_flag' is of type boolean but expression is of type integer"
- **Solution**: Cast explicitly: `has_package_flag::INTEGER` or use `CASE WHEN...THEN 1 ELSE 0 END`

#### 2. Python Import Errors

**Error**: "ModuleNotFoundError: No module named 'ST_01'"
- **Solution**: Ensure you're running from the correct directory or add project root to PYTHONPATH:
  ```bash
  export PYTHONPATH=D:\dev\healthcare_poc_bi
  ```

**Error**: "No module named 'shap'"
- **Solution**: `pip install shap>=0.44.0`

#### 3. Database Connection Errors

**Error**: "FATAL: password authentication failed for user"
- **Solution**: Verify `.env` file credentials match PostgreSQL setup

**Error**: "relation 'dk.mvw_ml_patient_features' does not exist"
- **Solution**: Refresh materialized view:
  ```sql
  REFRESH MATERIALIZED VIEW dk.mvw_ml_patient_features;
  ```

#### 4. pgAgent Issues

**Error**: "pgAgent extension not found"
- **Solution**: 
  ```sql
  CREATE EXTENSION pgagent;  -- Requires superuser
  ```

**Error**: "Jobs not executing"
- Verify pgAgent service: `services.msc`
- Check pgAgent logs in PostgreSQL log directory
- Verify PYTHON_PATH and ML_PIPELINE_PATH environment variables
- Restart pgAgent service after changing environment variables

**Error**: "Python script not found"
- Use absolute paths in job step commands
- Test manually: `python D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py --mode=incremental`

#### 5. Model Training Issues

**Warning**: "ALERT: churn AUC (0.62) below threshold (0.65)"
- **Cause**: Insufficient positive samples or weak signal in features
- **Solution**: 
  - Check sample size: minimum 200 positive samples required
  - Review feature engineering for data quality issues
  - Consider extending training period or adjusting class weights

**Warning**: "Insufficient positive samples for upsell: 150 < 200"
- **Solution**: Expand training data window or relax label definition

#### 6. SHAP Computation Errors

**Error**: "SHAP computation failed" for sklearn 1.8+
- **Solution**: The code handles sklearn version differences automatically:
  ```python
  if hasattr(calibrated_model, 'estimator'):
      base_model = calibrated_model.estimator  # sklearn 1.8+
  elif hasattr(calibrated_model, 'estimators_'):
      base_model = calibrated_model.estimators_[0]
  ```
- Verify XGBoost and SHAP versions are compatible

### Logs Location

Execution logs are written to:
```
ST-05/logs/
  ├── incremental_scoring_YYYY-MM-DD.log
  └── full_retrain_YYYY-MM-DD.log
```

### Permission Issues

**Error**: "permission denied for table ml_predictions"
- **Solution**:
  ```sql
  GRANT ALL ON dk.ml_predictions TO healthcare_bi_app;
  GRANT ALL ON dk.model_metadata TO healthcare_bi_app;
  GRANT ALL ON dk.ab_results TO healthcare_bi_app;
  GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA dk TO healthcare_bi_app;
  ```

### Performance Optimization

**Slow materialized view refresh**:
- Ensure unique indexes exist for CONCURRENTLY refresh
- Analyze table statistics: `ANALYZE dk.mvw_ml_patient_features;`
- Consider partitioning large tables

**High memory usage during training**:
- Reduce sample_size parameter in `compute_shap_values()` (default: 1000)
- Train models sequentially instead of in parallel
- Use XGBoost with `tree_method='hist'` for memory efficiency

---

## Testing

### Run All Tests

```bash
cd ST-05/python
pytest . -v
```

### Test Individual Modules

```bash
# Feature views
pytest test_ml_features.py -v

# ML pipeline
pytest test_ml_pipeline.py -v

# Dynamic pricing
pytest test_dynamic_pricing.py -v

# A/B testing
pytest test_ab_testing.py -v
```

### Expected Test Results

- **Feature views**: 3/3 tests PASS
- **ML pipeline**: 16/17 tests PASS (1 integration test may skip if views missing)
- **Dynamic pricing**: 46/46 tests PASS
- **A/B testing**: 6/23 tests PASS (others skip gracefully without database objects)

---

## Integration with Power BI

### Data Sources for Dashboards

Connect Power BI to these materialized views:

| View | Purpose |
|------|---------|
| `dk.mvw_ml_predictions` | Patient predictions with RFM segments |
| `dk.mvw_dynamic_pricing` | Personalized offers |
| `dk.vw_ml_job_execution_summary` | ML pipeline monitoring |

### Recommended Visualizations

1. **Churn Risk Dashboard**:
   - Patients by risk band (Low/Medium/High)
   - Top 100 high-risk patients list
   - SHAP feature importance chart

2. **Package Upsell Dashboard**:
   - Warm/Hot prospects by branch
   - Package penetration rate trend
   - Revenue uplift from upsell campaigns

3. **Promo Elasticity Dashboard**:
   - Promo-Driven vs Organic Loyal distribution
   - Discount spend optimization
   - A/B test results visualization

---

## Next Steps

1. ✅ Complete SQL view creation
2. ✅ Complete Python module implementation
3. ✅ Complete pgAgent scheduling setup
4. ✅ **ML pipeline end-to-end verified** — 3 models trained, 3,558 predictions saved
5. ✅ **Dynamic pricing end-to-end verified** — 3,558 offers generated
6. ⏳ **Configure Power BI dashboards** (future task)
7. ⏳ **Deploy to production** (future task)
8. ⏳ **Monitor model drift and retrain quarterly** (ongoing)

---

## Verified Results (2026-04-02)

### ML Pipeline Performance

| Model | AUC-ROC | Status |
|-------|---------|--------|
| Churn Risk | 0.8663 | ✅ Above 0.65 threshold |
| Package Upsell | 0.9041 | ✅ Above 0.65 threshold |
| Promo Elasticity | 0.9852 | ✅ Above 0.65 threshold |

- **Predictions saved:** 3,558 unique patients
- **Metadata records:** 3 (one per model)
- **Total runtime:** 13.9 seconds (SHAP batch computation)

### Dynamic Pricing Performance

- **Offers generated:** 3,558
- **Average discount:** 13.2%
- **High-priority offers:** 52

| Offer Type | Count |
|------------|-------|
| bundle | 944 |
| vip_perk | 835 |
| retention | 648 |
| standard | 639 |
| win_back | 227 |
| discount | 224 |
| welcome | 41 |

### Key Implementation Notes

1. **SHAP batch computation:** Uses `explainer.shap_values(X)` for all patients at once (~5s) instead of per-patient loops (~10min timeout)
2. **Bulk database insert:** Uses pandas `to_sql()` within the same transaction as the DELETE operation to prevent duplicate key errors
3. **Object dtype encoding:** Categorical string columns (e.g., `stress_level`) are encoded via `.astype('category').cat.codes` before XGBoost training
4. **Deduplication:** Predictions are deduplicated by MRN and filtered for empty values before database insertion

---

## References

- **Plan Document**: `docs/superpowers/plans/2026-03-31-st05-ml-predictive-engine.md`
- **Learnings Log**: `.sisyphus/notepads/2026-03-31-st05-ml-predictive-engine/learnings.md`
- **ST-01 Foundation**: `ST-01/README.md`
- **XGBoost Documentation**: https://xgboost.readthedocs.io/
- **SHAP Documentation**: https://shap.readthedocs.io/
- **scikit-learn Calibration**: https://scikit-learn.org/stable/modules/calibration.html
