-- ============================================================
-- ST-06: Geospatial Analytics
-- 05_scheduling.sql
-- pgAgent Job Definitions for Windows
-- ============================================================
-- 
-- This file creates pgAgent jobs for:
-- 1. Daily geocoding at 00:00 AM (incremental)
-- 2. Daily geo analysis at 03:30 AM (after ML pipeline)
-- 3. Weekly full refresh on Sunday at 03:00 AM
--
-- Prerequisites:
-- - pgAgent installed and running on Windows
-- - Python scripts accessible from PostgreSQL server
-- - Database user has permissions to create pgAgent jobs
-- - Required environment variables or PostgreSQL settings configured (see below)
--
-- IMPORTANT: Required Configuration
-- Run these commands BEFORE executing this script to set up configuration:
--
--   -- Set Python executable path (use your Python installation path)
--   SELECT set_config('geo.python_path', 'C:\Python310\python.exe', false);
--   -- Or for Unix-style path: SELECT set_config('geo.python_path', '/usr/bin/python3', false);
--
--   -- Set project root directory
--   SELECT set_config('geo.project_root', 'D:\dev\healthcare_poc_bi', false);
--
--   -- Set Python script paths (relative to project_root)
--   SELECT set_config('geo.pipeline_path', 'ST-06/python/geocoding_pipeline.py', false);
--   SELECT set_config('geo.analysis_path', 'ST-06/python/geo_analysis.py', false);
--
--   -- Set log directory (relative to project_root)
--   SELECT set_config('geo.log_dir', 'ST-06/logs', false);
--
--   -- Set script directory for batch files (relative to project_root)
--   SELECT set_config('geo.scripts_dir', 'ST-06/scripts', false);
--
-- For persistent configuration, add these to postgresql.conf:
--   geo.python_path = 'C:\Python310\python.exe'
--   geo.project_root = 'D:\dev\healthcare_poc_bi'
--   geo.pipeline_path = 'ST-06/python/geocoding_pipeline.py'
--   geo.analysis_path = 'ST-06/python/geo_analysis.py'
--   geo.log_dir = 'ST-06/logs'
--   geo.scripts_dir = 'ST-06/scripts'
--
-- Or set as environment variables (for pgAgent service):
--   GEO_PYTHON_PATH=C:\Python310\python.exe
--   GEO_PROJECT_ROOT=D:\dev\healthcare_poc_bi
-- ============================================================

-- ============================================================
-- Step 1: Verify pgAgent extension is installed
-- ============================================================

-- Create extension if not exists (requires superuser)
CREATE EXTENSION IF NOT EXISTS pgagent;

-- Verify pgAgent jobs table exists
SELECT tablename 
FROM pg_tables 
WHERE schemaname = 'pgagent' 
  AND tablename IN ('pga_job', 'pga_step', 'pga_schedule', 'pga_joblog', 'pga_steplog');

-- ============================================================
-- Step 2: Create log table and helper function
-- ============================================================

-- Create log table for geo jobs
CREATE TABLE IF NOT EXISTS dk.geo_job_execution_log (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    message TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_seconds INTEGER
);

CREATE OR REPLACE FUNCTION dk.log_geo_job_execution(
    p_job_name VARCHAR(100),
    p_status VARCHAR(20),
    p_message TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO dk.geo_job_execution_log (job_name, status, message)
    VALUES (p_job_name, p_status, p_message);

    RAISE NOTICE 'GEO Job [%]: % - %', p_job_name, p_status, COALESCE(p_message, '');
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.log_geo_job_execution IS 'Logs geo pipeline job execution status for monitoring and debugging';

-- ============================================================
-- Step 3: Create wrapper functions for Geo pipeline modes
-- ============================================================

-- Wrapper for incremental geocoding mode
CREATE OR REPLACE FUNCTION dk.run_geo_incremental_geocoding()
RETURNS INTEGER AS $$
DECLARE
    v_result INTEGER;
    v_start_time TIMESTAMP;
    v_end_time TIMESTAMP;
    v_duration INTEGER;
BEGIN
    v_start_time := clock_timestamp();
    
    -- Log job start
    CALL dk.log_geo_job_execution('daily_geocoding', 'STARTED');
    
    BEGIN
        -- Execute geocoding pipeline in incremental mode
        -- Paths are constructed from settings: project_root + relative_path
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s "%s%s%s" --incremental --log-file="%s%sgeocoding_%%s.log"' $copy$,
            COALESCE(current_setting('geo.python_path', TRUE), 'python'),
            COALESCE(current_setting('geo.project_root', TRUE), ''),
            CASE WHEN current_setting('geo.project_root', TRUE) != '' THEN '\' ELSE '' END,
            COALESCE(current_setting('geo.pipeline_path', TRUE), 'ST-06/python/geocoding_pipeline.py'),
            COALESCE(current_setting('geo.project_root', TRUE), ''),
            CASE WHEN current_setting('geo.project_root', TRUE) != '' THEN '\' ELSE '' END,
            COALESCE(current_setting('geo.log_dir', TRUE), 'ST-06/logs'),
            CASE WHEN current_setting('geo.project_root', TRUE) != '' THEN '\' ELSE '' END,
            to_char(CURRENT_DATE, 'YYYYMMDD')
        );
        
        v_result := 1;
    EXCEPTION WHEN OTHERS THEN
        v_result := 0;
        
        -- Log error details
        CALL dk.log_geo_job_execution('daily_geocoding', 'FAILED', SQLERRM);
        
        -- Re-raise to mark job as failed in pgAgent
        RAISE EXCEPTION 'Incremental geocoding failed: %', SQLERRM;
    END;
    
    v_end_time := clock_timestamp();
    v_duration := EXTRACT(EPOCH FROM (v_end_time - v_start_time))::INTEGER;
    
    -- Log success
    CALL dk.log_geo_job_execution('daily_geocoding', 'SUCCESS', 
        format('Completed in %s seconds', v_duration));
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.run_geo_incremental_geocoding IS 'Wrapper for daily incremental geocoding at 00:00 AM';

-- Wrapper for full geo analysis mode
CREATE OR REPLACE FUNCTION dk.run_geo_full_analysis()
RETURNS INTEGER AS $$
DECLARE
    v_result INTEGER;
    v_start_time TIMESTAMP;
    v_end_time TIMESTAMP;
    v_duration INTEGER;
BEGIN
    v_start_time := clock_timestamp();
    
    -- Log job start
    CALL dk.log_geo_job_execution('daily_geo_analysis', 'STARTED');
    
    BEGIN
        -- Execute geo analysis pipeline in full mode
        -- Paths are constructed from settings: project_root + relative_path
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s "%s%s%s" --full --log-file="%s%sgeo_analysis_%%s.log"' $copy$,
            COALESCE(current_setting('geo.python_path', TRUE), 'python'),
            COALESCE(current_setting('geo.project_root', TRUE), ''),
            CASE WHEN current_setting('geo.project_root', TRUE) != '' THEN '\' ELSE '' END,
            COALESCE(current_setting('geo.analysis_path', TRUE), 'ST-06/python/geo_analysis.py'),
            COALESCE(current_setting('geo.project_root', TRUE), ''),
            CASE WHEN current_setting('geo.project_root', TRUE) != '' THEN '\' ELSE '' END,
            COALESCE(current_setting('geo.log_dir', TRUE), 'ST-06/logs'),
            CASE WHEN current_setting('geo.project_root', TRUE) != '' THEN '\' ELSE '' END,
            to_char(CURRENT_DATE, 'YYYYMMDD')
        );
        
        v_result := 1;
    EXCEPTION WHEN OTHERS THEN
        v_result := 0;
        
        -- Log error details
        CALL dk.log_geo_job_execution('daily_geo_analysis', 'FAILED', SQLERRM);
        
        -- Re-raise to mark job as failed in pgAgent
        RAISE EXCEPTION 'Full geo analysis failed: %', SQLERRM;
    END;
    
    v_end_time := clock_timestamp();
    v_duration := EXTRACT(EPOCH FROM (v_end_time - v_start_time))::INTEGER;
    
    -- Log success
    CALL dk.log_geo_job_execution('daily_geo_analysis', 'SUCCESS', 
        format('Completed in %s seconds', v_duration));
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.run_geo_full_analysis IS 'Wrapper for daily full geo analysis at 03:30 AM';

-- ============================================================
-- Step 4: Create batch file generator functions
-- ============================================================

-- Function to generate batch file for geocoding
-- Uses environment variables for all paths - no hardcoded values
CREATE OR REPLACE FUNCTION dk.create_geocoding_batch_file()
RETURNS TEXT AS $$
DECLARE
    v_project_root TEXT := COALESCE(current_setting('geo.project_root', TRUE), 'D:\dev\healthcare_poc_bi');
    v_python_path TEXT := COALESCE(current_setting('geo.python_path', TRUE), 'C:\Python310\python.exe');
    v_pipeline_path TEXT := COALESCE(current_setting('geo.pipeline_path', TRUE), 'ST-06\python\geocoding_pipeline.py');
    v_log_dir TEXT := COALESCE(current_setting('geo.log_dir', TRUE), 'ST-06\logs');
    v_scripts_dir TEXT := COALESCE(current_setting('geo.scripts_dir', TRUE), 'ST-06\scripts');
    v_batch_path TEXT;
    v_batch_content TEXT;
BEGIN
    -- Construct full paths
    v_batch_path := v_project_root || '\' || v_scripts_dir || '\run_geocoding.bat';
    
    v_batch_content := format(
        $batch$
@echo off
REM ST-06 Geospatial Pipeline - Daily Incremental Geocoding
REM Scheduled: Daily at 00:00 AM via pgAgent
REM Auto-generated from database configuration - DO NOT EDIT MANUALLY

REM Use environment variables or database settings for paths
SET PYTHON_PATH=%GEO_PYTHON_PATH%
SET PROJECT_ROOT=%GEO_PROJECT_ROOT%
SET GEOCODING_PATH=%PROJECT_ROOT%\%GEO_PIPELINE_PATH%
SET LOG_DIR=%PROJECT_ROOT%\%GEO_LOG_DIR%
SET LOG_FILE=%LOG_DIR%\geocoding_%%DATE:~-4,4%%%%DATE:~-7,2%%%%DATE:~-10,2%%.log

REM Ensure log directory exists
IF NOT EXIST "%LOG_DIR%" MKDIR "%LOG_DIR%"

REM Run incremental geocoding
ECHO [%%DATE%% %%TIME%%] Starting geocoding... >> %%LOG_FILE%%
"%%PYTHON_PATH%%" "%%GEOCODING_PATH%%" --incremental --log-file="%%LOG_FILE%%" 2>&1

IF %%ERRORLEVEL%% EQU 0 (
    ECHO [%%DATE%% %%TIME%%] Geocoding completed successfully >> %%LOG_FILE%%
    EXIT /B 0
) ELSE (
    ECHO [%%DATE%% %%TIME%%] ERROR: Geocoding failed with code %%ERRORLEVEL%% >> %%LOG_FILE%%
    EXIT /B 1
)
$batch$
    );
    
    BEGIN
        EXECUTE format(
            $copy$ COPY (SELECT %L) TO %L $copy$,
            v_batch_content,
            v_batch_path
        );
        RETURN format('Batch file created: %s', v_batch_path);
    EXCEPTION WHEN OTHERS THEN
        RETURN format('Failed to create batch file: %s. Manual creation required.', SQLERRM);
    END;
END;
$$ LANGUAGE plpgsql;

-- Function to generate batch file for geo analysis
-- Uses environment variables for all paths - no hardcoded values
CREATE OR REPLACE FUNCTION dk.create_geo_analysis_batch_file()
RETURNS TEXT AS $$
DECLARE
    v_project_root TEXT := COALESCE(current_setting('geo.project_root', TRUE), 'D:\dev\healthcare_poc_bi');
    v_python_path TEXT := COALESCE(current_setting('geo.python_path', TRUE), 'C:\Python310\python.exe');
    v_analysis_path TEXT := COALESCE(current_setting('geo.analysis_path', TRUE), 'ST-06\python\geo_analysis.py');
    v_log_dir TEXT := COALESCE(current_setting('geo.log_dir', TRUE), 'ST-06\logs');
    v_scripts_dir TEXT := COALESCE(current_setting('geo.scripts_dir', TRUE), 'ST-06\scripts');
    v_batch_path TEXT;
    v_batch_content TEXT;
BEGIN
    -- Construct full paths
    v_batch_path := v_project_root || '\' || v_scripts_dir || '\run_geo_analysis.bat';
    
    v_batch_content := format(
        $batch$
@echo off
REM ST-06 Geospatial Pipeline - Daily Full Geo Analysis
REM Scheduled: Daily at 03:30 AM via pgAgent
REM Auto-generated from database configuration - DO NOT EDIT MANUALLY

REM Use environment variables or database settings for paths
SET PYTHON_PATH=%GEO_PYTHON_PATH%
SET PROJECT_ROOT=%GEO_PROJECT_ROOT%
SET GEO_ANALYSIS_PATH=%PROJECT_ROOT%\%GEO_ANALYSIS_PATH%
SET LOG_DIR=%PROJECT_ROOT%\%GEO_LOG_DIR%
SET LOG_FILE=%LOG_DIR%\geo_analysis_%%DATE:~-4,4%%%%DATE:~-7,2%%%%DATE:~-10,2%%.log

REM Ensure log directory exists
IF NOT EXIST "%LOG_DIR%" MKDIR "%LOG_DIR%"

REM Run full geo analysis
ECHO [%%DATE%% %%TIME%%] Starting geo analysis... >> %%LOG_FILE%%
"%%PYTHON_PATH%%" "%%GEO_ANALYSIS_PATH%%" --full --log-file="%%LOG_FILE%%" 2>&1

IF %%ERRORLEVEL%% EQU 0 (
    ECHO [%%DATE%% %%TIME%%] Geo analysis completed successfully >> %%LOG_FILE%%
    EXIT /B 0
) ELSE (
    ECHO [%%DATE%% %%TIME%%] ERROR: Geo analysis failed with code %%ERRORLEVEL%% >> %%LOG_FILE%%
    EXIT /B 1
)
$batch$
    );
    
    BEGIN
        EXECUTE format(
            $copy$ COPY (SELECT %L) TO %L $copy$,
            v_batch_content,
            v_batch_path
        );
        RETURN format('Batch file created: %s', v_batch_path);
    EXCEPTION WHEN OTHERS THEN
        RETURN format('Failed to create batch file: %s. Manual creation required.', SQLERRM);
    END;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Step 5: Create pgAgent Jobs
-- ============================================================

-- Job 1: Daily Geocoding at 00:00 AM

DO $$
DECLARE
    v_jobid INTEGER;
    v_schid INTEGER;
    v_jclid INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM pgagent.pga_job WHERE jobname = 'ST-06 Daily Geocoding') THEN
        RAISE NOTICE 'Job already exists, skipping creation';
        RETURN;
    END IF;

    SELECT jclid INTO v_jclid FROM pgagent.pga_jobclass LIMIT 1;
    IF v_jclid IS NULL THEN
        RAISE EXCEPTION 'No pgAgent job class found. Ensure pgAgent is properly configured.';
    END IF;

    INSERT INTO pgagent.pga_job (
        jobname,
        jobdesc,
        jobjclid,
        jobenabled,
        jobcreated
    ) VALUES (
        'ST-06 Daily Geocoding',
        'Daily incremental geocoding of patient addresses at 00:00 AM',
        v_jclid,
        TRUE,
        CURRENT_TIMESTAMP
    ) RETURNING jobid INTO v_jobid;

    INSERT INTO pgagent.pga_schedule (
        jscjobid,
        jscname,
        jscdesc,
        jscenabled,
        jscstart,
        jscminutes,
        jschours
    ) VALUES (
        v_jobid,
        'Daily 00:00',
        'Every day at 00:00 AM (midnight)',
        TRUE,
        CURRENT_DATE + INTERVAL '1 day',
        ARRAY[TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE],
        ARRAY[TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE]
    ) RETURNING jscid INTO v_schid;

    RAISE NOTICE 'Created job: ST-06 Daily Geocoding (ID: %)', v_jobid;
END $$;

-- Job 2: Daily Geo Analysis at 03:30 AM

DO $$
DECLARE
    v_jobid INTEGER;
    v_schid INTEGER;
    v_jclid INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM pgagent.pga_job WHERE jobname = 'ST-06 Daily Geo Analysis') THEN
        RAISE NOTICE 'Job already exists, skipping creation';
        RETURN;
    END IF;

    SELECT jclid INTO v_jclid FROM pgagent.pga_jobclass LIMIT 1;
    IF v_jclid IS NULL THEN
        RAISE EXCEPTION 'No pgAgent job class found. Ensure pgAgent is properly configured.';
    END IF;

    INSERT INTO pgagent.pga_job (
        jobname,
        jobdesc,
        jobjclid,
        jobenabled,
        jobcreated
    ) VALUES (
        'ST-06 Daily Geo Analysis',
        'Daily full geo analysis (distance, clusters, cannibalization) at 03:30 AM',
        v_jclid,
        TRUE,
        CURRENT_TIMESTAMP
    ) RETURNING jobid INTO v_jobid;

    INSERT INTO pgagent.pga_schedule (
        jscjobid,
        jscname,
        jscdesc,
        jscenabled,
        jscstart,
        jscminutes,
        jschours
    ) VALUES (
        v_jobid,
        'Daily 03:30',
        'Every day at 03:30 AM (after ML pipeline)',
        TRUE,
        CURRENT_DATE + INTERVAL '1 day' + INTERVAL '3 hours 30 minutes',
        ARRAY[FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE],
        ARRAY[FALSE,FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE]
    ) RETURNING jscid INTO v_schid;

    RAISE NOTICE 'Created job: ST-06 Daily Geo Analysis (ID: %)', v_jobid;
END $$;

-- Job 3: Weekly Full Refresh on Sunday at 03:00 AM

DO $$
DECLARE
    v_jobid INTEGER;
    v_schid INTEGER;
    v_jclid INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM pgagent.pga_job WHERE jobname = 'ST-06 Weekly Full Refresh') THEN
        RAISE NOTICE 'Job already exists, skipping creation';
        RETURN;
    END IF;

    SELECT jclid INTO v_jclid FROM pgagent.pga_jobclass LIMIT 1;
    IF v_jclid IS NULL THEN
        RAISE EXCEPTION 'No pgAgent job class found. Ensure pgAgent is properly configured.';
    END IF;

    INSERT INTO pgagent.pga_job (
        jobname,
        jobdesc,
        jobjclid,
        jobenabled,
        jobcreated
    ) VALUES (
        'ST-06 Weekly Full Refresh',
        'Weekly full refresh of all geospatial materialized views on Sunday at 03:00 AM',
        v_jclid,
        TRUE,
        CURRENT_TIMESTAMP
    ) RETURNING jobid INTO v_jobid;

    INSERT INTO pgagent.pga_schedule (
        jscjobid,
        jscname,
        jscdesc,
        jscenabled,
        jscstart,
        jscminutes,
        jschours,
        jscweekdays
    ) VALUES (
        v_jobid,
        'Sunday 03:00',
        'Every Sunday at 03:00 AM',
        TRUE,
        CURRENT_DATE +
            CASE
                WHEN EXTRACT(DOW FROM CURRENT_DATE) = 0 THEN 7
                ELSE 7 - EXTRACT(DOW FROM CURRENT_DATE)::INTEGER
            END * INTERVAL '1 day' +
            INTERVAL '3 hours',
        ARRAY[TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE],
        ARRAY[FALSE,FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE],
        '{t,f,f,f,f,f,f}'
    ) RETURNING jscid INTO v_schid;

    RAISE NOTICE 'Created job: ST-06 Weekly Full Refresh (ID: %)', v_jobid;
END $$;

-- ============================================================
-- Step 6: Verify job creation
-- ============================================================

-- List all ST-06 pgAgent jobs
SELECT 
    j.jobid,
    j.jobname,
    j.jobdesc,
    j.jobenabled,
    s.jscname AS schedule_name,
    s.jscstart AS next_run,
    s.jscminutes,
    s.jschours,
    s.jscweekdays
FROM pgagent.pga_job j
LEFT JOIN pgagent.pga_schedule s ON j.jobid = s.jscjobid
WHERE j.jobname LIKE 'ST-06%'
ORDER BY j.jobname;

-- Simple job list
SELECT 
    j.jobid,
    j.jobname,
    j.jobdesc,
    j.jobenabled,
    j.jobcreated
FROM pgagent.pga_job j
WHERE j.jobname LIKE 'ST-06%'
ORDER BY j.jobname;

-- ============================================================
-- Step 7: Monitoring Views
-- ============================================================

-- View: Job Status - Current status of all ST-06 jobs
CREATE OR REPLACE VIEW dk.vw_geo_job_status AS
SELECT DISTINCT ON (job_name)
    job_name,
    status,
    message,
    executed_at,
    duration_seconds
FROM dk.geo_job_execution_log
ORDER BY job_name, executed_at DESC;

COMMENT ON VIEW dk.vw_geo_job_status IS 'Current execution status for each ST-06 geo job';

-- View: Job History - Recent execution history
CREATE OR REPLACE VIEW dk.vw_geo_job_history AS
SELECT 
    job_name,
    status,
    message,
    executed_at,
    duration_seconds,
    CASE 
        WHEN executed_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 'Last Hour'
        WHEN executed_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN 'Last 24 Hours'
        WHEN executed_at >= CURRENT_TIMESTAMP - INTERVAL '7 days' THEN 'Last 7 Days'
        ELSE 'Older'
    END AS time_bucket
FROM dk.geo_job_execution_log
ORDER BY executed_at DESC
LIMIT 100;

COMMENT ON VIEW dk.vw_geo_job_history IS 'Recent execution history for ST-06 geo jobs';

-- Check monitoring views
SELECT * FROM dk.vw_geo_job_status;
SELECT * FROM dk.vw_geo_job_history;

-- ============================================================
-- Step 8: Error handling functions
-- ============================================================

-- Function to check for failed geo jobs in last 24 hours
CREATE OR REPLACE FUNCTION dk.check_geo_job_failures()
RETURNS TABLE (
    job_name VARCHAR(100),
    failed_at TIMESTAMP,
    error_message TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        l.job_name,
        l.executed_at,
        l.message
    FROM dk.geo_job_execution_log l
    WHERE l.status = 'FAILED'
      AND l.executed_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
    ORDER BY l.executed_at DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.check_geo_job_failures IS 'Returns geo jobs that failed in the last 24 hours for alerting';

-- Check for failures
SELECT * FROM dk.check_geo_job_failures();

-- ============================================================
-- Step 9: Manual execution functions (for testing)
-- ============================================================

-- Function to manually trigger geocoding
CREATE OR REPLACE FUNCTION dk.trigger_geocoding()
RETURNS TEXT AS $$
DECLARE
    v_result TEXT;
BEGIN
    CALL dk.log_geo_job_execution('manual_geocoding', 'STARTED');
    
    BEGIN
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s "%s%s%s" --incremental' $copy$,
            COALESCE(current_setting('geo.python_path', TRUE), 'python'),
            COALESCE(current_setting('geo.project_root', TRUE), ''),
            CASE WHEN current_setting('geo.project_root', TRUE) != '' THEN '\' ELSE '' END,
            COALESCE(current_setting('geo.pipeline_path', TRUE), 'ST-06/python/geocoding_pipeline.py')
        );
        
        CALL dk.log_geo_job_execution('manual_geocoding', 'SUCCESS');
        v_result := 'Geocoding triggered successfully';
    EXCEPTION WHEN OTHERS THEN
        CALL dk.log_geo_job_execution('manual_geocoding', 'FAILED', SQLERRM);
        v_result := format('Failed: %s', SQLERRM);
    END;
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Function to manually trigger geo analysis
CREATE OR REPLACE FUNCTION dk.trigger_geo_analysis()
RETURNS TEXT AS $$
DECLARE
    v_result TEXT;
BEGIN
    CALL dk.log_geo_job_execution('manual_geo_analysis', 'STARTED');
    
    BEGIN
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s "%s%s%s" --full' $copy$,
            COALESCE(current_setting('geo.python_path', TRUE), 'python'),
            COALESCE(current_setting('geo.project_root', TRUE), ''),
            CASE WHEN current_setting('geo.project_root', TRUE) != '' THEN '\' ELSE '' END,
            COALESCE(current_setting('geo.analysis_path', TRUE), 'ST-06/python/geo_analysis.py')
        );
        
        CALL dk.log_geo_job_execution('manual_geo_analysis', 'SUCCESS');
        v_result := 'Geo analysis triggered successfully';
    EXCEPTION WHEN OTHERS THEN
        CALL dk.log_geo_job_execution('manual_geo_analysis', 'FAILED', SQLERRM);
        v_result := format('Failed: %s', SQLERRM);
    END;
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Function to manually trigger MVW refresh (weekly)
CREATE OR REPLACE FUNCTION dk.trigger_geo_mvw_refresh()
RETURNS TABLE (mvw_name VARCHAR(100), status VARCHAR(50), duration_ms FLOAT) AS $$
BEGIN
    CALL dk.log_geo_job_execution('manual_mvw_refresh', 'STARTED');
    
    -- Call the refresh function from 04_materialized_views.sql
    RETURN QUERY
    SELECT * FROM dk.refresh_geo_mvws();
    
    CALL dk.log_geo_job_execution('manual_mvw_refresh', 'SUCCESS');
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Step 10: Final verification
-- ============================================================

-- Verify all components created
SELECT 
    'pgAgent Jobs' AS component,
    COUNT(*) AS count
FROM pgagent.pga_job
WHERE jobname LIKE 'ST-06%'

UNION ALL

SELECT 
    'pgAgent Schedules',
    COUNT(*)
FROM pgagent.pga_schedule s
JOIN pgagent.pga_job j ON s.jscjobid = j.jobid
WHERE j.jobname LIKE 'ST-06%'

UNION ALL

SELECT 
    'Monitoring Views',
    COUNT(*)
FROM information_schema.views
WHERE table_schema = 'dk' 
  AND table_name LIKE 'vw_geo_job%'

UNION ALL

SELECT 
    'Helper Functions',
    COUNT(*)
FROM information_schema.routines
WHERE routine_schema = 'dk' 
  AND (routine_name LIKE 'run_geo%' OR routine_name LIKE 'check_geo%' OR routine_name LIKE 'trigger_geo%');

-- Verification query from task requirements
SELECT jobname FROM pgagent.pga_job WHERE jobname LIKE 'ST-06%';

-- ============================================================
-- END OF FILE
-- ============================================================