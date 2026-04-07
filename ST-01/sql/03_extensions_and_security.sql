-- ============================================================
-- ST-01: Data Foundation & Infrastructure
-- 03_extensions_and_security.sql
-- Extensions, Roles, and Security Setup
-- ============================================================

-- ============================================================
-- ENABLE EXTENSIONS
-- ============================================================

-- PostGIS for geospatial analytics (ST-06)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- pg_stat_statements for query performance monitoring
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- NOTE: pg_cron is not available on Windows.
-- For scheduling on Windows, use pgAgent or Windows Task Scheduler.
-- Example: psql -U postgres -d postgres -c "SELECT dk.refresh_all_mvws();"

-- ============================================================
-- CREATE ROLES
-- ============================================================

-- Read-only role for Power BI users
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'healthcare_bi_reader') THEN
        CREATE ROLE healthcare_bi_reader NOLOGIN;
    END IF;
END
$$;

-- Read-write role for application
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'healthcare_bi_app') THEN
        CREATE ROLE healthcare_bi_app NOLOGIN;
    END IF;
END
$$;

-- Admin role for data engineers
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'healthcare_bi_admin') THEN
        CREATE ROLE healthcare_bi_admin NOLOGIN;
    END IF;
END
$$;

-- ============================================================
-- GRANT PERMISSIONS
-- ============================================================

-- Grant schema usage
GRANT USAGE ON SCHEMA dk TO healthcare_bi_reader;
GRANT USAGE ON SCHEMA dk TO healthcare_bi_app;
GRANT USAGE ON SCHEMA dk TO healthcare_bi_admin;

-- Grant read-only permissions on views
GRANT SELECT ON dk.vw_patient_enriched TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_transaction_flat TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_transactions TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_rfm TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_patient_lifetime_value TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_ml_patient_features TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_calendar_effects TO healthcare_bi_reader;
GRANT SELECT ON dk.vw_d3_followup_tracker TO healthcare_bi_reader;

-- Grant read-only permissions on materialized views
GRANT SELECT ON dk.mvw_patient_enriched TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_transaction_flat TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_patient_transactions TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_patient_rfm TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_patient_ltv TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_calendar_effects TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_branch_performance TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_product_performance TO healthcare_bi_reader;
GRANT SELECT ON dk.mvw_d3_followup_list TO healthcare_bi_reader;

-- Grant app role permissions (read base tables, write to staging tables)
GRANT SELECT ON dk.patient TO healthcare_bi_app;
GRANT SELECT ON dk.collection TO healthcare_bi_app;
GRANT SELECT ON dk.collection_report TO healthcare_bi_app;

-- Grant admin permissions
GRANT ALL ON SCHEMA dk TO healthcare_bi_admin;
GRANT ALL ON ALL TABLES IN SCHEMA dk TO healthcare_bi_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA dk TO healthcare_bi_admin;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA dk TO healthcare_bi_admin;

-- ============================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================

-- Enable RLS on patient table for sensitive data
ALTER TABLE dk.patient ENABLE ROW LEVEL SECURITY;

-- Create policy: users can only see patients from branches they have access to
-- This requires a branch_access table or user metadata
-- For now, create a placeholder policy that allows all (to be customized)
CREATE POLICY patient_access_policy ON dk.patient
    FOR SELECT
    TO healthcare_bi_reader, healthcare_bi_app
    USING (true);

-- ============================================================
-- AUDIT LOGGING SETUP
-- ============================================================

-- Create audit log table
CREATE TABLE IF NOT EXISTS dk.audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100),
    action VARCHAR(50),
    old_data JSONB,
    new_data JSONB,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Function to log changes
CREATE OR REPLACE FUNCTION dk.log_audit()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO dk.audit_log (table_name, action, new_data, changed_by)
        VALUES (TG_TABLE_NAME, 'INSERT', to_jsonb(NEW), current_user);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO dk.audit_log (table_name, action, old_data, new_data, changed_by)
        VALUES (TG_TABLE_NAME, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW), current_user);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO dk.audit_log (table_name, action, old_data, changed_by)
        VALUES (TG_TABLE_NAME, 'DELETE', to_jsonb(OLD), current_user);
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- DATA QUALITY CHECK FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION dk.check_data_quality()
RETURNS TABLE (
    check_name VARCHAR(200),
    check_status VARCHAR(50),
    issue_count INTEGER,
    details TEXT
) AS $$
BEGIN
    -- Check 1: NULL MRNs
    RETURN QUERY
    SELECT 
        'NULL MRN Check'::VARCHAR(200),
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::VARCHAR(50),
        COUNT(*)::INTEGER,
        'Records with NULL MRN in patient table'::TEXT
    FROM dk.patient
    WHERE mrn IS NULL;
    
    -- Check 2: Duplicate MRNs
    RETURN QUERY
    SELECT 
        'Duplicate MRN Check'::VARCHAR(200),
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::VARCHAR(50),
        COUNT(*)::INTEGER,
        'Duplicate MRN count'::TEXT
    FROM (
        SELECT mrn, COUNT(*) 
        FROM dk.patient 
        GROUP BY mrn 
        HAVING COUNT(*) > 1
    ) dupes;
    
    -- Check 3: Future dates
    RETURN QUERY
    SELECT 
        'Future Transaction Date Check'::VARCHAR(200),
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::VARCHAR(50),
        COUNT(*)::INTEGER,
        'Transactions with future dates'::TEXT
    FROM dk.collection
    WHERE date > CURRENT_DATE;
    
    -- Check 4: Negative amounts
    RETURN QUERY
    SELECT 
        'Negative Amount Check'::VARCHAR(200),
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::VARCHAR(50),
        COUNT(*)::INTEGER,
        'Transactions with negative amount_collected'::TEXT
    FROM dk.collection
    WHERE amount_collected < 0;
    
    -- Check 5: Materialized view freshness
    RETURN QUERY
    SELECT 
        'MVW Freshness Check'::VARCHAR(200),
        'INFO'::VARCHAR(50),
        0::INTEGER,
        'Last refresh: ' || COALESCE(
            (SELECT max(last_refresh) FROM pg_stat_user_tables WHERE relname LIKE 'mvw_%'),
            'Never'
        )::TEXT;
END;
$$ LANGUAGE plpgsql;

-- Grant execute on data quality function
GRANT EXECUTE ON FUNCTION dk.check_data_quality() TO healthcare_bi_reader;
GRANT EXECUTE ON FUNCTION dk.check_data_quality() TO healthcare_bi_app;
GRANT EXECUTE ON FUNCTION dk.check_data_quality() TO healthcare_bi_admin;
