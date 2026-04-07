-- ============================================================
-- ST-07: Automation & Campaigns
-- 01_campaign_tables.sql
-- ============================================================
-- Creates all campaign-related tables in dk schema:
-- 1. dk.whatsapp_templates - Meta-approved message templates
-- 2. dk.campaign_queue - Outbound message queue
-- 3. dk.delivery_log - Full message lifecycle tracking
-- 4. dk.patient_consent - PDPA-compliant opt-in/opt-out tracking
-- 5. dk.campaign_stats - Aggregated daily campaign performance
-- ============================================================

-- ============================================================
-- 1. WhatsApp Templates
-- ============================================================
CREATE TABLE IF NOT EXISTS dk.whatsapp_templates (
    template_id SERIAL PRIMARY KEY,
    template_name VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(20) NOT NULL CHECK (category IN ('utility', 'marketing', 'authentication')),
    language VARCHAR(10) DEFAULT 'en',
    body_text TEXT NOT NULL,
    variables_schema JSONB,
    status VARCHAR(20) DEFAULT 'pending_approval' CHECK (status IN ('pending_approval', 'approved', 'rejected')),
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE dk.whatsapp_templates IS 'WhatsApp message templates registered with Meta';

-- ============================================================
-- 2. Campaign Queue
-- ============================================================
CREATE TABLE IF NOT EXISTS dk.campaign_queue (
    queue_id BIGSERIAL PRIMARY KEY,
    mrn VARCHAR(50) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    template_name VARCHAR(100) NOT NULL,
    template_params JSONB NOT NULL,
    trigger_type VARCHAR(20) NOT NULL CHECK (trigger_type IN ('scheduled', 'event', 'manual')),
    campaign_type VARCHAR(50) NOT NULL CHECK (campaign_type IN (
        'appointment_reminder', 'no_show_followup', 'churn_prevention',
        'upsell_recommendation', 'dynamic_pricing_offer', 'reactivation',
        'marketing_broadcast'
    )),
    priority SMALLINT DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
    scheduled_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')),
    retry_count SMALLINT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);

-- Index for queue processor (the hot path)
CREATE INDEX IF NOT EXISTS idx_campaign_queue_status_priority
    ON dk.campaign_queue (status, priority, scheduled_at NULLS FIRST)
    WHERE status = 'pending';

-- Index for patient-level queries
CREATE INDEX IF NOT EXISTS idx_campaign_queue_mrn
    ON dk.campaign_queue (mrn);

COMMENT ON TABLE dk.campaign_queue IS 'Outbound message queue - single source of truth for all sends';

-- ============================================================
-- 3. Delivery Log
-- ============================================================
CREATE TABLE IF NOT EXISTS dk.delivery_log (
    log_id BIGSERIAL PRIMARY KEY,
    queue_id BIGINT NOT NULL REFERENCES dk.campaign_queue(queue_id),
    whatsapp_message_id VARCHAR(100),
    status VARCHAR(20) NOT NULL CHECK (status IN ('sent', 'delivered', 'read', 'failed')),
    status_timestamp TIMESTAMPTZ DEFAULT NOW(),
    raw_response JSONB
);

-- Unique constraint to prevent duplicate delivery updates
CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_log_queue_status
    ON dk.delivery_log (queue_id, status);

-- Index for webhook lookups
CREATE INDEX IF NOT EXISTS idx_delivery_log_whatsapp_id
    ON dk.delivery_log (whatsapp_message_id);

COMMENT ON TABLE dk.delivery_log IS 'Full message lifecycle tracking via WhatsApp webhooks';

-- ============================================================
-- 4. Patient Consent
-- ============================================================
CREATE TABLE IF NOT EXISTS dk.patient_consent (
    consent_id SERIAL PRIMARY KEY,
    mrn VARCHAR(50) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    consent_given BOOLEAN DEFAULT TRUE,
    consent_timestamp TIMESTAMPTZ DEFAULT NOW(),
    consent_source VARCHAR(30) CHECK (consent_source IN ('registration', 'import', 'manual')),
    opt_out_timestamp TIMESTAMPTZ,
    opt_out_reason VARCHAR(200)
);

-- Unique constraint: one active consent record per mrn + phone
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_consent_mrn_phone
    ON dk.patient_consent (mrn, phone_number);

COMMENT ON TABLE dk.patient_consent IS 'PDPA-compliant opt-in/opt-out tracking for WhatsApp messaging';

-- ============================================================
-- 5. Campaign Stats
-- ============================================================
CREATE TABLE IF NOT EXISTS dk.campaign_stats (
    stat_id SERIAL PRIMARY KEY,
    campaign_type VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    queued INTEGER DEFAULT 0,
    sent INTEGER DEFAULT 0,
    delivered INTEGER DEFAULT 0,
    "read" INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    opt_outs INTEGER DEFAULT 0
);

-- One row per campaign type per day
CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_stats_type_date
    ON dk.campaign_stats (campaign_type, date);

COMMENT ON TABLE dk.campaign_stats IS 'Aggregated daily campaign performance for Power BI dashboards';
