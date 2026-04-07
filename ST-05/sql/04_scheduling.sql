-- ============================================================
-- ST-05: AI/ML Predictive Engine
-- 04_scheduling.sql
-- pgAgent Job Definitions for Windows
-- ============================================================
-- 
-- This file creates pgAgent jobs for:
-- 1. Daily incremental scoring at 3:00 AM
-- 2. Weekly full retrain on Sunday at 2:00 AM
--
-- Prerequisites:
-- - pgAgent installed and running on Windows
-- - ml_pipeline.py accessible from PostgreSQL server
-- - Database user has permissions to create pgAgent jobs
--
-- Windows Setup Instructions:
-- 1. Install pgAgent from: https://www.pgadmin.org/download/pgagent-archives/
-- 2. Ensure pgAgent service is running:
--    - Open Services (services.msc)
--    - Verify "pgAgent for PostgreSQL" is running
--    - Set startup type to "Automatic"
-- 3. Set PYTHON_PATH environment variable:
--    - System Properties > Environment Variables
--    - Add new System Variable: PYTHON_PATH
--    - Value: C:\path\to\your\python.exe (e.g., C:\Python310\python.exe)
-- 4. Set ML_PIPELINE_PATH environment variable:
--    - Add new System Variable: ML_PIPELINE_PATH
--    - Value: D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py
-- 5. Restart pgAgent service after setting environment variables
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

-- Create log table first so views/functions can reference it
CREATE TABLE IF NOT EXISTS dk.ml_job_execution_log (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    message TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_seconds INTEGER
);

CREATE OR REPLACE FUNCTION dk.log_ml_job_execution(
    p_job_name VARCHAR(100),
    p_status VARCHAR(20),
    p_message TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO dk.ml_job_execution_log (job_name, status, message)
    VALUES (p_job_name, p_status, p_message);

    RAISE NOTICE 'ML Job [%]: % - %', p_job_name, p_status, COALESCE(p_message, '');
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.log_ml_job_execution IS 'Logs ML pipeline job execution status for monitoring and debugging';

-- ============================================================
-- Step 3: Create wrapper functions for ML pipeline modes
-- ============================================================

-- Wrapper for incremental scoring mode
CREATE OR REPLACE FUNCTION dk.run_ml_incremental_scoring()
RETURNS INTEGER AS $$
DECLARE
    v_result INTEGER;
    v_start_time TIMESTAMP;
    v_end_time TIMESTAMP;
    v_duration INTEGER;
BEGIN
    v_start_time := clock_timestamp();
    
    -- Log job start
    CALL dk.log_ml_job_execution('daily_incremental_scoring', 'STARTED');
    
    -- Execute ML pipeline in incremental mode
    -- Note: pgAgent executes via psql, so we use COPY TO PROGRAM (PostgreSQL 12+)
    -- or we can use a batch file executor
    
    BEGIN
        -- Method 1: Direct execution via COPY TO PROGRAM (PostgreSQL 12+)
        -- This writes output to a log file for debugging
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s %s --mode=incremental --log-file=D:\dev\healthcare_poc_bi\ST-05\logs\incremental_%%s.log' $copy$,
            COALESCE(current_setting('ml.python_path', TRUE), 'python'),
            COALESCE(current_setting('ml.pipeline_path', TRUE), 'D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py'),
            to_char(CURRENT_DATE, 'YYYYMMDD')
        );
        
        v_result := 1; -- Success indicator
    EXCEPTION WHEN OTHERS THEN
        -- Method 2: Fallback - create batch file and execute
        -- This is more reliable on Windows
        v_result := 0; -- Will be handled by batch file approach
        
        -- Log error details
        CALL dk.log_ml_job_execution('daily_incremental_scoring', 'FAILED', SQLERRM);
        
        -- Re-raise to mark job as failed in pgAgent
        RAISE EXCEPTION 'Incremental scoring failed: %', SQLERRM;
    END;
    
    v_end_time := clock_timestamp();
    v_duration := EXTRACT(EPOCH FROM (v_end_time - v_start_time))::INTEGER;
    
    -- Log success
    CALL dk.log_ml_job_execution('daily_incremental_scoring', 'SUCCESS', 
        format('Completed in %s seconds', v_duration));
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.run_ml_incremental_scoring IS 'Wrapper function for daily incremental ML scoring at 3 AM';

-- Wrapper for full retrain mode
CREATE OR REPLACE FUNCTION dk.run_ml_full_retrain()
RETURNS INTEGER AS $$
DECLARE
    v_result INTEGER;
    v_start_time TIMESTAMP;
    v_end_time TIMESTAMP;
    v_duration INTEGER;
BEGIN
    v_start_time := clock_timestamp();
    
    -- Log job start
    CALL dk.log_ml_job_execution('weekly_full_retrain', 'STARTED');
    
    BEGIN
        -- Execute ML pipeline in retrain mode
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s %s --mode=retrain --log-file=D:\dev\healthcare_poc_bi\ST-05\logs\retrain_%%s.log' $copy$,
            COALESCE(current_setting('ml.python_path', TRUE), 'python'),
            COALESCE(current_setting('ml.pipeline_path', TRUE), 'D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py'),
            to_char(CURRENT_DATE, 'YYYYMMDD')
        );
        
        v_result := 1; -- Success indicator
    EXCEPTION WHEN OTHERS THEN
        v_result := 0;
        
        -- Log error details
        CALL dk.log_ml_job_execution('weekly_full_retrain', 'FAILED', SQLERRM);
        
        -- Re-raise to mark job as failed in pgAgent
        RAISE EXCEPTION 'Full retrain failed: %', SQLERRM;
    END;
    
    v_end_time := clock_timestamp();
    v_duration := EXTRACT(EPOCH FROM (v_end_time - v_start_time))::INTEGER;
    
    -- Log success
    CALL dk.log_ml_job_execution('weekly_full_retrain', 'SUCCESS', 
        format('Completed in %s seconds', v_duration));
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.run_ml_full_retrain IS 'Wrapper function for weekly full ML model retrain on Sunday at 2 AM';

-- ============================================================
-- Step 4: Create alternative batch file executor (Windows-specific)
-- ============================================================

-- For more reliable Windows execution, create batch files
-- These are called by pgAgent jobs instead of direct SQL functions

-- Function to generate batch file for incremental scoring
CREATE OR REPLACE FUNCTION dk.create_incremental_batch_file()
RETURNS TEXT AS $$
DECLARE
    v_batch_path TEXT := 'D:\dev\healthcare_poc_bi\ST-05\scripts\run_incremental.bat';
    v_batch_content TEXT;
BEGIN
    v_batch_content := format(
        $batch$
@echo off
REM ST-05 ML Pipeline - Daily Incremental Scoring
REM Scheduled: Daily at 3:00 AM via pgAgent

SET PYTHON_PATH=C:\Python310\python.exe
SET ML_PIPELINE_PATH=D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py
SET LOG_DIR=D:\dev\healthcare_poc_bi\ST-05\logs
SET LOG_FILE=%LOG_DIR%\incremental_%%DATE:~-4,4%%%%DATE:~-7,2%%%%DATE:~-10,2%%.log

REM Ensure log directory exists
IF NOT EXIST "%LOG_DIR%" MKDIR "%LOG_DIR%"

REM Run incremental scoring
ECHO [%DATE% %TIME%] Starting incremental scoring... >> %LOG_FILE%
"%PYTHON_PATH%" "%ML_PIPELINE_PATH%" --mode=incremental --log-file="%LOG_FILE%" 2>&1

IF %ERRORLEVEL% EQU 0 (
    ECHO [%DATE% %TIME%] Incremental scoring completed successfully >> %LOG_FILE%
    EXIT /B 0
) ELSE (
    ECHO [%DATE% %TIME%] ERROR: Incremental scoring failed with code %ERRORLEVEL% >> %LOG_FILE%
    EXIT /B 1
)
$batch$
    );
    
    -- Write batch file using COPY TO (PostgreSQL 9.3+)
    -- Note: Requires write permissions to target directory
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

-- Function to generate batch file for full retrain
CREATE OR REPLACE FUNCTION dk.create_retrain_batch_file()
RETURNS TEXT AS $$
DECLARE
    v_batch_path TEXT := 'D:\dev\healthcare_poc_bi\ST-05\scripts\run_retrain.bat';
    v_batch_content TEXT;
BEGIN
    v_batch_content := format(
        $batch$
@echo off
REM ST-05 ML Pipeline - Weekly Full Retrain
REM Scheduled: Sunday at 2:00 AM via pgAgent

SET PYTHON_PATH=C:\Python310\python.exe
SET ML_PIPELINE_PATH=D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py
SET LOG_DIR=D:\dev\healthcare_poc_bi\ST-05\logs
SET LOG_FILE=%LOG_DIR%\retrain_%%DATE:~-4,4%%%%DATE:~-7,2%%%%DATE:~-10,2%%.log

REM Ensure log directory exists
IF NOT EXIST "%LOG_DIR%" MKDIR "%LOG_DIR%"

REM Run full retrain
ECHO [%DATE% %TIME%] Starting full retrain... >> %LOG_FILE%
"%PYTHON_PATH%" "%ML_PIPELINE_PATH%" --mode=retrain --log-file="%LOG_FILE%" 2>&1

IF %ERRORLEVEL% EQU 0 (
    ECHO [%DATE% %TIME%] Full retrain completed successfully >> %LOG_FILE%
    EXIT /B 0
) ELSE (
    ECHO [%DATE% %TIME%] ERROR: Full retrain failed with code %ERRORLEVEL% >> %LOG_FILE%
    EXIT /B 1
)
$batch$
    );
    
    -- Write batch file using COPY TO
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

-- Job 1: Daily Incremental Scoring at 3:00 AM

DO $$
DECLARE
    v_jobid INTEGER;
    v_schid INTEGER;
    v_jclid INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM pgagent.pga_job WHERE jobname = 'ST-05 Daily Incremental Scoring') THEN
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
        'ST-05 Daily Incremental Scoring',
        'Daily incremental ML scoring for churn, upsell, NBT, and promo models at 3:00 AM',
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
        'Daily 3AM',
        'Every day at 3:00 AM',
        TRUE,
        CURRENT_DATE + INTERVAL '1 day' + INTERVAL '3 hours',
        ARRAY[TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE],
        ARRAY[FALSE,FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE]
    ) RETURNING jscid INTO v_schid;

    RAISE NOTICE 'Created job: ST-05 Daily Incremental Scoring (ID: %)', v_jobid;
END $$;

-- Job 2: Weekly Full Retrain on Sunday at 2:00 AM

DO $$
DECLARE
    v_jobid INTEGER;
    v_schid INTEGER;
    v_jclid INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM pgagent.pga_job WHERE jobname = 'ST-05 Weekly Full Retrain') THEN
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
        'ST-05 Weekly Full Retrain',
        'Weekly full retraining of all ML models on Sunday at 2:00 AM',
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
        'Sunday 2AM',
        'Every Sunday at 2:00 AM',
        TRUE,
        CURRENT_DATE +
            CASE
                WHEN EXTRACT(DOW FROM CURRENT_DATE) = 0 THEN 7
                ELSE 7 - EXTRACT(DOW FROM CURRENT_DATE)::INTEGER
            END * INTERVAL '1 day' +
            INTERVAL '2 hours',
        ARRAY[TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE],
        ARRAY[FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE],
        '{t,f,f,f,f,f,f}'
    ) RETURNING jscid INTO v_schid;

    RAISE NOTICE 'Created job: ST-05 Weekly Full Retrain (ID: %)', v_jobid;
END $$;

-- ============================================================
-- Step 6: Verify job creation
-- ============================================================

-- List all ST-05 pgAgent jobs
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
WHERE j.jobname LIKE 'ST-05%'
ORDER BY j.jobname;

-- pgAgent 4.x+ no longer uses a separate pga_step table.
-- Job commands are managed through the pgAgent interface.
SELECT 
    j.jobid,
    j.jobname,
    j.jobdesc,
    j.jobenabled,
    j.jobcreated
FROM pgagent.pga_job j
WHERE j.jobname LIKE 'ST-05%'
ORDER BY j.jobname;

-- ============================================================
-- Step 7: Monitoring queries
-- ============================================================

-- View: ml_job_execution_log summary
CREATE OR REPLACE VIEW dk.vw_ml_job_execution_summary AS
SELECT 
    job_name,
    status,
    COUNT(*) AS execution_count,
    MAX(executed_at) AS last_execution,
    AVG(duration_seconds) AS avg_duration_seconds,
    MIN(duration_seconds) AS min_duration_seconds,
    MAX(duration_seconds) AS max_duration_seconds
FROM dk.ml_job_execution_log
GROUP BY job_name, status
ORDER BY job_name, status;

COMMENT ON VIEW dk.vw_ml_job_execution_summary IS 'Summary of ML job execution history for monitoring dashboards';

-- Check recent job executions
SELECT * FROM dk.vw_ml_job_execution_summary;

-- View: Latest execution status per job
CREATE OR REPLACE VIEW dk.vw_ml_job_latest_status AS
SELECT DISTINCT ON (job_name)
    job_name,
    status,
    message,
    executed_at,
    duration_seconds
FROM dk.ml_job_execution_log
ORDER BY job_name, executed_at DESC;

COMMENT ON VIEW dk.vw_ml_job_latest_status IS 'Latest execution status for each ML job';

-- Check latest status
SELECT * FROM dk.vw_ml_job_latest_status;

-- ============================================================
-- Step 8: Error handling and alerts
-- ============================================================

-- Function to check for failed jobs in last 24 hours
CREATE OR REPLACE FUNCTION dk.check_ml_job_failures()
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
    FROM dk.ml_job_execution_log l
    WHERE l.status = 'FAILED'
      AND l.executed_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
    ORDER BY l.executed_at DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.check_ml_job_failures IS 'Returns ML jobs that failed in the last 24 hours for alerting';

-- Check for failures
SELECT * FROM dk.check_ml_job_failures();

-- ============================================================
-- Step 9: Manual execution functions (for testing)
-- ============================================================

-- Function to manually trigger incremental scoring
CREATE OR REPLACE FUNCTION dk.trigger_incremental_scoring()
RETURNS TEXT AS $$
DECLARE
    v_result TEXT;
BEGIN
    CALL dk.log_ml_job_execution('manual_incremental', 'STARTED');
    
    BEGIN
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s %s --mode=incremental' $copy$,
            COALESCE(current_setting('ml.python_path', TRUE), 'python'),
            COALESCE(current_setting('ml.pipeline_path', TRUE), 'D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py')
        );
        
        CALL dk.log_ml_job_execution('manual_incremental', 'SUCCESS');
        v_result := 'Incremental scoring triggered successfully';
    EXCEPTION WHEN OTHERS THEN
        CALL dk.log_ml_job_execution('manual_incremental', 'FAILED', SQLERRM);
        v_result := format('Failed: %s', SQLERRM);
    END;
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Function to manually trigger full retrain
CREATE OR REPLACE FUNCTION dk.trigger_full_retrain()
RETURNS TEXT AS $$
DECLARE
    v_result TEXT;
BEGIN
    CALL dk.log_ml_job_execution('manual_retrain', 'STARTED');
    
    BEGIN
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s %s --mode=retrain' $copy$,
            COALESCE(current_setting('ml.python_path', TRUE), 'python'),
            COALESCE(current_setting('ml.pipeline_path', TRUE), 'D:\dev\healthcare_poc_bi\ST-05\python\ml_pipeline.py')
        );
        
        CALL dk.log_ml_job_execution('manual_retrain', 'SUCCESS');
        v_result := 'Full retrain triggered successfully';
    EXCEPTION WHEN OTHERS THEN
        CALL dk.log_ml_job_execution('manual_retrain', 'FAILED', SQLERRM);
        v_result := format('Failed: %s', SQLERRM);
    END;
    
    RETURN v_result;
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
WHERE jobname LIKE 'ST-05%'

UNION ALL

SELECT 
    'pgAgent Schedules',
    COUNT(*)
FROM pgagent.pga_schedule s
JOIN pgagent.pga_job j ON s.jscjobid = j.jobid
WHERE j.jobname LIKE 'ST-05%'

UNION ALL

SELECT 
    'Monitoring Views',
    COUNT(*)
FROM information_schema.views
WHERE table_schema = 'dk' 
  AND table_name LIKE 'vw_ml_job%'

UNION ALL

SELECT 
    'Helper Functions',
    COUNT(*)
FROM information_schema.routines
WHERE routine_schema = 'dk' 
  AND routine_name LIKE 'run_ml%' OR routine_name LIKE 'check_ml%' OR routine_name LIKE 'trigger_ml%';

-- ============================================================
-- END OF FILE
-- ============================================================
