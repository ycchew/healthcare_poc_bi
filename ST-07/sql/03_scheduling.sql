-- ============================================================
-- ST-07: Automation & Campaigns
-- 03_scheduling.sql
-- ============================================================
-- pgAgent Job Definitions for Windows
-- Creates job log table and wrapper functions for 8 scheduled jobs:
-- 1. st07_queue_appointment_reminders - Daily 08:00 AM
-- 2. st07_queue_no_show_followup - Daily 12:00 PM
-- 3. st07_queue_churn_prevention - Weekly Mon 09:00
-- 4. st07_queue_upsell_campaign - Weekly Wed 09:00
-- 5. st07_queue_dynamic_pricing - Weekly Fri 09:00
-- 6. st07_queue_reactivation - Monthly 1st Mon 09:00
-- 7. st07_process_queue - Every 5 min
-- 8. st07_refresh_stats - Daily 06:00 AM
--
-- Prerequisites:
-- - pgAgent installed and running on Windows
-- - Required configuration set via current_setting() or postgresql.conf:
--   st07.python_path = path to python.exe
--   st07.project_root = D:\dev\healthcare_poc_bi
--   st07.campaign_sender_path = ST-07/python/campaign_sender.py
-- ============================================================

-- ============================================================
-- Step 1: Verify pgAgent extension
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pgagent;

-- ============================================================
-- Step 2: Create log table and helper
-- ============================================================
CREATE TABLE IF NOT EXISTS dk.st07_job_execution_log (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    message TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_seconds INTEGER
);

CREATE OR REPLACE FUNCTION dk.log_st07_job(
    p_job_name VARCHAR(100),
    p_status VARCHAR(20),
    p_message TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO dk.st07_job_execution_log (job_name, status, message)
    VALUES (p_job_name, p_status, p_message);
    RAISE NOTICE 'ST07 Job [%]: % - %', p_job_name, p_status, COALESCE(p_message, '');
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.log_st07_job IS 'Logs ST-07 campaign job execution status for monitoring';

-- ============================================================
-- Step 3: Wrapper functions for campaign operations
-- ============================================================

-- Wrapper: Queue appointment reminders
CREATE OR REPLACE FUNCTION dk.run_st07_appointment_reminders() RETURNS INTEGER AS $$
DECLARE
    v_start_time TIMESTAMP;
    v_end_time TIMESTAMP;
    v_duration INTEGER;
BEGIN
    v_start_time := clock_timestamp();
    CALL dk.log_st07_job('st07_appointment_reminders', 'STARTED');

    BEGIN
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s "%s%s%s"' $copy$,
            COALESCE(current_setting('st07.python_path', TRUE), 'python'),
            COALESCE(current_setting('st07.project_root', TRUE), ''),
            CASE WHEN current_setting('st07.project_root', TRUE) != '' THEN '\' ELSE '' END,
            COALESCE(current_setting('st07.campaign_sender_path', TRUE), 'ST-07/python/campaign_sender.py')
        );
    EXCEPTION WHEN OTHERS THEN
        CALL dk.log_st07_job('st07_appointment_reminders', 'FAILED', SQLERRM);
        RAISE EXCEPTION 'Appointment reminders failed: %', SQLERRM;
    END;

    v_end_time := clock_timestamp();
    v_duration := EXTRACT(EPOCH FROM (v_end_time - v_start_time))::INTEGER;
    CALL dk.log_st07_job('st07_appointment_reminders', 'SUCCESS', format('Completed in %ss', v_duration));
    RETURN 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.run_st07_appointment_reminders IS 'Wrapper for daily appointment reminders at 08:00 AM';

-- Wrapper: Process queue (the sender)
CREATE OR REPLACE FUNCTION dk.run_st07_process_queue() RETURNS INTEGER AS $$
DECLARE
    v_start_time TIMESTAMP;
    v_end_time TIMESTAMP;
    v_duration INTEGER;
BEGIN
    v_start_time := clock_timestamp();

    BEGIN
        EXECUTE format(
            $copy$ COPY (SELECT 1) TO PROGRAM '%s "%s%s%s"' $copy$,
            COALESCE(current_setting('st07.python_path', TRUE), 'python'),
            COALESCE(current_setting('st07.project_root', TRUE), ''),
            CASE WHEN current_setting('st07.project_root', TRUE) != '' THEN '\' ELSE '' END,
            COALESCE(current_setting('st07.campaign_sender_path', TRUE), 'ST-07/python/campaign_sender.py')
        );
    EXCEPTION WHEN OTHERS THEN
        CALL dk.log_st07_job('st07_process_queue', 'FAILED', SQLERRM);
        RAISE EXCEPTION 'Queue processing failed: %', SQLERRM;
    END;

    v_end_time := clock_timestamp();
    v_duration := EXTRACT(EPOCH FROM (v_end_time - v_start_time))::INTEGER;
    CALL dk.log_st07_job('st07_process_queue', 'SUCCESS', format('Completed in %ss', v_duration));
    RETURN 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.run_st07_process_queue IS 'Wrapper for queue processing every 5 minutes';

-- Wrapper: Refresh stats
CREATE OR REPLACE FUNCTION dk.run_st07_refresh_stats() RETURNS INTEGER AS $$
BEGIN
    CALL dk.log_st07_job('st07_refresh_stats', 'STARTED');
    PERFORM dk.refresh_campaign_stats();
    CALL dk.log_st07_job('st07_refresh_stats', 'SUCCESS', 'Stats refreshed');
    RETURN 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dk.run_st07_refresh_stats IS 'Wrapper for daily stats refresh at 06:00 AM';

-- ============================================================
-- Step 4: pgAgent Job Definitions
-- ============================================================
-- NOTE: pgAgent jobs are created via the pgAdmin UI or pgAgent's
-- internal API. The following are conceptual definitions.
-- In practice, create these jobs through pgAdmin:
--
-- Job: st07_queue_appointment_reminders
--   Schedule: Daily at 08:00
--   Step: SELECT dk.run_st07_appointment_reminders();
--
-- Job: st07_queue_no_show_followup
--   Schedule: Daily at 12:00
--   Step: Queue no-show follow-ups (implement similar wrapper)
--
-- Job: st07_queue_churn_prevention
--   Schedule: Weekly, Monday at 09:00
--   Step: Queue churn prevention (implement similar wrapper)
--
-- Job: st07_queue_upsell_campaign
--   Schedule: Weekly, Wednesday at 09:00
--   Step: Queue upsell campaigns (implement similar wrapper)
--
-- Job: st07_queue_dynamic_pricing
--   Schedule: Weekly, Friday at 09:00
--   Step: Queue pricing offers (implement similar wrapper)
--
-- Job: st07_queue_reactivation
--   Schedule: Monthly, 1st Monday at 09:00
--   Step: Queue reactivation (implement similar wrapper)
--
-- Job: st07_process_queue
--   Schedule: Every 5 minutes
--   Step: SELECT dk.run_st07_process_queue();
--
-- Job: st07_refresh_stats
--   Schedule: Daily at 06:00
--   Step: SELECT dk.run_st07_refresh_stats();
-- ============================================================

-- Verify
SELECT routine_name FROM information_schema.routines 
WHERE routine_schema = 'dk' AND routine_name LIKE 'run_st07_%'
ORDER BY routine_name;
