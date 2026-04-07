-- ============================================================================
-- ST-01: Data Foundation & Infrastructure
-- File: 03_scheduling_views.sql
-- Description: Cross-platform scheduling for materialized view refreshes
--              Auto-detects OS and configures pg_cron (Linux/macOS) or pgAgent (Windows)
-- Schema: dk
-- ============================================================================

-- ============================================================================
-- SECTION 1: Create OS Detection Function
-- ============================================================================

CREATE OR REPLACE FUNCTION dk.detect_os()
RETURNS TEXT AS $$
DECLARE
    v_os TEXT;
    v_version TEXT;
BEGIN
    -- Method 1: Use dynamic_shared_memory_type (most reliable)
    SELECT setting INTO v_os
    FROM pg_settings
    WHERE name = 'dynamic_shared_memory_type';

    -- Method 2: Fallback to parsing version() string
    IF v_os IS NULL OR v_os = '' THEN
        v_version := version();
        IF v_version ILIKE '%windows%' OR v_version ILIKE '%mingw%' OR v_version ILIKE '%visual%' THEN
            v_os := 'windows';
        ELSE
            v_os := 'unix';
        END IF;
    END IF;

    -- Normalize output
    RETURN CASE 
        WHEN v_os = 'windows' THEN 'windows'
        ELSE 'unix'
    END;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.detect_os() IS 'Detects the host operating system (windows or unix)';

-- ============================================================================
-- SECTION 2: Configure pg_cron (Linux/macOS)
-- ============================================================================

DO $$
DECLARE
    v_os TEXT;
    v_job_exists BOOLEAN;
BEGIN
    -- Detect OS
    v_os := dk.detect_os();

    RAISE NOTICE 'Detected OS platform: %', v_os;

    -- Skip if Windows (pg_cron not supported on Windows)
    IF v_os = 'windows' THEN
        RAISE NOTICE 'Skipping pg_cron setup (Windows detected). Use pgAgent instead.';
        RETURN;
    END IF;

    -- Check if pg_cron is installed
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN

        -- Check if job already exists to avoid duplicates
        SELECT EXISTS(
            SELECT 1 FROM cron.job WHERE jobname = 'daily-mvw-refresh'
        ) INTO v_job_exists;

        IF NOT v_job_exists THEN
            PERFORM cron.schedule(
                'daily-mvw-refresh',
                '0 1 * * *',
                'SELECT dk.refresh_all_mvws()'
            );
            RAISE NOTICE 'pg_cron job scheduled: daily-mvw-refresh (Daily at 1:00 AM)';
        ELSE
            RAISE NOTICE 'pg_cron job already exists: daily-mvw-refresh';
        END IF;

    ELSE
        RAISE NOTICE 'pg_cron extension not installed. Skipping pg_cron setup.';
        RAISE NOTICE 'To enable automatic refresh on Linux/macOS:';
        RAISE NOTICE '  1. Install pg_cron: https://github.com/citusdata/pg_cron';
        RAISE NOTICE '  2. Add to postgresql.conf: shared_preload_libraries = ''pg_cron''';
        RAISE NOTICE '  3. Restart PostgreSQL';
        RAISE NOTICE '  4. Run: CREATE EXTENSION pg_cron;';
    END IF;
END
$$;

-- ============================================================================
-- SECTION 3: Configure pgAgent (Windows)
-- ============================================================================

DO $$
DECLARE
    v_os TEXT;
    v_job_id INTEGER;
    v_step_id INTEGER;
    v_schedule_id INTEGER;
    v_job_exists BOOLEAN;
BEGIN
    -- Detect OS
    v_os := dk.detect_os();

    -- Skip if not Windows
    IF v_os != 'windows' THEN
        RAISE NOTICE 'Skipping pgAgent setup (Linux/Unix detected). Use pg_cron instead.';
        RETURN;
    END IF;

    -- Check if pgAgent is installed
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgagent') THEN

        -- Check if job already exists
        SELECT EXISTS(
            SELECT 1 FROM pgagent.pga_job WHERE jobname = 'daily-mvw-refresh'
        ) INTO v_job_exists;

        IF v_job_exists THEN
            RAISE NOTICE 'pgAgent job already exists: daily-mvw-refresh';
            RETURN;
        END IF;

        -- Create the job
        INSERT INTO pgagent.pga_job (
            jobjclid,
            jobname,
            jobenabled,
            jobhostagent,
            jobcreated,
            jobchanged,
            jobagentid,
            jobnextrun,
            joblastrun,
            jobdesc
        ) VALUES (
            1,
            'daily-mvw-refresh',
            true,
            '',
            current_timestamp,
            current_timestamp,
            NULL,
            NULL,
            NULL,
            'Daily refresh of all materialized views at 1:00 AM'
        )
        RETURNING jobid INTO v_job_id;

        -- Add the job step (SQL command)
        INSERT INTO pgagent.pga_jobstep (
            jstjobid,
            jstname,
            jstenabled,
            jstkind,
            jstonerror,
            jstcode,
            jstdbname,
            jstconnstr,
            jstdesc
        ) VALUES (
            v_job_id,
            'refresh_materialized_views',
            true,
            's',
            'f',
            'SELECT dk.refresh_all_mvws();',
            current_database(),
            '',
            'Execute refresh_all_mvws() to update all materialized views'
        )
        RETURNING jstid INTO v_step_id;

        -- Add daily schedule at 1:00 AM
        INSERT INTO pgagent.pga_schedule (
            jscjobid,
            jscname,
            jscdesc,
            jscenabled,
            jscstart,
            jscend,
            jscminutes,
            jschours,
            jscweekdays,
            jscmonthdays,
            jscmonths
        ) VALUES (
            v_job_id,
            'daily_at_1am',
            'Run daily at 1:00 AM',
            true,
            current_timestamp,
            NULL,
            -- Minute 0 (Exactly 60 boolean values)
            '{t,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f}',
            -- Hour 1 (24 boolean values, 't' at position 1)
            '{f,t,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f,f}',
            -- All weekdays (7 boolean values, all 't')
            '{t,t,t,t,t,t,t}',
            -- All month days (32 boolean values, all 't')
            '{t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t,t}',
            -- All months (12 boolean values, all 't')
            '{t,t,t,t,t,t,t,t,t,t,t,t}'
        )
        RETURNING jscid INTO v_schedule_id;

        RAISE NOTICE 'pgAgent job created: daily-mvw-refresh (ID: %)', v_job_id;
        RAISE NOTICE '  Step ID: %, Schedule ID: %', v_step_id, v_schedule_id;
        RAISE NOTICE '  Schedule: Daily at 1:00 AM';

    ELSE
        RAISE NOTICE 'pgAgent extension not installed. Skipping pgAgent setup.';
        RAISE NOTICE 'To enable automatic refresh on Windows:';
        RAISE NOTICE '  1. Install pgAgent: https://www.pgadmin.org/docs/pgadmin4/latest/pgagent.html';
        RAISE NOTICE '  2. Run: CREATE EXTENSION pgagent;';
        RAISE NOTICE '  3. Start pgAgent service (pgagent.exe)';
        RAISE NOTICE '';
        RAISE NOTICE 'Alternative: Use Windows Task Scheduler:';
        RAISE NOTICE '  schtasks /create /tn "Refresh Materialized Views" /tr "psql -U user -d db -c SELECT dk.refresh_all_mvws();" /sc daily /st 01:00';
    END IF;
END
$$;

-- ============================================================================
-- SECTION 4: Summary & Verification
-- ============================================================================

DO $$
DECLARE
    v_os TEXT;
    v_pg_cron_installed BOOLEAN;
    v_pgagent_installed BOOLEAN;
BEGIN
    -- Detect OS
    v_os := dk.detect_os();

    -- Check installed extensions
    v_pg_cron_installed := EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron');
    v_pgagent_installed := EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgagent');

    RAISE NOTICE '';
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Scheduling Setup Summary';
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Detected OS: %', CASE WHEN v_os = 'windows' THEN 'Windows' ELSE 'Linux/Unix/macOS' END;
    RAISE NOTICE 'pg_cron installed: %', v_pg_cron_installed;
    RAISE NOTICE 'pgAgent installed: %', v_pgagent_installed;
    RAISE NOTICE '';

    IF v_pg_cron_installed THEN
        RAISE NOTICE 'View pg_cron jobs: SELECT * FROM cron.job;';
        RAISE NOTICE 'View run history: SELECT * FROM cron.job_run_details ORDER BY start_time DESC;';
    END IF;

    IF v_pgagent_installed THEN
        RAISE NOTICE 'View pgAgent jobs: SELECT * FROM pgagent.pga_job;';
        RAISE NOTICE 'View schedules: SELECT * FROM pgagent.pga_schedule;';
    END IF;

    IF NOT v_pg_cron_installed AND NOT v_pgagent_installed THEN
        RAISE NOTICE 'WARNING: No scheduling extension detected!';
        RAISE NOTICE 'Materialized views will NOT refresh automatically.';
        RAISE NOTICE 'Install pg_cron (Linux/macOS) or pgAgent (Windows) for automatic refresh.';
        RAISE NOTICE '';
        RAISE NOTICE 'Manual refresh command: SELECT dk.refresh_all_mvws();';
    END IF;

    RAISE NOTICE '============================================================';
END
$$;

-- ============================================================================
-- END OF FILE
-- ============================================================================
