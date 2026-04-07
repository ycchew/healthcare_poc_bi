-- ============================================================
-- ST-07: Automation & Campaigns
-- 02_campaign_views.sql
-- ============================================================
-- Creates views and functions for campaign management:
-- Views:
--   1. vw_campaign_queue_pending - Items ready to send
--   2. vw_campaign_performance - Daily delivery/read rates
--   3. vw_patient_communication_status - Patient-level comm status
-- Functions:
--   1. dk.check_patient_consent(mrn, phone_number) -> boolean
--   2. dk.queue_campaign_message(...) -> bigint
--   3. dk.update_delivery_status(...) -> void
--   4. dk.refresh_campaign_stats() -> void
--   5. dk.cancel_pending_for_opted_out(mrn) -> void
-- ============================================================

-- ============================================================
-- Views
-- ============================================================

-- View: Pending items ready to send
CREATE OR REPLACE VIEW dk.vw_campaign_queue_pending AS
SELECT 
    cq.queue_id,
    cq.mrn,
    cq.phone_number,
    cq.template_name,
    cq.template_params,
    cq.trigger_type,
    cq.campaign_type,
    cq.priority,
    cq.scheduled_at,
    cq.created_at
FROM dk.campaign_queue cq
INNER JOIN dk.patient_consent pc 
    ON cq.mrn = pc.mrn AND cq.phone_number = pc.phone_number
WHERE cq.status = 'pending'
  AND (cq.scheduled_at IS NULL OR cq.scheduled_at <= NOW())
  AND pc.consent_given = TRUE
  AND pc.opt_out_timestamp IS NULL
ORDER BY cq.priority ASC, cq.scheduled_at ASC NULLS FIRST, cq.created_at ASC;

COMMENT ON VIEW dk.vw_campaign_queue_pending IS 'Pending campaign items ready to send (consent verified)';

-- View: Campaign performance dashboard
CREATE OR REPLACE VIEW dk.vw_campaign_performance AS
SELECT 
    cs.campaign_type,
    cs.date,
    cs.queued,
    cs.sent,
    cs.delivered,
    cs."read",
    cs.failed,
    cs.opt_outs,
    CASE WHEN cs.sent > 0 THEN ROUND(cs.delivered::NUMERIC / cs.sent * 100, 2) ELSE 0 END AS delivery_rate_pct,
    CASE WHEN cs.delivered > 0 THEN ROUND(cs."read"::NUMERIC / cs.delivered * 100, 2) ELSE 0 END AS read_rate_pct,
    CASE WHEN cs.sent > 0 THEN ROUND(cs.failed::NUMERIC / cs.sent * 100, 2) ELSE 0 END AS failure_rate_pct
FROM dk.campaign_stats cs
ORDER BY cs.date DESC, cs.campaign_type;

COMMENT ON VIEW dk.vw_campaign_performance IS 'Daily campaign performance with delivery and read rates';

-- View: Patient communication status
CREATE OR REPLACE VIEW dk.vw_patient_communication_status AS
SELECT 
    p.mrn,
    p.location,
    pc.phone_number,
    pc.consent_given,
    pc.consent_timestamp,
    pc.opt_out_timestamp,
    pc.consent_source,
    last_msg.campaign_type AS last_campaign_type,
    last_msg.sent_at AS last_message_sent,
    last_dl.status AS last_delivery_status,
    last_dl.status_timestamp AS last_delivery_timestamp
FROM dk.patient p
LEFT JOIN dk.patient_consent pc ON p.mrn = pc.mrn
LEFT JOIN LATERAL (
    SELECT cq.campaign_type, cq.sent_at
    FROM dk.campaign_queue cq
    WHERE cq.mrn = p.mrn AND cq.status = 'sent'
    ORDER BY cq.sent_at DESC
    LIMIT 1
) last_msg ON true
LEFT JOIN LATERAL (
    SELECT dl.status, dl.status_timestamp
    FROM dk.delivery_log dl
    INNER JOIN dk.campaign_queue cq ON dl.queue_id = cq.queue_id
    WHERE cq.mrn = p.mrn
    ORDER BY dl.status_timestamp DESC
    LIMIT 1
) last_dl ON true
ORDER BY p.mrn;

COMMENT ON VIEW dk.vw_patient_communication_status IS 'Patient-level communication status: consent, last message, delivery';

-- ============================================================
-- Functions
-- ============================================================

-- Function: Check patient consent
CREATE OR REPLACE FUNCTION dk.check_patient_consent(
    p_mrn VARCHAR(50),
    p_phone_number VARCHAR(20)
) RETURNS BOOLEAN AS $$
DECLARE
    v_consent BOOLEAN;
BEGIN
    SELECT consent_given AND opt_out_timestamp IS NULL
    INTO v_consent
    FROM dk.patient_consent
    WHERE mrn = p_mrn AND phone_number = p_phone_number;
    
    RETURN COALESCE(v_consent, FALSE);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION dk.check_patient_consent IS 'Returns true if patient has active consent for WhatsApp messaging';

-- Function: Queue a campaign message
CREATE OR REPLACE FUNCTION dk.queue_campaign_message(
    p_mrn VARCHAR(50),
    p_phone_number VARCHAR(20),
    p_template_name VARCHAR(100),
    p_template_params JSONB,
    p_trigger_type VARCHAR(20),
    p_campaign_type VARCHAR(50),
    p_priority SMALLINT DEFAULT 3,
    p_scheduled_at TIMESTAMPTZ DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_queue_id BIGINT;
    v_has_consent BOOLEAN;
BEGIN
    -- Check consent first
    v_has_consent := dk.check_patient_consent(p_mrn, p_phone_number);
    
    IF NOT v_has_consent THEN
        RAISE NOTICE 'Patient % (%) has no consent - message not queued', p_mrn, p_phone_number;
        RETURN NULL;
    END IF;
    
    -- Validate template exists and is approved
    IF NOT EXISTS (
        SELECT 1 FROM dk.whatsapp_templates 
        WHERE template_name = p_template_name AND status = 'approved'
    ) THEN
        RAISE WARNING 'Template % not found or not approved', p_template_name;
    END IF;
    
    -- Insert into queue
    INSERT INTO dk.campaign_queue (
        mrn, phone_number, template_name, template_params,
        trigger_type, campaign_type, priority, scheduled_at
    ) VALUES (
        p_mrn, p_phone_number, p_template_name, p_template_params,
        p_trigger_type, p_campaign_type, p_priority, p_scheduled_at
    ) RETURNING queue_id INTO v_queue_id;
    
    RETURN v_queue_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION dk.queue_campaign_message IS 'Queue a campaign message with consent validation';

-- Function: Update delivery status (called by webhook handler)
CREATE OR REPLACE FUNCTION dk.update_delivery_status(
    p_queue_id BIGINT,
    p_whatsapp_message_id VARCHAR(100),
    p_status VARCHAR(20),
    p_raw_response JSONB DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    -- Insert or update delivery log
    INSERT INTO dk.delivery_log (queue_id, whatsapp_message_id, status, raw_response)
    VALUES (p_queue_id, p_whatsapp_message_id, p_status, p_raw_response)
    ON CONFLICT (queue_id, status) DO UPDATE SET
        whatsapp_message_id = EXCLUDED.whatsapp_message_id,
        raw_response = EXCLUDED.raw_response,
        status_timestamp = NOW();
    
    -- Update campaign_queue status if sent
    IF p_status = 'sent' THEN
        UPDATE dk.campaign_queue 
        SET status = 'sent', sent_at = NOW()
        WHERE queue_id = p_queue_id AND status IN ('pending', 'processing');
    END IF;
    
    -- If failed, update queue
    IF p_status = 'failed' THEN
        UPDATE dk.campaign_queue 
        SET status = 'failed', error_message = p_raw_response::TEXT
        WHERE queue_id = p_queue_id AND status != 'cancelled';
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION dk.update_delivery_status IS 'Update delivery status from webhook events';

-- Function: Refresh campaign stats
CREATE OR REPLACE FUNCTION dk.refresh_campaign_stats() RETURNS VOID AS $$
BEGIN
    -- Upsert daily stats from campaign_queue and delivery_log
    INSERT INTO dk.campaign_stats (campaign_type, date, queued, sent, delivered, "read", failed, opt_outs)
    SELECT 
        cq.campaign_type,
        cq.created_at::DATE AS date,
        COUNT(*) FILTER (WHERE cq.status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')) AS queued,
        COUNT(*) FILTER (WHERE cq.status = 'sent') AS sent,
        COUNT(DISTINCT dl.queue_id) FILTER (WHERE dl.status = 'delivered') AS delivered,
        COUNT(DISTINCT dl.queue_id) FILTER (WHERE dl.status = 'read') AS "read",
        COUNT(*) FILTER (WHERE cq.status = 'failed') AS failed,
        0 AS opt_outs  -- Tracked separately from consent table
    FROM dk.campaign_queue cq
    LEFT JOIN dk.delivery_log dl ON cq.queue_id = dl.queue_id
    WHERE cq.created_at::DATE >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY cq.campaign_type, cq.created_at::DATE
    ON CONFLICT (campaign_type, date) DO UPDATE SET
        queued = EXCLUDED.queued,
        sent = EXCLUDED.sent,
        delivered = EXCLUDED.delivered,
        "read" = EXCLUDED."read",
        failed = EXCLUDED.failed;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION dk.refresh_campaign_stats IS 'Aggregate delivery_log into campaign_stats daily';

-- Function: Cancel pending messages for opted-out patient
CREATE OR REPLACE FUNCTION dk.cancel_pending_for_opted_out(
    p_mrn VARCHAR(50)
) RETURNS VOID AS $$
BEGIN
    UPDATE dk.campaign_queue
    SET status = 'cancelled', error_message = 'Patient opted out'
    WHERE mrn = p_mrn AND status IN ('pending', 'processing');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION dk.cancel_pending_for_opted_out IS 'Cancel all pending queue items for a patient who opted out';