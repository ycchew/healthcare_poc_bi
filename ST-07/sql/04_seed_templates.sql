-- ============================================================
-- ST-07: Automation & Campaigns
-- 04_seed_templates.sql
-- ============================================================
-- Seeds initial WhatsApp message templates.
-- NOTE: These templates must be submitted to Meta for approval
-- via the WhatsApp Cloud API or Meta Business Manager.
-- Status is set to 'pending_approval' by default.
-- ============================================================

INSERT INTO dk.whatsapp_templates (template_name, category, language, body_text, variables_schema)
VALUES
    ('appointment_reminder', 'utility', 'en',
     'Hi {{1}}, this is a reminder about your appointment on {{2}} at {{3}} at our {{4}} branch. Reply to confirm or reschedule.',
     '{"1": "patient_name", "2": "date", "3": "time", "4": "branch"}'
    ),
    ('no_show_followup', 'utility', 'en',
     'Hi {{1}}, we missed you at your appointment on {{2}}. Would you like to reschedule? Reply or call us.',
     '{"1": "patient_name", "2": "missed_date", "3": "reschedule_cta"}'
    ),
    ('churn_prevention', 'marketing', 'en',
     'Hi {{1}}, we haven''t seen you since {{2}}. We miss you! Here''s a special offer just for you: {{3}}. Book now!',
     '{"1": "patient_name", "2": "last_visit", "3": "special_offer"}'
    ),
    ('upsell_recommendation', 'marketing', 'en',
     'Hi {{1}}, based on your visit history, we think you''d love our {{2}}. Book a session today!',
     '{"1": "patient_name", "2": "recommended_service"}'
    ),
    ('dynamic_pricing_offer', 'marketing', 'en',
     'Hi {{1}}, exclusive offer for you: {{2}} off your next visit! Valid until {{3}}. Don''t miss out.',
     '{"1": "patient_name", "2": "discount_pct", "3": "valid_until"}'
    ),
    ('reactivation', 'marketing', 'en',
     'Hi {{1}}, it''s been {{2}} months since your last visit. We''d love to see you again! {{3}}',
     '{"1": "patient_name", "2": "months_away", "3": "welcome_back_offer"}'
    ),
    ('marketing_broadcast', 'marketing', 'en',
     'Hi {{1}}, {{2}}',
     '{"1": "patient_name", "2": "campaign_body"}'
    )
ON CONFLICT (template_name) DO NOTHING;

-- Verify
SELECT template_name, category, status FROM dk.whatsapp_templates ORDER BY template_name;
