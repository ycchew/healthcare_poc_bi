# Healthcare Analytics Business Intelligence Platform

## Enterprise Healthcare Intelligence Solution

---

## Executive Summary

This Healthcare Analytics Business Intelligence Platform is a comprehensive, enterprise-grade solution designed to transform raw healthcare transaction data into actionable business intelligence. The platform enables data-driven decision-making across patient management, revenue optimization, predictive analytics, geospatial intelligence, and automated patient engagement.

### Business Value Proposition

| Capability | Business Impact |
|------------|-----------------|
| **Patient Intelligence** | Proactive retention, reducing churn by identifying at-risk patients before they disengage |
| **Revenue Forecasting** | 90-day Prophet-based forecasting with Malaysian holiday integration for accurate planning |
| **ML Predictive Engine** | 4 XGBoost models scoring every patient daily for personalized outreach |
| **Geospatial Analytics** | Branch catchment analysis, cannibalization detection, and expansion whitespace identification |
| **Automated Campaigns** | WhatsApp-based patient communication with PDPA-compliant consent management |
| **Dynamic Pricing** | Personalized discount offers based on patient value tiers and promo elasticity |

### Key Metrics

- **3,558+ patients** scored daily by ML models
- **90-day revenue forecasts** with AUC > 0.85
- **30+ engineered features** per patient for ML
- **7 interactive maps** for geospatial visualization
- **7 campaign types** for automated patient engagement

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    Healthcare Analytics Business Intelligence Platform                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                        DATA LAYER (PostgreSQL + PostGIS)                     │    │
│  ├─────────────────────────────────────────────────────────────────────────────┤    │
│  │  Source Tables: dk.patient, dk.collection, dk.collection_report             │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ ST-01: Core Views + Materialized Views + DatabaseManager            │   │    │
│  │  │ • 8 analytical views • 7 materialized views • RFM segmentation       │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ ST-02: Sales Views + Prophet Forecasting + Festival Analysis        │   │    │
│  │  │ • 4 sales views • 4 calendar views • 7 MVWs • malaysian_holidays     │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ ST-03: Patient Intelligence + CLTV + Cohort Retention               │   │    │
│  │  │ • 7 patient views • 7 MVWs • BG/NBD + Gamma-Gamma CLTV               │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ ST-04: Product & Package Performance + Payment Behavior             │   │    │
│  │  │ • 13 views • 7 MVWs • Package composition • Affordability stress     │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ ST-05: ML Predictive Engine + Dynamic Pricing                       │   │    │
│  │  │ • 30+ features • 4 XGBoost models • SHAP interpretability            │   │    │
│  │  │ • Churn risk, Package upsell, NBT, Promo elasticity                  │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ ST-06: Geospatial Analytics + PostGIS                               │   │    │
│  │  │ • Azure Maps geocoding • DBSCAN clustering • Cannibalization         │   │    │
│  │  │ • 7 views • 6 MVWs • 7 interactive maps                              │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ ST-07: Automation & Campaigns (WhatsApp Cloud API)                  │   │    │
│  │  │ • 5 tables • 3 views • 7 campaign types • PDPA compliance            │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                    │                                                 │
│                                    ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                     PYTHON ANALYTICS LAYER                                   │    │
│  ├─────────────────────────────────────────────────────────────────────────────┤    │
│  │  ST-01/python/database.py         → DatabaseManager (shared utility)        │    │
│  │  ST-02/python/sales_forecast.py   → Prophet 90-day forecasting              │    │
│  │  ST-03/python/cltv_model.py       → BG/NBD + Gamma-Gamma CLTV                │    │
│  │  ST-04/python/product_analytics.py→ Product & Package analytics              │    │
│  │  ST-05/python/ml_pipeline.py      → XGBoost training + SHAP                  │    │
│  │  ST-05/python/dynamic_pricing.py  → Personalized discount engine             │    │
│  │  ST-06/python/geocoding_pipeline.py→ Azure Maps + Nominatim fallback         │    │
│  │  ST-06/python/geo_analysis.py     → DBSCAN + Cannibalization + Maps          │    │
│  │  ST-07/python/campaign_manager.py → WhatsApp campaign orchestration          │    │
│  │  ST-07/python/webhook_handler.py  → FastAPI event-driven webhooks            │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                    │                                                 │
│                                    ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                     VISUALIZATION & OUTPUT                                   │    │
│  ├─────────────────────────────────────────────────────────────────────────────┤    │
│  │  Power BI Dashboards  → Materialized views (DirectQuery/Import)             │    │
│  │  7 Folium Maps        → Interactive HTML maps (ST-06/maps/)                  │    │
│  │  WhatsApp Cloud API   → Patient communication (ST-07)                        │    │
│  │  pgAgent Jobs         → Windows scheduling (22 scheduled jobs)               │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Overview

### ST-01: Data Foundation & Infrastructure

**Purpose**: Establishes the core data foundation with SQL views, materialized views, and Python database utilities used by all subsequent modules.

| Component | Count | Description |
|-----------|-------|-------------|
| Core Views | 8 | Patient enrichment, transaction flat, RFM, LTV, ML features |
| Materialized Views | 7 | Daily refresh at 1:00 AM via pgAgent |
| Python Modules | 2 | DatabaseManager, setup utilities |
| Unit Tests | 40+ | Mocked database + integration tests |

**Key Views**:
- `vw_patient_enriched` — Patient data with calculated fields (age, status, recency)
- `vw_patient_rfm` — RFM segmentation with 11 customer segments
- `vw_patient_lifetime_value` — Patient LTV predictions and health scores
- `vw_ml_patient_features` — Feature engineering for ML models

**RFM Segments**: Champions, Loyal Customers, Potential Loyalists, New Customers, Promising, Need Attention, About to Sleep, At Risk, Cannot Lose Them, Hibernating, Lost

---

### ST-02: Sales & Revenue Analytics

**Purpose**: Comprehensive sales analytics with Prophet-based forecasting, festival impact analysis, and promotion effectiveness tracking.

| Component | Count | Description |
|-----------|-------|-------------|
| Sales Views | 4 | Daily summary, branch performance, product performance |
| Calendar Views | 4 | Festival analysis, promotion impact, DOW heatmap |
| Materialized Views | 7 | Daily refresh at 2:00 AM |
| Tables | 2 | malaysian_holidays, sales_forecast |
| Python Modules | 2 | sales_forecast.py (Prophet), sales_analytics.py |

**Key Features**:
- **90-day Prophet forecasting** with Malaysian holiday integration
- **Festival impact analysis** (pre/during/post period classification)
- **Branch performance ranking** with tier classification (Top/High/Medium/Low)
- **Promotion effectiveness** with discount tier analysis

**Festivals Configured**: Chinese New Year, Hari Raya, Deepavali, Christmas, Merdeka

---

### ST-03: Patient Intelligence

**Purpose**: Patient-focused analytics for D+3 follow-up, risk classification, RFM segmentation, cohort retention, and CLTV predictions.

| Component | Count | Description |
|-----------|-------|-------------|
| Patient Views | 7 | Follow-up tracker, risk classification, RFM, cohort, visit frequency |
| Materialized Views | 7 | Daily refresh at 2:00 AM |
| Tables | 2 | patient_ltv_predictions, ltv_model_runs |
| Python Modules | 2 | patient_analytics.py, cltv_model.py (BG/NBD + Gamma-Gamma) |

**Risk Classification**:
| Status | Days Since Visit | Description |
|--------|------------------|-------------|
| ACTIVE | 0-21 days | Currently engaged patients |
| AT RISK | 22-45 days | Showing signs of disengagement |
| HIGH RISK | 46-90 days | At risk of being lost |
| LOST | >90 days | No recent activity |

**CLTV Model Results** (2,689 patients):
- Average 12m CLV: ₱166.96
- Average 24m CLV: ₱333.73
- Average probability alive: 82.9%
- Top tier patients: 5 PREMIUM, 27 HIGH, 587 MEDIUM, 2,070 LOW

---

### ST-04: Product & Package Performance

**Purpose**: Product category views, package analytics, payment behavior analysis, and affordability stress metrics.

| Component | Count | Description |
|-----------|-------|-------------|
| Product Views | 5 | Skincare, supplements, medications, services, category mix |
| Package Views | 4 | Composition, redemption, addon, conversion demographics |
| Payment Views | 4 | Payment mode, affordability stress, preference, stressed buyers |
| Materialized Views | 7 | Daily refresh at 2:00 AM |
| Python Modules | 1 | product_analytics.py (17 methods) |

**Product Categories**: Consultations, Services, Medications, Supplements (RM5), Skincare, Other

**Payment Modes**: PACKAGE_REDEMPTION, LOYALTY_DEPOSIT, ON_BEHALF, OPEN_DEPOSIT, DIRECT_PAYMENT

**Affordability Stress Levels**:
| Level | Stress Ratio | Description |
|-------|--------------|-------------|
| CRITICAL | ≥ 3.0 | Outstanding ≥ 3x monthly spend |
| HIGH | ≥ 2.0 | Outstanding ≥ 2x monthly spend |
| MEDIUM | ≥ 1.0 | Outstanding ≥ monthly spend |
| LOW | < 1.0 | Outstanding < monthly spend |

---

### ST-05: AI/ML Predictive Engine

**Purpose**: Four XGBoost models scoring every patient daily for churn risk, package upsell, next best treatment, and promo elasticity.

| Component | Count | Description |
|-----------|-------|-------------|
| Feature Views | 2 | ML features (30+ engineered features), patient labels |
| Pricing Views | 2 | Dynamic pricing, A/B assignment |
| Tables | 4 | ml_predictions, model_metadata, dynamic_pricing_offers, ab_results |
| Materialized Views | 3 | Cached features, predictions, pricing |
| Python Modules | 2 | ml_pipeline.py, dynamic_pricing.py |

**ML Model Performance** (Verified 2026-04-02):
| Model | AUC-ROC | Purpose |
|-------|---------|---------|
| Churn Risk | 0.8663 | Predict patients likely to churn (>180 days inactive) |
| Package Upsell | 0.9041 | Predict patients likely to upgrade to packages |
| Promo Elasticity | 0.9852 | Predict price sensitivity |

**Output**: 3,558 patients scored daily with personalized offers

**Dynamic Pricing Offer Types**: discount, bundle, retention, vip_perk, win_back, welcome, standard

---

### ST-06: Geospatial Analytics

**Purpose**: Convert patient addresses into geographic intelligence for catchment analysis, cannibalization detection, and expansion planning.

| Component | Count | Description |
|-----------|-------|-------------|
| Core Tables | 7 | branch_master, patient_geocode, patient_branch_distance, clusters |
| Analytical Views | 7 | Patient geo, branch summary, catchment, cannibalization, whitespace |
| Materialized Views | 6 | Daily refresh at 3:30 AM |
| Python Modules | 4 | geocoding_pipeline, geo_analysis, branch_geocoding, load_postcode |
| Interactive Maps | 7 | Folium HTML maps in ST-06/maps/ |
| pgAgent Jobs | 3 | Daily geocoding, analysis, weekly full refresh |

**Geocoding Strategy**: Azure Maps API (primary) → Nominatim (fallback) with four-level fallback:
1. Full address (street + city + state + zip)
2. Street + City only
3. City + State only
4. ZIP code only

**Interactive Maps**:
| Map | File | Purpose |
|-----|------|---------|
| Patient Origin | map_01_patient_origin.html | Patient dots by distance band |
| Branch Catchments | map_02_branch_catchments.html | Branch circles with radius |
| Patient Clusters | map_03_patient_clusters.html | DBSCAN cluster visualization |
| Cannibalization Network | map_04_cannibalization_network.html | Branch overlap network |
| Whitespace Expansion | map_05_whitespace_opportunity.html | Expansion bubble chart |
| Revenue Heatmap | map_06_revenue_heatmap.html | Revenue intensity map |
| Patient Acquisition | map_07_new_patient_flow.html | New patient flow over time |

---

### ST-07: Automation & Campaigns

**Purpose**: WhatsApp-based patient communication with PDPA-compliant consent management and automated campaign orchestration.

| Component | Count | Description |
|-----------|-------|-------------|
| Tables | 5 | whatsapp_templates, campaign_queue, delivery_log, patient_consent, campaign_stats |
| Views | 3 | Pending queue, campaign performance, communication status |
| Python Modules | 4 | whatsapp_client, campaign_sender, campaign_manager, webhook_handler |
| Campaign Types | 7 | Appointment reminder, no-show follow-up, churn prevention, upsell, dynamic pricing, reactivation, marketing |
| pgAgent Jobs | 8 | Queue processing, campaign triggers, stats refresh |

**Campaign Types**:
| Type | Trigger | Template | Priority |
|------|---------|----------|----------|
| appointment_reminder | Daily batch (D-1) | appointment_reminder | 2 (high) |
| no_show_followup | Daily batch or event | no_show_followup | 1 (critical) |
| churn_prevention | Weekly batch | churn_prevention | 2 (high) |
| upsell_recommendation | Weekly batch | upsell_recommendation | 3 (normal) |
| dynamic_pricing_offer | Weekly batch | dynamic_pricing_offer | 3 (normal) |
| reactivation | Monthly batch | reactivation | 4 (low) |
| marketing_broadcast | Manual | marketing_broadcast | 3 (normal) |

**Architecture**: Hybrid — pgAgent batch scheduling + FastAPI event-driven webhooks

**Compliance**: PDPA 2010 (Malaysia) — explicit opt-in, opt-out via "STOP", no PHI in messages

---

## Data Assets Summary

### Total Database Objects

| Category | Count | Description |
|----------|-------|-------------|
| **Tables** | 31 | Source + output tables across all modules |
| **Views** | 38 | Analytical views for reporting |
| **Materialized Views** | 37 | Cached data for Power BI |
| **Functions** | 15+ | Helper functions for refresh, scheduling |
| **pgAgent Jobs** | 22 | Automated scheduling |

### Module-by-Module Breakdown

| Module | Tables | Views | MVWs | Python Modules |
|--------|--------|-------|------|----------------|
| ST-01 | 0 | 8 | 7 | 2 |
| ST-02 | 2 | 8 | 7 | 2 |
| ST-03 | 2 | 7 | 7 | 2 |
| ST-04 | 0 | 13 | 7 | 1 |
| ST-05 | 4 | 4 | 3 | 2 |
| ST-06 | 7 | 7 | 6 | 4 |
| ST-07 | 5 | 3 | 0 | 4 |
| **Total** | **20** | **38** | **30** | **15** |

---

## Business Use Cases

### 1. Patient Retention & Churn Prevention
- **ST-03** identifies at-risk patients (22-45 days inactive)
- **ST-05** predicts churn probability with ML models
- **ST-07** triggers WhatsApp retention campaigns automatically
- **Impact**: Reduce patient churn by proactive engagement

### 2. Revenue Optimization
- **ST-02** forecasts 90-day revenue with Prophet
- **ST-05** identifies upsell opportunities with package probability
- **ST-05** generates personalized discount offers via dynamic pricing
- **Impact**: Increase average revenue per patient through targeted offers

### 3. Branch Performance & Expansion
- **ST-02** ranks branches by performance tiers
- **ST-06** identifies cannibalization between branches
- **ST-06** scores whitespace opportunities for expansion
- **Impact**: Data-driven branch network optimization

### 4. Patient Engagement Automation
- **ST-07** automates D-1 appointment reminders
- **ST-07** triggers no-show follow-up within hours
- **ST-07** sends personalized upsell recommendations weekly
- **Impact**: Reduce no-show rates, increase repeat visits

### 5. Product Mix Optimization
- **ST-04** analyzes category revenue share per branch
- **ST-04** tracks package vs standalone preference
- **ST-04** monitors affordability stress for pricing decisions
- **Impact**: Optimize product mix and package composition

---

## ROI Potential

| Use Case | Potential ROI | Timeline |
|----------|---------------|----------|
| Churn Prevention | 15-25% reduction in lost patients | 3-6 months |
| Revenue Forecasting | 10-15% improvement in budget accuracy | 1-3 months |
| Upsell Targeting | 20-30% increase in package conversions | 6-12 months |
| Branch Optimization | 5-10% reduction in cannibalization | 6-12 months |
| Campaign Automation | 40-50% reduction in manual outreach effort | 1-3 months |

---

## Technical Specifications

### Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| PostgreSQL | 12+ | Primary database with materialized view support |
| PostGIS | 3.6+ | Geospatial analytics (ST-06) |
| pgAgent | Latest | Job scheduling (Windows) |
| Python | 3.10+ | Analytics pipelines |
| Power BI Desktop | Latest | Visualization dashboards |
| Npgsql | 4.0.10 | Power BI PostgreSQL driver |

### Python Dependencies

```
# Core
pandas>=1.5.0
numpy>=1.20.0
sqlalchemy>=1.4.0
psycopg2-binary>=2.9.0
python-dotenv>=1.0.0

# Analytics
prophet>=1.1.0
lifetimes>=0.11.0
scikit-learn>=1.2.0

# ML
xgboost>=1.7.0
shap>=0.44.0

# Geospatial
folium>=0.14.0
requests>=2.28.0

# Automation
fastapi>=0.104.0
uvicorn>=0.24.0

# Testing
pytest>=7.0.0
```

### Environment Variables

```bash
# Database Connection
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password
DB_SCHEMA=dk

# Azure Maps API (ST-06)
AZURE_MAPS_CLIENT_ID=your_client_id
AZURE_MAPS_PRIMARY_KEY=your_primary_key

# WhatsApp Cloud API (ST-07)
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_VERIFY_TOKEN=your_verify_token
```

---

## Quick Start Guide

### Phase 1: Environment Setup (30 minutes)

```bash
# 1. Clone/Create project directory
cd D:\dev\healthcare_poc_bi

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your database credentials
```

### Phase 2: Database Setup (45 minutes)

```bash
# Execute SQL scripts in order (Windows)
psql -U postgres -d postgres -f ST-01/sql/01_core_views.sql
psql -U postgres -d postgres -f ST-01/sql/02_materialized_views.sql
psql -U postgres -d postgres -f ST-01/sql/03_scheduling_views.sql

psql -U postgres -d postgres -f ST-02/sql/01_sales_views.sql
psql -U postgres -d postgres -f ST-02/sql/02_calendar_effects_views.sql
psql -U postgres -d postgres -f ST-02/sql/03_materialized_views.sql

psql -U postgres -d postgres -f ST-03/sql/01_patient_intelligence_views.sql
psql -U postgres -d postgres -f ST-03/sql/02_materialized_views.sql

psql -U postgres -d postgres -f ST-04/sql/01_product_performance_views.sql
psql -U postgres -d postgres -f ST-04/sql/03_payment_behavior_views.sql
psql -U postgres -d postgres -f ST-04/sql/02_package_analytics_views.sql
psql -U postgres -d postgres -f ST-04/sql/04_materialized_views.sql

psql -U postgres -d postgres -f ST-05/sql/01_ml_features_views.sql
psql -U postgres -d postgres -f ST-05/sql/02_dynamic_pricing_views.sql
psql -U postgres -d postgres -f ST-05/sql/03_materialized_views.sql

psql -U postgres -d postgres -f ST-06/sql/01_postgis_setup.sql
psql -U postgres -d postgres -f ST-06/sql/02_branch_geocoding_tables.sql
psql -U postgres -d postgres -f ST-06/sql/03_analytical_views.sql
psql -U postgres -d postgres -f ST-06/sql/04_materialized_views.sql

psql -U postgres -d postgres -f ST-07/sql/01_campaign_tables.sql
psql -U postgres -d postgres -f ST-07/sql/02_campaign_views.sql
psql -U postgres -d postgres -f ST-07/sql/04_seed_templates.sql
```

### Phase 3: Initial Data Processing (15 minutes)

```bash
# Refresh all materialized views
python -c "from ST_01.python.database import get_db_manager; db = get_db_manager(); db.execute_query('SELECT dk.refresh_all_mvws()')"

# Run ML pipeline
python ST-05/python/ml_pipeline.py --mode=retrain

# Generate dynamic pricing offers
python ST-05/python/dynamic_pricing.py --mode=generate --save

# Run geospatial analysis
python ST-06/python/geocoding_pipeline.py
python ST-06/python/geo_analysis.py
```

### Phase 4: Power BI Connection (10 minutes)

1. Install Npgsql v4.0.10 with GAC installation
2. Open Power BI Desktop → Get Data → PostgreSQL
3. Server: `localhost`, Database: `postgres`
4. Select materialized views: `dk.mvw_*`
5. Build dashboards from cached data

### Phase 5: pgAgent Scheduling (15 minutes)

1. Install pgAgent from pgAdmin.org
2. Open Services (`services.msc`) → Start pgAgent
3. Execute scheduling SQL files:
   ```bash
   psql -U postgres -d postgres -f ST-05/sql/04_scheduling.sql
   psql -U postgres -d postgres -f ST-06/sql/05_scheduling.sql
   psql -U postgres -d postgres -f ST-07/sql/03_scheduling.sql
   ```

---

## Implementation Roadmap

### Phase Dependencies

```
ST-01 (Foundation)
  │
  ├──→ ST-02 (Sales Analytics) [depends on ST-01/python/database]
  │
  ├──→ ST-03 (Patient Intelligence) [depends on ST-01]
  │
  ├──→ ST-04 (Product Performance) [depends on ST-01]
  │
  ├──→ ST-05 (ML Predictive Engine) [depends on ST-01, ST-02, ST-03]
  │      │
  │      └──→ ST-07 (Campaigns) [uses ML predictions for targeting]
  │
  └──→ ST-06 (Geospatial Analytics) [depends on ST-01, PostGIS]
```

### Execution Sequence

| Phase | Modules | Duration | Dependencies |
|-------|---------|----------|--------------|
| 1 | ST-01 | Day 1 | None |
| 2 | ST-02, ST-03, ST-04 | Day 2-3 | ST-01 |
| 3 | ST-05 | Day 4-5 | ST-01, ST-02, ST-03 |
| 4 | ST-06 | Day 6-7 | ST-01, PostGIS |
| 5 | ST-07 | Day 8 | ST-05, WhatsApp setup |

---

## Scheduled Jobs Summary

### Daily Jobs (22 total)

| Module | Jobs | Schedule | Purpose |
|--------|------|----------|---------|
| ST-01 | 1 | 1:00 AM | Refresh core materialized views |
| ST-02 | 1 | 2:00 AM | Refresh sales materialized views |
| ST-03 | 1 | 2:00 AM | Refresh patient intelligence MVWs |
| ST-04 | 1 | 2:00 AM | Refresh product MVWs |
| ST-05 | 1 | 3:00 AM | Daily incremental ML scoring |
| ST-06 | 2 | 00:00, 3:30 AM | Geocoding + geo analysis |
| ST-07 | 5 | Various | Queue processing + campaign triggers |

### Weekly Jobs

| Module | Job | Schedule | Purpose |
|--------|-----|----------|---------|
| ST-05 | Full Retrain | Sunday 2:00 AM | Retrain all ML models |
| ST-06 | Full Refresh | Sunday 3:00 AM | Full geo MVW refresh |

---

## Project Structure

```
healthcare_poc_bi/
├── ST-01/                          # Data Foundation
│   ├── sql/
│   │   ├── 01_core_views.sql
│   │   ├── 02_materialized_views.sql
│   │   └── 03_scheduling_views.sql
│   └── python/
│       ├── database.py
│       ├── setup.py
│       └── test_database.py
│
├── ST-02/                          # Sales Analytics
│   ├── sql/
│   │   ├── 01_sales_views.sql
│   │   ├── 02_calendar_effects_views.sql
│   │   └── 03_materialized_views.sql
│   └── python/
│       ├── sales_forecast.py
│       ├── sales_analytics.py
│       └── test_sales_analytics.py
│
├── ST-03/                          # Patient Intelligence
│   ├── sql/
│   │   ├── 01_patient_intelligence_views.sql
│   │   └── 02_materialized_views.sql
│   └── python/
│       ├── patient_analytics.py
│       ├── cltv_model.py
│       ├── test_patient_analytics.py
│       └── test_cltv_model.py
│
├── ST-04/                          # Product Performance
│   ├── sql/
│   │   ├── 01_product_performance_views.sql
│   │   ├── 02_package_analytics_views.sql
│   │   ├── 03_payment_behavior_views.sql
│   │   └── 04_materialized_views.sql
│   └── python/
│       ├── product_analytics.py
│       └── test_product_analytics.py
│
├── ST-05/                          # ML Predictive Engine
│   ├── sql/
│   │   ├── 01_ml_features_views.sql
│   │   ├── 02_dynamic_pricing_views.sql
│   │   ├── 03_materialized_views.sql
│   │   └── 04_scheduling.sql
│   └── python/
│       ├── ml_pipeline.py
│       ├── dynamic_pricing.py
│       ├── test_ml_pipeline.py
│       ├── test_dynamic_pricing.py
│       └── test_ab_testing.py
│
├── ST-06/                          # Geospatial Analytics
│   ├── sql/
│   │   ├── 01_postgis_setup.sql
│   │   ├── 02_branch_geocoding_tables.sql
│   │   ├── 03_analytical_views.sql
│   │   ├── 04_materialized_views.sql
│   │   └── 05_scheduling.sql
│   ├── python/
│   │   ├── geocoding_pipeline.py
│   │   ├── geo_analysis.py
│   │   ├── branch_geocoding.py
│   │   ├── load_postcode_data.py
│   │   ├── test_geocoding.py
│   │   └── test_geo_analysis.py
│   └── maps/
│       ├── map_01_patient_origin.html
│       ├── map_02_branch_catchments.html
│       ├── map_03_patient_clusters.html
│       ├── map_04_cannibalization_network.html
│       ├── map_05_whitespace_opportunity.html
│       ├── map_06_revenue_heatmap.html
│       └── map_07_new_patient_flow.html
│
├── ST-07/                          # Automation & Campaigns
│   ├── sql/
│   │   ├── 01_campaign_tables.sql
│   │   ├── 02_campaign_views.sql
│   │   ├── 03_scheduling.sql
│   │   └── 04_seed_templates.sql
│   └── python/
│       ├── whatsapp_client.py
│       ├── campaign_sender.py
│       ├── campaign_manager.py
│       ├── webhook_handler.py
│       └── test_campaigns.py
│
├── docs/                           # Documentation
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment template
├── .env                            # Environment (configured)
└── README.md                       # This file
```

---

## Implementation Status

| Module | Status | Completion Date |
|--------|--------|-----------------|
| **ST-01** | ✅ Complete | 2026-03-22 |
| **ST-02** | ✅ Complete | 2026-03-30 |
| **ST-03** | ✅ Complete | 2026-03-31 |
| **ST-04** | ✅ Complete | 2026-04-01 |
| **ST-05** | ✅ Complete | 2026-04-02 |
| **ST-06** | ✅ Complete | 2026-04-04 |
| **ST-07** | ✅ Complete | 2026-04-04 |

---

## Key Design Decisions

### Architecture Choices

| Decision | Rationale |
|----------|-----------|
| PostgreSQL + PostGIS | Single database for all analytics, avoiding data silos |
| Materialized Views | Cached data for Power BI, reducing query latency |
| pgAgent over pg_cron | Windows compatibility (pg_cron Linux-only) |
| Direct WhatsApp Cloud API | No BSP dependency, lowest cost, full control |
| Prophet for forecasting | Handles Malaysian holidays, festival seasonality |
| XGBoost + SHAP | Interpretable ML with feature importance |
| Azure Maps + Nominatim | Enterprise geocoding with free fallback |

### Data Model Constraints

| Constraint | Reason |
|------------|--------|
| Schema: `dk` | All objects in single schema for consistency |
| Patient PK: `location` | MRN has duplicates, location is unique |
| Collection PK: `row_number` | Auto-increment, not `id` |
| Date field: `date` | Not `transaction_date` (source schema) |
| Amount field: `amount_collected` | Not `net_amount` |

---

## Troubleshooting Guide

### Common Issues

| Issue | Solution |
|-------|----------|
| Views return empty | Check source tables: `SELECT COUNT(*) FROM dk.collection` |
| MVW refresh fails | Manual refresh: `SELECT dk.refresh_all_mvws()` |
| Prophet fails to train | Minimum 30 days of historical data required |
| Power BI connection fails | Install Npgsql with GAC, restart computer |
| pgAgent jobs not running | Check service in `services.msc`, verify environment variables |
| Azure Maps 401 error | Key sent as query param, check `AZURE_MAPS_PRIMARY_KEY` |
| WhatsApp templates rejected | Utility templates approved faster than marketing |

---

## Support & Maintenance

### Daily Monitoring

- Check pgAgent job execution: `SELECT * FROM cron.job_run_details ORDER BY start_time DESC`
- Verify MVW freshness: `SELECT * FROM dk.vw_ml_job_latest_status`
- Monitor ML predictions: `SELECT COUNT(*) FROM dk.ml_predictions WHERE prediction_date = CURRENT_DATE`

### Weekly Maintenance

- Review model performance: `SELECT * FROM dk.model_metadata ORDER BY train_date DESC`
- Analyze campaign effectiveness: `SELECT * FROM dk.vw_campaign_performance`
- Check geocode quality: `SELECT geocode_quality, COUNT(*) FROM dk.patient_geocode GROUP BY geocode_quality`

### Quarterly Review

- Retrain ML models if AUC drops below 0.65
- Review cannibalization trends
- Update Malaysian holidays table for new festivals
- Analyze cohort retention trends

---

## Contact & Contribution

This Healthcare Analytics Business Intelligence Platform was developed as a proof-of-concept to demonstrate enterprise-grade healthcare analytics capabilities.

**Project Repository**: `D:\dev\healthcare_poc_bi`

**For detailed module documentation**, see individual README files:
- `ST-01/README.md` — Data Foundation
- `ST-02/README.md` — Sales Analytics
- `ST-03/README.md` — Patient Intelligence
- `ST-04/README.md` — Product Performance
- `ST-05/README.md` — ML Predictive Engine
- `ST-06/README.md` — Geospatial Analytics
- `ST-07/README.md` — Automation & Campaigns

---

## License

This project is developed for demonstration purposes. All patient data used is synthetic/sample data for proof-of-concept validation.

---

*Last Updated: April 2026*