# ST-08: ECharts Healthcare Analytics Dashboard

6-page interactive dashboard using Apache ECharts with FastAPI backend.

## Quick Start

```bash
# 1. Start the API server
cd ST-08/python
python -m uvicorn api:app --reload --port 8000

# 2. Open dashboard
# Navigate to http://localhost:8000
```

## Architecture

- **Backend**: FastAPI serving JSON from PostgreSQL MVWs (dk schema)
- **Frontend**: Single HTML file with ECharts 5.x via CDN
- **Database**: Reuses ST-01 DatabaseManager for PostgreSQL connections

## Features

The dashboard provides 6 integrated pages for comprehensive healthcare analytics:

1. **Executive Overview**: Key revenue, patient, and branch KPIs
2. **Patient Intelligence**: Demographics, growth trends, risk segments
3. **Product & Package Analytics**: Category mix, positioning analysis
4. **AI Predictive Engine**: ML-powered churn, upsell, pricing insights
5. **Geospatial Analytics**: Patient origins, branch catchments, whitespace opportunities
6. **Payment Behavior**: Payment method trends and affordability analysis

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/` | Dashboard frontend |
| `/favicon.ico` | Prevents 404 browser errors |
| `/api/health` | Health check |
| `/api/kpis` | Executive Overview KPI cards |
| `/api/revenue/trends` | 12-month revenue trend |
| `/api/revenue/forecast` | Actuals + forecast with confidence bands |
| `/api/patients/demographics` | Patient demographics by age/gender/race |
| `/api/patients/growth` | New vs returning patient trends |
| `/api/products/mix` | Product category mix analysis |
| `/api/products/category-revenue` | Revenue by product category and branch |
| `/api/packages/composition` | Service/meds/skincare package composition |
| `/api/payments/mode` | Payment mode distribution |
| `/api/payments/trends` | Payment trend analysis |
| `/api/ml/predictions` | ML predictions for churn/upsell |
| `/api/geo/patients` | Patient geospatial data with distance bands |
| `/api/geo/branches` | Branch location and performance data |
| `/api/geo/catchment` | Branch catchment penetration metrics |
| `/api/geo/whitespace` | Expansion opportunity analysis |
| `/api/geo/whitespace/patients/{cluster_label}` | Patients in whitespace opportunity areas for outreach |

## Configuration

Set these in `.env` (project root):
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password
DB_SCHEMA=dk
```

## Outreach Capabilities

### Whitespace Opportunity Campaigns

For targeting patients in identified whitespace opportunities:

1. **Get whitespace clusters**: `/api/geo/whitespace` (returns labels like "Area_6.0_116.1")
2. **Get cluster patients**: `/api/geo/whitespace/patients/Area_6.0_116.1`
3. **Use ST-07 system**: Integrate patient MRNs with WhatsApp campaigns using `CampaignManager.queue_campaign_message()`

Example for targeted outreach:
```python
import requests

# Get patients in specific whitespace area (e.g., Area_6.0_116.1)
cluster_label = 'Area_6.0_116.1'
response = requests.get(f'/api/geo/whitespace/patients/{cluster_label}')
patients = response.json()['data']

# Extract MRNs for campaign targeting
patient_mrns = [patient['mrn'] for patient in patients]

# Integrate with ST-07 for WhatsApp campaign
from campaign_manager import CampaignManager

def launch_whitespace_outreach(patient_mrns):
    mgr = CampaignManager()
    for mrn in patient_mrns:
        mgr.queue_campaign_message(
            # Queue targeted message promoting nearby branch expansion
        )
```

## Data Flow Architecture

1. **Data Sources**: PostgreSQL (dk schema) with materialized views cached from ST-01 through ST-07
2. **API Layer**: FastAPI endpoints execute SQL against materialized views
3. **Frontend**: Pure JavaScript transforms JSON to ECharts visualizations
4. **Interactions**: Real-time charts update based on date ranges

## Troubleshooting

- If dashboard doesn't load: verify API endpoints return JSON data
- If charts show blanks: ensure required data exists in PostgreSQL for date range
- For performance: refresh materialized views (executed via ST-06 `db.refresh_geo_mvws()`)

## Performance Optimizations

- **Caching**: All endpoints query materialized views instead of base tables
- **Indexing**: GEOGRAPHY indexes for geospatial queries, composite indexes for date filters
- **Paging**: Limited result sets with LIMIT clauses where appropriate
- **Date Filtering**: Applied at database level to reduce data transfer

## Security Notes

- **No PII in queries**: Patient names/addresses excluded (only MRNs and aggregated data)
- **Input Validation**: All URL parameters validated with FastAPI Query validators
- **Connection Security**: Production deployment requires secure DB connection settings
- **CORS**: Configured to restrict access in production (currently wide open for development)

## Lessons Learned

### Geospatial Analysis Complexity
- **Distance Band Issues**: Initial "Distance Band Distribution" visual showed 100% undefined due to missing distance band data in patient records
  - **Issue**: `vw_patient_geo_enriched` data didn't include distance bands for visualization
  - **Solution**: Enhanced `/api/geo/patients` endpoint to include `nearest_branch_dist_band` and ensure data consistency  
  - **Key Takeaway**: Ensure all required fields from geospatial views are available in API output, not just primary geocoordinates

- **Whitespace Opportunity Integration**: Needed special API integration for connecting geographic opportunities to patient outreach
  - **Challenge**: Converting area identifiers like "Area_6.0_116.1" back to specific patients
  - **Learning**: Created `/api/geo/whitespace/patients/{cluster_label}` endpoint to bridge gap between abstract opportunities and actual patients
  - **Insight**: Whitespace visualizations are strategic but operational outreach needs individual patient data

### API Data Consistency
- **Column Availability Problems**: Difficulty accessing correct column names across different views (patient names, contact numbers)
  - **Lesson**: Always verify column schema at runtime or use reliable fallbacks with COALESCE
  - **Best Practice**: Use `vw_patient_geo_enriched` for geospatial patient data, `collection_report` for contact info
  - **Key Learning**: Don't assume schema stability - use flexible SQL approach

- **Date Range Application**: Critical to apply date filtering consistently across all related endpoints
  - **Implementation**: All endpoints now validate dates with `start_date/end_date` via FastAPI Query parameters
  - **Pattern**: Join with transactional dates (collection, collection_report) to filter by date range
  - **Benefit**: Eliminates temporal anomalies between dashboard pages

### Dashboard Development Challenges
- **Empty Chart Handling**: Many charts showing as empty due to date range mismatches between view availability and required data
  - **Discovery**: Views created but dependencies (collections, transactions) not populated in required date range
  - **Solution**: Validate data existence before chart rendering with fallback displays
  - **Insight**: Data availability ≠ data readiness - ensure data pipeline completes before dashboard usage

- **Frontend Error Suppression**: Visual indicators for "No Data Available" needed instead of blank screens
  - **Learning**: Clear error messaging improves user experience significantly
  - **Implementation**: Enhanced JavaScript to detect null/undefined values and show meaningful "No Data Available" messages

### Data Integration Across Systems
- **ST-07 Campaign Connectivity**: Connected whitespace opportunities to WhatsApp outreach system needed
  - **Insight**: Strategic visuals (whitespace) must connect to operational systems (ST-07 campaigns)
  - **Feature Added**: New API endpoint allows retrieving actual patient MRNs from whitespace clusters for targeted outreach
  - **Lesson**: Dashboards often need operational follow-through capabilities

- **Cross-Module Dependencies**: Understanding relationships between ST-01 through ST-07 data layers
  - **Key Relationship**: `patient_geocode` (geospatial) connects to `patient` (demographics) and `collection_report` (contacts)
  - **Dependency Chain**: ST-06 clustering feeds ST-08 whitespace; ST-05 ML feeds ST-08 predictions
  - **Best Practice**: Document all inter-module dependencies for maintainability

### Testing and Validation
- **Database Schema Validation**: Assumptions about field names often incorrect in actual database
  - **Issue**: Column names like `name`, `total_visits`, `phone_primary` didn't exist in actual tables
  - **Validation Process**: Always use `execute_query()` results to verify available columns before relying on them
  - **Defensive Programming**: Use conditional logic when joining related tables with varying schemas

- **User Workflow Integration**: Understanding how analytics feed into business processes
  - **Example**: Whitespace data leads to patient outreach campaigns via ST-07
  - **Design Insight**: Dashboards should facilitate workflows, not just show data
  - **Implementation**: Added patient MRN retrieval capabilities in whitespace analysis

### System Reliability
- **Fallback Systems**: Implement robust error handling for missing data scenarios
  - **Pattern**: Standardized `safe_query()` function returns structured error responses
  - **Benefit**: Dashboard gracefully handles temporary data unavailability without crashing
  - **Lesson**: Resilient design essential for production analytics systems

- **Dashboard Responsiveness**: Ensuring data loads timely across all visualization pages  
  - **Optimization**: Reduced result set sizes with LIMIT clauses for faster chart rendering
  - **Performance**: Caching strategy using materialized views significantly impacts responsiveness
  - **Monitoring**: Track API response times to identify database performance bottlenecks

## Development Best Practices Documented

1. **Query Design**:
   - Always apply date filters at database level vs. in-memory filtering
   - Use `COALESCE(column, default)` for nullable columns to prevent NULL-related JS errors
   - Leverage PostGIS functions for geospatial calculations at database layer

2. **API Interface Patterns**:
   - Parameter validation via FastAPI `Query()` with default values  
   - Consistent response structures with `data`, `columns`, `source`, `count`, `error` fields
   - Error boundaries to prevent cascading failures between dashboard sections

3. **Frontend Design Principles**:
   - Defensive JavaScript coding to handle missing/null data gracefully
   - Consistent visualization themes with error/empty states
   - Responsive date filter coordination across all dashboard pages

## Running Tests

```bash
cd ST-08/python
python -m pytest test_api.py -v
```

## Future Enhancements

1. **Operational Integration**: Direct campaign creation from whitespace opportunities
2. **Advanced Analytics**: Seasonal-adjusted predictions and trend analysis
3. **Real-time Monitoring**: Live KPI updates with WebSocket connections
4. **Mobile Optimization**: Responsive design for executive review on mobile devices