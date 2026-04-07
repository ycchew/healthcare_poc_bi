-- ============================================================
-- ST-07: Automation & Campaigns
-- automation_campaign_views.sql
-- Views for WhatsApp Campaigns and Conversion Tracking
-- ============================================================

-- ============================================================
-- TABLE: WhatsApp Campaign Templates
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.whatsapp_campaign_templates (
    template_id SERIAL PRIMARY KEY,
    template_name VARCHAR(200) NOT NULL,
    template_code VARCHAR(50) UNIQUE NOT NULL,
    template_type VARCHAR(100),  -- 'followup', 'promotional', 'reminder', 'winback'
    language_code VARCHAR(10) DEFAULT 'en',
    message_body TEXT NOT NULL,
    message_header VARCHAR(60),
    message_footer VARCHAR(60),
    button_type VARCHAR(50),  -- 'none', 'quick_reply', 'url'
    button_text VARCHAR(50),
    button_url VARCHAR(500),
    parameters JSONB,  -- Dynamic parameter placeholders
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample templates
INSERT INTO dk.whatsapp_campaign_templates 
(template_name, template_code, template_type, message_body, message_header, button_type, button_text)
VALUES 
('D+3 Follow-up', 'd3_followup', 'followup', 
 'Hi {{patient_name}}, thank you for visiting {{branch_name}}. How are you feeling after your {{treatment_name}}? We''d love to help you with your next session. Reply to book!', 
 'Follow-up from {{branch_name}}', 'quick_reply', 'Book Now'),

('Win-back Campaign', 'winback_30d', 'winback',
 'Hi {{patient_name}}, we miss you at {{branch_name}}! It''s been {{days_since_visit}} days since your last visit. Here''s a special 10% discount for your next treatment. Valid for 7 days!',
 'We miss you!', 'quick_reply', 'Claim Offer'),

('Package Reminder', 'package_reminder', 'reminder',
 'Hi {{patient_name}}, you have {{sessions_remaining}} sessions remaining in your {{package_name}}. Ready to schedule your next session?',
 'Package Reminder', 'quick_reply', 'Schedule Now')
ON CONFLICT (template_code) DO NOTHING;

-- ============================================================
-- TABLE: Campaigns
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.campaigns (
    campaign_id SERIAL PRIMARY KEY,
    campaign_name VARCHAR(200) NOT NULL,
    campaign_type VARCHAR(100),  -- 'd3_followup', 'rfm_targeted', 'winback', 'promotional'
    target_segment VARCHAR(100),
    target_rfm_segments TEXT[],
    template_code VARCHAR(50) REFERENCES dk.whatsapp_campaign_templates(template_code),
    start_date DATE,
    end_date DATE,
    target_patient_count INTEGER,
    message_sent_count INTEGER DEFAULT 0,
    message_delivered_count INTEGER DEFAULT 0,
    message_read_count INTEGER DEFAULT 0,
    response_count INTEGER DEFAULT 0,
    conversion_count INTEGER DEFAULT 0,
    conversion_revenue DECIMAL(15, 2) DEFAULT 0,
    status VARCHAR(50) DEFAULT 'draft',  -- 'draft', 'scheduled', 'running', 'completed', 'stopped'
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE: Campaign Patient Assignments
-- ============================================================

CREATE TABLE IF NOT EXISTS dk.campaign_assignments (
    assignment_id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES dk.campaigns(campaign_id),
    mrn VARCHAR(50) REFERENCES dk.patient(mrn),
    patient_name VARCHAR(200),
    phone VARCHAR(50),
    rfm_segment VARCHAR(100),
    ltv_segment VARCHAR(100),
    priority_score INTEGER,
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'sent', 'delivered', 'read', 'responded', 'converted', 'failed'
    message_id VARCHAR(100),  -- WhatsApp message ID
    sent_at TIMESTAMP,
    delivered_at TIMESTAMP,
    read_at TIMESTAMP,
    responded_at TIMESTAMP,
    converted_at TIMESTAMP,
    response_text TEXT,
    conversion_order_id VARCHAR(100),
    conversion_revenue DECIMAL(15, 2),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_campaign_assign_campaign ON dk.campaign_assignments(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_assign_mrn ON dk.campaign_assignments(mrn);
CREATE INDEX IF NOT EXISTS idx_campaign_assign_status ON dk.campaign_assignments(status);

-- ============================================================
-- VIEW: Campaign Performance Summary
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_campaign_performance AS
SELECT 
    c.campaign_id,
    c.campaign_name,
    c.campaign_type,
    c.target_segment,
    c.start_date,
    c.end_date,
    c.target_patient_count,
    c.status,
    COUNT(ca.assignment_id) AS total_assigned,
    COUNT(*) FILTER (WHERE ca.status IN ('sent', 'delivered', 'read', 'responded', 'converted')) AS sent_count,
    COUNT(*) FILTER (WHERE ca.status IN ('delivered', 'read', 'responded', 'converted')) AS delivered_count,
    COUNT(*) FILTER (WHERE ca.status IN ('read', 'responded', 'converted')) AS read_count,
    COUNT(*) FILTER (WHERE ca.status IN ('responded', 'converted')) AS response_count,
    COUNT(*) FILTER (WHERE ca.status = 'converted') AS conversion_count,
    COALESCE(SUM(ca.conversion_revenue), 0) AS total_conversion_revenue,
    -- Calculate rates
    CASE 
        WHEN COUNT(*) FILTER (WHERE ca.status IN ('sent', 'delivered', 'read', 'responded', 'converted')) > 0 
        THEN ROUND(COUNT(*) FILTER (WHERE ca.status IN ('delivered', 'read', 'responded', 'converted'))::NUMERIC / 
             COUNT(*) FILTER (WHERE ca.status IN ('sent', 'delivered', 'read', 'responded', 'converted')) * 100, 2)
        ELSE 0 
    END AS delivery_rate_pct,
    CASE 
        WHEN COUNT(*) FILTER (WHERE ca.status IN ('delivered', 'read', 'responded', 'converted')) > 0 
        THEN ROUND(COUNT(*) FILTER (WHERE ca.status IN ('read', 'responded', 'converted'))::NUMERIC / 
             COUNT(*) FILTER (WHERE ca.status IN ('delivered', 'read', 'responded', 'converted')) * 100, 2)
        ELSE 0 
    END AS read_rate_pct,
    CASE 
        WHEN COUNT(*) FILTER (WHERE ca.status IN ('read', 'responded', 'converted')) > 0 
        THEN ROUND(COUNT(*) FILTER (WHERE ca.status IN ('responded', 'converted'))::NUMERIC / 
             COUNT(*) FILTER (WHERE ca.status IN ('read', 'responded', 'converted')) * 100, 2)
        ELSE 0 
    END AS response_rate_pct,
    CASE 
        WHEN COUNT(*) FILTER (WHERE ca.status IN ('responded', 'converted')) > 0 
        THEN ROUND(COUNT(*) FILTER (WHERE ca.status = 'converted')::NUMERIC / 
             COUNT(*) FILTER (WHERE ca.status IN ('responded', 'converted')) * 100, 2)
        ELSE 0 
    END AS conversion_rate_pct
FROM dk.campaigns c
LEFT JOIN dk.campaign_assignments ca ON c.campaign_id = ca.campaign_id
GROUP BY c.campaign_id, c.campaign_name, c.campaign_type, c.target_segment, 
         c.start_date, c.end_date, c.target_patient_count, c.status;

-- ============================================================
-- VIEW: Campaign Patient Details
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_campaign_patient_details AS
SELECT 
    ca.assignment_id,
    ca.campaign_id,
    c.campaign_name,
    ca.mrn,
    ca.patient_name,
    ca.phone,
    ca.rfm_segment,
    ca.ltv_segment,
    ca.priority_score,
    ca.status,
    ca.sent_at,
    ca.delivered_at,
    ca.read_at,
    ca.responded_at,
    ca.converted_at,
    ca.response_text,
    ca.conversion_order_id,
    ca.conversion_revenue,
    -- Calculate time metrics
    CASE 
        WHEN ca.delivered_at IS NOT NULL AND ca.sent_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (ca.delivered_at - ca.sent_at)) / 60 
        ELSE NULL 
    END AS time_to_deliver_minutes,
    CASE 
        WHEN ca.read_at IS NOT NULL AND ca.delivered_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (ca.read_at - ca.delivered_at)) / 3600 
        ELSE NULL 
    END AS time_to_read_hours,
    CASE 
        WHEN ca.converted_at IS NOT NULL AND ca.sent_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (ca.converted_at - ca.sent_at)) / 86400 
        ELSE NULL 
    END AS time_to_conversion_days
FROM dk.campaign_assignments ca
JOIN dk.campaigns c ON ca.campaign_id = c.campaign_id;

-- ============================================================
-- VIEW: D+3 Follow-up Queue
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_d3_followup_queue AS
SELECT 
    d3.mrn,
    d3.patient_name,
    d3.phone,
    d3.email,
    d3.last_visit_date,
    d3.last_branch,
    d3.last_doctor,
    d3.last_visit_amount,
    d3.followup_priority,
    d3.rfm_segment,
    d3.ltv_segment,
    d3.value_tier,
    d3.churn_risk,
    d3.suggested_whatsapp_message,
    d3.is_campaign_eligible,
    -- Check if already in an active campaign
    NOT EXISTS (
        SELECT 1 FROM dk.campaign_assignments ca
        JOIN dk.campaigns c ON ca.campaign_id = c.campaign_id
        WHERE ca.mrn = d3.mrn
          AND c.campaign_type = 'd3_followup'
          AND c.status IN ('running', 'scheduled')
          AND ca.created_at >= CURRENT_DATE - INTERVAL '7 days'
    ) AS is_available_for_campaign
FROM dk.vw_d3_followup_enhanced d3
WHERE d3.followup_priority IN ('High Priority', 'Medium Priority')
ORDER BY 
    CASE d3.followup_priority 
        WHEN 'High Priority' THEN 1 
        WHEN 'Medium Priority' THEN 2 
        ELSE 3 
    END,
    d3.last_visit_amount DESC;

-- ============================================================
-- VIEW: Conversion Attribution
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_conversion_attribution AS
WITH campaign_conversions AS (
    SELECT 
        ca.mrn,
        ca.campaign_id,
        c.campaign_name,
        c.campaign_type,
        ca.converted_at,
        ca.conversion_revenue,
        ca.conversion_order_id,
        ca.sent_at AS campaign_sent_at
    FROM dk.campaign_assignments ca
    JOIN dk.campaigns c ON ca.campaign_id = c.campaign_id
    WHERE ca.status = 'converted'
),
natural_conversions AS (
    SELECT 
        mrn,
        MIN(transaction_date) AS first_transaction_after_campaign
    FROM dk.mvw_transaction_flat
    GROUP BY mrn
)
SELECT 
    cc.mrn,
    cc.campaign_id,
    cc.campaign_name,
    cc.campaign_type,
    cc.campaign_sent_at,
    cc.converted_at,
    cc.conversion_revenue,
    cc.conversion_order_id,
    EXTRACT(DAY FROM (cc.converted_at - cc.campaign_sent_at)) AS days_to_convert,
    CASE 
        WHEN EXTRACT(DAY FROM (cc.converted_at - cc.campaign_sent_at)) <= 7 THEN 'Direct (< 7 days)'
        WHEN EXTRACT(DAY FROM (cc.converted_at - cc.campaign_sent_at)) <= 30 THEN 'Influenced (7-30 days)'
        ELSE 'Long-term (> 30 days)'
    END AS attribution_window,
    cc.conversion_revenue AS attributed_revenue
FROM campaign_conversions cc
ORDER BY cc.converted_at DESC;

-- ============================================================
-- MATERIALIZED VIEW: Campaign Intelligence
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_campaign_intelligence CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_campaign_intelligence AS
SELECT 
    vp.*,
    cp.campaign_id,
    cp.campaign_name,
    cp.campaign_type,
    cp.delivery_rate_pct,
    cp.read_rate_pct,
    cp.response_rate_pct,
    cp.conversion_rate_pct,
    cp.total_conversion_revenue,
    -- Campaign ROI
    CASE 
        WHEN cp.total_conversion_revenue > 0 
        THEN cp.total_conversion_revenue / NULLIF(cp.sent_count, 0) 
        ELSE 0 
    END AS revenue_per_message
FROM dk.vw_campaign_performance cp
CROSS JOIN (
    SELECT 
        mrn,
        rfm_segment,
        ltv_segment,
        value_tier,
        predicted_annual_ltv
    FROM dk.mvw_patient_intelligence
) vp
WHERE EXISTS (
    SELECT 1 FROM dk.campaign_assignments ca
    WHERE ca.campaign_id = cp.campaign_id AND ca.mrn = vp.mrn
);

CREATE UNIQUE INDEX idx_mvw_campaign_intel ON dk.mvw_campaign_intelligence(campaign_id, mrn);

-- ============================================================
-- FUNCTION: Create D+3 Campaign
-- ============================================================

CREATE OR REPLACE FUNCTION dk.create_d3_campaign(
    p_campaign_name VARCHAR,
    p_max_patients INTEGER DEFAULT 100
)
RETURNS INTEGER AS $$
DECLARE
    v_campaign_id INTEGER;
    v_template_code VARCHAR := 'd3_followup';
BEGIN
    -- Create campaign record
    INSERT INTO dk.campaigns (
        campaign_name,
        campaign_type,
        template_code,
        status,
        target_patient_count
    ) VALUES (
        p_campaign_name,
        'd3_followup',
        v_template_code,
        'draft',
        p_max_patients
    ) RETURNING campaign_id INTO v_campaign_id;
    
    -- Assign patients from D+3 queue
    INSERT INTO dk.campaign_assignments (
        campaign_id,
        mrn,
        patient_name,
        phone,
        rfm_segment,
        ltv_segment,
        priority_score
    )
    SELECT 
        v_campaign_id,
        mrn,
        patient_name,
        phone,
        rfm_segment,
        ltv_segment,
        CASE followup_priority
            WHEN 'High Priority' THEN 3
            WHEN 'Medium Priority' THEN 2
            ELSE 1
        END
    FROM dk.vw_d3_followup_queue
    WHERE is_available_for_campaign = TRUE
    ORDER BY followup_priority, last_visit_amount DESC
    LIMIT p_max_patients;
    
    -- Update campaign with actual count
    UPDATE dk.campaigns 
    SET target_patient_count = (SELECT COUNT(*) FROM dk.campaign_assignments WHERE campaign_id = v_campaign_id)
    WHERE campaign_id = v_campaign_id;
    
    RETURN v_campaign_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE dk.whatsapp_campaign_templates IS 'Templates for WhatsApp campaign messages';
COMMENT ON TABLE dk.campaigns IS 'Campaign definitions and performance tracking';
COMMENT ON TABLE dk.campaign_assignments IS 'Patient assignments to campaigns';
COMMENT ON VIEW dk.vw_campaign_performance IS 'Campaign performance metrics and rates';
COMMENT ON VIEW dk.vw_campaign_patient_details IS 'Detailed patient-level campaign status';
COMMENT ON VIEW dk.vw_d3_followup_queue IS 'Queue of patients eligible for D+3 follow-up';
COMMENT ON VIEW dk.vw_conversion_attribution IS 'Conversion attribution to campaigns';
COMMENT ON MATERIALIZED VIEW dk.mvw_campaign_intelligence IS 'Campaign intelligence with patient segments';
