# ST-07: Automation & Campaigns

## Overview

ST-07 implements WhatsApp-based patient communication and campaign automation. It leverages outputs from ST-03 (Patient Intelligence) and ST-05 (ML Predictions) to deliver targeted, automated patient communications.

**Channel:** WhatsApp only (via Meta Cloud API)
**Architecture:** Hybrid — pgAgent batch + FastAPI event-driven
**Compliance:** PDPA 2010 (Malaysia)

## Files

### SQL
- `sql/01_campaign_tables.sql` — 5 tables: whatsapp_templates, campaign_queue, delivery_log, patient_consent, campaign_stats
- `sql/02_campaign_views.sql` — 3 views + 5 functions
- `sql/03_scheduling.sql` — pgAgent job definitions + wrapper functions
- `sql/04_seed_templates.sql` — 7 initial WhatsApp message templates

### Python
- `python/whatsapp_client.py` — Meta Cloud API client
- `python/campaign_sender.py` — Queue processor (shared by pgAgent + FastAPI)
- `python/campaign_manager.py` — Campaign orchestration (7 campaign types)
- `python/webhook_handler.py` — FastAPI webhook endpoint
- `python/test_campaigns.py` — Test suite

## Setup

### 1. Execute SQL Scripts

```bash
psql -U <user> -d <db> -f ST-07/sql/01_campaign_tables.sql
psql -U <user> -d <db> -f ST-07/sql/02_campaign_views.sql
psql -U <user> -d <db> -f ST-07/sql/03_scheduling.sql
psql -U <user> -d <db> -f ST-07/sql/04_seed_templates.sql
```

### 2. Configure Environment Variables

Add to `.env`:

```env
# WhatsApp Cloud API (get from developers.facebook.com)
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_VERIFY_TOKEN=your_webhook_verify_token
WHATSAPP_TIER_LIMIT=250
WHATSAPP_API_VERSION=v21.0
```

### 3. Configure PostgreSQL Settings (for pgAgent)

```sql
SELECT set_config('st07.python_path', 'C:\Python310\python.exe', false);
SELECT set_config('st07.project_root', 'D:\dev\healthcare_poc_bi', false);
SELECT set_config('st07.campaign_sender_path', 'ST-07\python\campaign_sender.py', false);
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

New dependencies added: `fastapi>=0.104.0`, `uvicorn>=0.24.0`

### 5. Run Tests

```bash
pytest ST-07/python/test_campaigns.py -v
```

## WhatsApp Business API Setup

### Getting Credentials

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Create a Meta Business Account (or use existing)
3. Add WhatsApp product to your app
4. Verify your business
5. Register a phone number (must NOT be linked to existing WhatsApp)
6. Create message templates in Meta Business Manager
7. Update templates in `dk.whatsapp_templates` with `status = 'approved'`

### Template Approval

Templates seeded via `04_seed_templates.sql` start as `pending_approval`. After Meta approves them:

```sql
UPDATE dk.whatsapp_templates SET status = 'approved' WHERE template_name = 'appointment_reminder';
```

## Usage

### Running Campaigns Manually

```python
from campaign_manager import CampaignManager

mgr = CampaignManager()

# Queue appointment reminders for tomorrow
mgr.queue_appointment_reminders()

# Queue churn prevention for high-risk patients
mgr.queue_churn_prevention()

# Queue upsell recommendations
mgr.queue_upsell_campaign()

# Queue dynamic pricing offers
mgr.queue_dynamic_pricing()

# Queue patient reactivation
mgr.queue_reactivation()

# Queue marketing broadcast to specific segment
mgr.queue_marketing_broadcast(
    segment_filters={"rfm_segment": "PREMIUM", "message": "Exclusive offer for our premium patients!"}
)
```

### Processing the Queue

```bash
# Process up to 50 pending items
python ST-07/python/campaign_sender.py

# Process with custom batch size
python ST-07/python/campaign_sender.py --batch-size 100

# Test mode (check queue status without sending)
python ST-07/python/campaign_sender.py --test
```

### Running the Webhook Server

```bash
uvicorn ST-07.python.webhook_handler:app --host 0.0.0.0 --port 8007
```

Endpoints:
- `GET /health` — Health check
- `GET /webhook/whatsapp` — Meta verification
- `POST /webhook/whatsapp` — WhatsApp events
- `POST /api/v1/events/no-show` — Trigger no-show follow-up

### pgAgent Jobs

Create 8 jobs via pgAdmin UI:

| Job | Schedule | Step |
|-----|----------|------|
| st07_queue_appointment_reminders | Daily 08:00 | `SELECT dk.run_st07_appointment_reminders()` |
| st07_queue_no_show_followup | Daily 12:00 | Queue no-show follow-ups |
| st07_queue_churn_prevention | Weekly Mon 09:00 | Queue churn prevention |
| st07_queue_upsell_campaign | Weekly Wed 09:00 | Queue upsell campaigns |
| st07_queue_dynamic_pricing | Weekly Fri 09:00 | Queue pricing offers |
| st07_queue_reactivation | Monthly 1st Mon 09:00 | Queue reactivation |
| st07_process_queue | Every 5 min | `SELECT dk.run_st07_process_queue()` |
| st07_refresh_stats | Daily 06:00 | `SELECT dk.run_st07_refresh_stats()` |

## Campaign Types

| Type | Trigger | Template | Priority |
|------|---------|----------|----------|
| appointment_reminder | Daily batch (D-1) | appointment_reminder | 2 (high) |
| no_show_followup | Daily batch or event | no_show_followup | 1 (critical) |
| churn_prevention | Weekly batch | churn_prevention | 2 (high) |
| upsell_recommendation | Weekly batch | upsell_recommendation | 3 (normal) |
| dynamic_pricing_offer | Weekly batch | dynamic_pricing_offer | 3 (normal) |
| reactivation | Monthly batch | reactivation | 4 (low) |
| marketing_broadcast | Manual | marketing_broadcast | 3 (normal) |

## Integration with ST-01 to ST-06

| Source | Used By |
|--------|---------|
| `dk.patient` | Phone numbers, MRN for all campaigns |
| `dk.collection` | Appointment dates for reminders |
| `dk.ml_predictions` (ST-05) | Churn risk, upsell probability |
| `dk.dynamic_pricing_offers` (ST-05) | Personalized discount offers |
| `dk.mvw_patient_rfm` (ST-03) | RFM segments for marketing |
| `ST-01/python/database.py` | Database connections |

## Compliance (PDPA 2010)

- Explicit opt-in required before any message
- Opt-out via "STOP" keyword (auto-processed)
- No PHI in messages
- All sends logged in `dk.delivery_log`
- Consent tracked in `dk.patient_consent`

## Database Schema Summary

### Tables (5)
| Table | Purpose |
|-------|---------|
| `dk.whatsapp_templates` | Meta-approved message templates with status tracking |
| `dk.campaign_queue` | Outbound message queue (single source of truth for all sends) |
| `dk.delivery_log` | Full message lifecycle tracking (sent → delivered → read → failed) |
| `dk.patient_consent` | PDPA-compliant opt-in/opt-out tracking |
| `dk.campaign_stats` | Aggregated daily campaign performance for Power BI |

### Views (3)
| View | Purpose |
|------|---------|
| `dk.vw_campaign_queue_pending` | Pending items ready to send (consent-verified, priority-ordered) |
| `dk.vw_campaign_performance` | Daily delivery/read rates by campaign type |
| `dk.vw_patient_communication_status` | Patient-level: consent status, last message, delivery status |

### Functions (5)
| Function | Purpose |
|----------|---------|
| `dk.check_patient_consent(mrn, phone)` | Returns boolean — gate before queueing |
| `dk.queue_campaign_message(...)` | Validates consent, inserts into campaign_queue, returns queue_id |
| `dk.update_delivery_status(...)` | Called by webhook handler to update delivery_log |
| `dk.refresh_campaign_stats()` | Aggregates delivery_log into campaign_stats |
| `dk.cancel_pending_for_opted_out(mrn)` | Cancels all pending messages for opted-out patient |

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────┐     ┌───────────────────┐
│  pgAgent    │     │  dk.campaign_queue (shared queue)    │     │  WhatsApp Cloud   │
│  (batch)    │────→│  dk.delivery_log                     │────→│  API (Meta)       │
│             │     │  dk.campaign_stats                   │     └────────┬──────────┘
└─────────────┘     │  dk.whatsapp_templates               │              │
                    │  dk.patient_consent                  │              │
┌─────────────┐     └──────────────────────────────────────┘              │
│  FastAPI    │───────────────────────────────────────────────────────────┘
│  (events +  │←─────────────────────────────────────────────────────────┘
│  webhooks)  │     WhatsApp webhooks (delivery receipts, opt-outs)
└─────────────┘
```

## Key Design Decisions

1. **Direct Meta Cloud API** — No BSP (Business Solution Provider) dependency. Lowest cost, full control.
2. **Consent gate at DB level** — `dk.queue_campaign_message()` checks consent before every insert. Double-gated by `vw_campaign_queue_pending` view.
3. **Shared queue processor** — Both pgAgent (batch) and FastAPI (events) use the same `campaign_sender.py` module.
4. **Dry-run mode** — WhatsApp client operates without credentials for testing. No messages sent until `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_ACCESS_TOKEN` are configured.
5. **Rate limiting** — Daily tier limit enforced at client level (default 250 for Tier 0). Auto-resets at midnight.
6. **Retry logic** — Failed sends retry up to 3 times with exponential backoff. After 3 failures, marked as 'failed'.
7. **Opt-out auto-processing** — "STOP" keyword in webhook triggers automatic consent revocation + pending message cancellation.

## Lessons Learned

- WhatsApp message templates must be approved by Meta before use. Utility templates (appointment reminders) approved faster than marketing templates.
- Phone numbers must be in E.164 format (+60...). The campaign manager auto-converts local Malaysian format.
- Webhook signature verification requires `WHATSAPP_VERIFY_TOKEN` to match the one configured in Meta Business Manager.
- Meta requires webhook endpoints to return 200 OK within 3 seconds. Processing is done synchronously but must be fast.
- No PHI (Protected Health Information) should ever be sent via WhatsApp, per PDPA 2010 compliance.
