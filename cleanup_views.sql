-- =============================================================================
-- cleanup_views.sql
-- Remove all views and materialized views from dk schema
-- =============================================================================
-- Usage: psql -h localhost -p 5432 -U postgres -d postgres -f cleanup_views.sql
-- =============================================================================

BEGIN;

-- Set schema
SET search_path TO dk;

-- =============================================================================
-- Drop all materialized views in dk schema (with CASCADE)
-- EXCLUDE materialized views owned by extensions
-- =============================================================================
DO $$
DECLARE
    mv_record RECORD;
BEGIN
    FOR mv_record IN 
        SELECT schemaname, matviewname 
        FROM pg_matviews mv
        WHERE schemaname = 'dk'
        AND NOT EXISTS (
            SELECT 1 
            FROM pg_depend d
            JOIN pg_extension e ON d.refobjid = e.oid
            JOIN pg_class c ON d.objid = c.oid
            WHERE d.deptype = 'e'
            AND c.relname = mv.matviewname
            AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'dk')
        )
        ORDER BY matviewname
    LOOP
        EXECUTE format('DROP MATERIALIZED VIEW IF EXISTS %I.%I CASCADE', 
                       mv_record.schemaname, mv_record.matviewname);
        RAISE NOTICE 'Dropped materialized view: %', mv_record.matviewname;
    END LOOP;
END $$;

-- =============================================================================
-- Drop all views in dk schema (with CASCADE)
-- EXCLUDE views owned by extensions (e.g., PostGIS geography_columns)
-- =============================================================================
DO $$
DECLARE
    view_record RECORD;
BEGIN
    FOR view_record IN 
        SELECT schemaname, viewname 
        FROM pg_views v
        WHERE schemaname = 'dk'
        AND NOT EXISTS (
            -- Exclude views that are owned by an extension
            SELECT 1 
            FROM pg_depend d
            JOIN pg_extension e ON d.refobjid = e.oid
            JOIN pg_class c ON d.objid = c.oid
            WHERE d.deptype = 'e'  -- extension dependency
            AND c.relname = v.viewname
            AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'dk')
        )
        ORDER BY viewname
    LOOP
        EXECUTE format('DROP VIEW IF EXISTS %I.%I CASCADE', 
                       view_record.schemaname, view_record.viewname);
        RAISE NOTICE 'Dropped view: %', view_record.viewname;
    END LOOP;
    
    -- List extension-owned views that were skipped
    FOR view_record IN 
        SELECT schemaname, viewname 
        FROM pg_views v
        WHERE schemaname = 'dk'
        AND EXISTS (
            SELECT 1 
            FROM pg_depend d
            JOIN pg_extension e ON d.refobjid = e.oid
            JOIN pg_class c ON d.objid = c.oid
            WHERE d.deptype = 'e'
            AND c.relname = v.viewname
            AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'dk')
        )
        ORDER BY viewname
    LOOP
        RAISE NOTICE 'Skipped extension-owned view: %', view_record.viewname;
    END LOOP;
END $$;

-- =============================================================================
-- Verification - Show remaining objects in dk schema
-- =============================================================================
SELECT 'Materialized Views remaining:' as category, count(*) as count
FROM pg_matviews WHERE schemaname = 'dk'
UNION ALL
SELECT 'Views remaining:' as category, count(*) as count
FROM pg_views WHERE schemaname = 'dk';

-- Show tables remaining (should not be affected)
SELECT 'Tables in dk schema:' as category, count(*) as count
FROM pg_tables WHERE schemaname = 'dk';

COMMIT;

-- =============================================================================
-- Summary message
-- =============================================================================
\echo 'Cleanup complete. All views and materialized views in dk schema have been removed.'