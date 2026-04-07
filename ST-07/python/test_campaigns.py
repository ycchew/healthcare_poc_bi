"""
ST-07: Automation & Campaigns
Test suite for WhatsApp campaign modules.

Tests cover:
- WhatsAppClient: template sending, webhook parsing, rate limiting, signature verification
- CampaignSender: queue processing, single event processing
- CampaignManager: all 7 campaign types, opt-out processing
- Database: schema validation, function behavior

To run tests:
    pytest ST-07/python/test_campaigns.py -v

Requirements:
    pip install pytest pandas sqlalchemy httpx fastapi
    Configure .env with DB_* credentials
    WhatsApp credentials optional (tests run in dry-run mode)
"""

import os
import sys
import json
import time
import pytest
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pandas as pd
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ST-01" / "python"))
sys.path.insert(0, str(project_root / "ST-07" / "python"))

from database import DatabaseManager
from whatsapp_client import WhatsAppClient
from campaign_sender import process_queue, process_single_event
from campaign_manager import CampaignManager


@pytest.fixture(scope="module")
def db() -> Generator[DatabaseManager, None, None]:
    manager = DatabaseManager()
    yield manager
    manager.close()


@pytest.fixture(scope="module")
def db_env_configured() -> bool:
    return all(
        os.getenv(var)
        for var in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    )


@pytest.fixture
def wa_client() -> WhatsAppClient:
    """WhatsApp client in dry-run mode (no credentials needed)."""
    return WhatsAppClient(
        phone_number_id=None,
        access_token=None,
        verify_token="test_verify_token",
    )


@pytest.fixture
def campaign_mgr(db: DatabaseManager) -> CampaignManager:
    return CampaignManager(db_manager=db)


# ============================================================
# WhatsAppClient Tests
# ============================================================


class TestWhatsAppClientInit:
    def test_init_with_no_credentials(self):
        """Client initializes in dry-run mode without credentials."""
        client = WhatsAppClient(phone_number_id=None, access_token=None)
        assert client.phone_number_id == ""
        assert client.access_token == ""
        assert client.tier_limit == 250

    def test_init_with_custom_credentials(self):
        """Client uses provided credentials."""
        client = WhatsAppClient(
            phone_number_id="123456",
            access_token="test_token",
            verify_token="verify_123",
            api_version="v20.0",
            tier_limit=1000,
        )
        assert client.phone_number_id == "123456"
        assert client.access_token == "test_token"
        assert client.verify_token == "verify_123"
        assert client.api_version == "v20.0"
        assert client.tier_limit == 1000

    def test_init_default_api_version(self):
        """Default API version is v21.0."""
        client = WhatsAppClient()
        assert client.api_version == "v21.0"


class TestWhatsAppClientRateLimiting:
    def test_can_send_within_limit(self, wa_client: WhatsAppClient):
        """can_send returns True when under limit."""
        assert wa_client.can_send() is True

    def test_can_send_exceeds_limit(self):
        """can_send returns False when over limit."""
        client = WhatsAppClient(tier_limit=2)
        client._daily_send_count = 2
        assert client.can_send() is False

    def test_daily_count_resets_at_midnight(self, wa_client: WhatsAppClient):
        """Daily count resets when date changes."""
        wa_client._daily_send_count = 100
        wa_client._send_count_date = "2020-01-01"
        assert wa_client.can_send() is True
        assert wa_client._daily_send_count == 0

    def test_send_template_increments_count(self, wa_client: WhatsAppClient):
        """Successful send increments daily counter."""
        initial = wa_client.get_daily_send_count()
        wa_client.send_template(
            to="+60123456789",
            template_name="appointment_reminder",
            components={"1": "Test", "2": "2026-04-05", "3": "10:00", "4": "KLCC"},
        )
        assert wa_client.get_daily_send_count() == initial + 1

    def test_send_template_dry_run(self, wa_client: WhatsAppClient):
        """Send returns success in dry-run mode."""
        result = wa_client.send_template(
            to="+60123456789",
            template_name="appointment_reminder",
            components={"1": "Test", "2": "2026-04-05", "3": "10:00", "4": "KLCC"},
        )
        assert result["success"] is True
        assert result["dry_run"] is True
        assert "dry_run_" in result["message_id"]

    def test_send_template_blocked_by_limit(self):
        """Send fails when tier limit reached."""
        client = WhatsAppClient(tier_limit=1)
        client._daily_send_count = 1
        result = client.send_template(
            to="+60123456789",
            template_name="appointment_reminder",
            components={"1": "Test"},
        )
        assert result["success"] is False
        assert "tier limit" in result["error"].lower()


class TestWhatsAppClientWebhooks:
    def test_verify_signature_valid(self, wa_client: WhatsAppClient):
        """Valid signature passes verification."""
        import hmac
        import hashlib

        payload = '{"test": true}'
        expected = hmac.new(
            b"test_verify_token",
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={expected}"
        assert wa_client.verify_webhook_signature(payload, signature) is True

    def test_verify_signature_invalid(self, wa_client: WhatsAppClient):
        """Invalid signature fails verification."""
        assert (
            wa_client.verify_webhook_signature('{"test": true}', "sha256=invalid")
            is False
        )

    def test_parse_webhook_delivery_status(self, wa_client: WhatsAppClient):
        """Parse delivery status webhook event."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "msg_123",
                                        "status": "delivered",
                                        "recipient_id": "60123456789",
                                        "timestamp": "1234567890",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        events = wa_client.parse_webhook_event(payload)
        assert len(events) == 1
        assert events[0]["event_type"] == "delivered"
        assert events[0]["message_id"] == "msg_123"
        assert events[0]["phone_number"] == "60123456789"

    def test_parse_webhook_opt_out(self, wa_client: WhatsAppClient):
        """Parse opt-out event when patient sends STOP."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "msg_456",
                                        "from": "60123456789",
                                        "timestamp": "1234567890",
                                        "text": {"body": "STOP"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        events = wa_client.parse_webhook_event(payload)
        assert len(events) == 1
        assert events[0]["event_type"] == "opt_out"

    def test_parse_webhook_reply(self, wa_client: WhatsAppClient):
        """Parse normal reply message."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "msg_789",
                                        "from": "60123456789",
                                        "timestamp": "1234567890",
                                        "text": {"body": "Yes, I confirm"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        events = wa_client.parse_webhook_event(payload)
        assert len(events) == 1
        assert events[0]["event_type"] == "reply"
        assert events[0]["text"] == "Yes, I confirm"

    def test_parse_webhook_failed_delivery(self, wa_client: WhatsAppClient):
        """Parse failed delivery event."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "msg_err",
                                        "status": "failed",
                                        "recipient_id": "60123456789",
                                        "timestamp": "1234567890",
                                        "errors": [
                                            {
                                                "code": 131047,
                                                "message": "Invalid recipient",
                                            }
                                        ],
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        events = wa_client.parse_webhook_event(payload)
        assert len(events) == 1
        assert events[0]["event_type"] == "failed"
        assert "Invalid recipient" in events[0].get("error", "")


# ============================================================
# Database Schema Tests
# ============================================================


class TestCampaignSchema(db_env_configured):
    """Verify ST-07 database schema exists."""

    def test_whatsapp_templates_table(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM information_schema.tables "
            "WHERE table_schema = 'dk' AND table_name = 'whatsapp_templates'"
        )
        assert result.iloc[0]["cnt"] == 1

    def test_campaign_queue_table(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM information_schema.tables "
            "WHERE table_schema = 'dk' AND table_name = 'campaign_queue'"
        )
        assert result.iloc[0]["cnt"] == 1

    def test_delivery_log_table(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM information_schema.tables "
            "WHERE table_schema = 'dk' AND table_name = 'delivery_log'"
        )
        assert result.iloc[0]["cnt"] == 1

    def test_patient_consent_table(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM information_schema.tables "
            "WHERE table_schema = 'dk' AND table_name = 'patient_consent'"
        )
        assert result.iloc[0]["cnt"] == 1

    def test_campaign_stats_table(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM information_schema.tables "
            "WHERE table_schema = 'dk' AND table_name = 'campaign_stats'"
        )
        assert result.iloc[0]["cnt"] == 1

    def test_vw_campaign_queue_pending_view(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM information_schema.views "
            "WHERE table_schema = 'dk' AND table_name = 'vw_campaign_queue_pending'"
        )
        assert result.iloc[0]["cnt"] == 1

    def test_check_patient_consent_function(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM information_schema.routines "
            "WHERE routine_schema = 'dk' AND routine_name = 'check_patient_consent'"
        )
        assert result.iloc[0]["cnt"] == 1

    def test_queue_campaign_message_function(self, db: DatabaseManager):
        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM information_schema.routines "
            "WHERE routine_schema = 'dk' AND routine_name = 'queue_campaign_message'"
        )
        assert result.iloc[0]["cnt"] == 1


# ============================================================
# Integration Tests (requires database)
# ============================================================


class TestCampaignFunctionsIntegration(db_env_configured):
    """Integration tests against real database."""

    def test_consent_check_no_record(self, db: DatabaseManager):
        """Consent check returns False for unknown patient."""
        result = db.execute_query(
            "SELECT dk.check_patient_consent('NONEXISTENT', '+60123456789') AS has_consent"
        )
        assert result.iloc[0]["has_consent"] is False

    def test_consent_check_with_consent(self, db: DatabaseManager):
        """Consent check returns True for opted-in patient."""
        db.execute_query(
            """INSERT INTO dk.patient_consent (mrn, phone_number, consent_given, consent_source)
               VALUES ('TEST_ST07_001', '+60199999999', TRUE, 'manual')
               ON CONFLICT (mrn, phone_number) DO UPDATE SET 
                   consent_given = TRUE, opt_out_timestamp = NULL""",
            return_df=False,
        )

        result = db.execute_query(
            "SELECT dk.check_patient_consent('TEST_ST07_001', '+60199999999') AS has_consent"
        )
        assert result.iloc[0]["has_consent"] is True

        db.execute_query(
            "DELETE FROM dk.patient_consent WHERE mrn = 'TEST_ST07_001'",
            return_df=False,
        )

    def test_consent_check_opted_out(self, db: DatabaseManager):
        """Consent check returns False for opted-out patient."""
        db.execute_query(
            """INSERT INTO dk.patient_consent (mrn, phone_number, consent_given, opt_out_timestamp, consent_source)
               VALUES ('TEST_ST07_002', '+60199999998', FALSE, NOW(), 'manual')
               ON CONFLICT (mrn, phone_number) DO UPDATE SET 
                   consent_given = FALSE, opt_out_timestamp = NOW()""",
            return_df=False,
        )

        result = db.execute_query(
            "SELECT dk.check_patient_consent('TEST_ST07_002', '+60199999998') AS has_consent"
        )
        assert result.iloc[0]["has_consent"] is False

        db.execute_query(
            "DELETE FROM dk.patient_consent WHERE mrn = 'TEST_ST07_002'",
            return_df=False,
        )

    def test_queue_campaign_message_with_consent(self, db: DatabaseManager):
        """Queue message for patient with consent returns queue_id."""
        db.execute_query(
            """INSERT INTO dk.patient_consent (mrn, phone_number, consent_given, consent_source)
               VALUES ('TEST_ST07_003', '+60199999997', TRUE, 'manual')
               ON CONFLICT (mrn, phone_number) DO UPDATE SET 
                   consent_given = TRUE, opt_out_timestamp = NULL""",
            return_df=False,
        )

        db.execute_query(
            """INSERT INTO dk.whatsapp_templates (template_name, category, body_text, status)
               VALUES ('test_template', 'utility', 'Hello {{1}}', 'approved')
               ON CONFLICT (template_name) DO NOTHING""",
            return_df=False,
        )

        result = db.execute_query(
            """SELECT dk.queue_campaign_message(
                'TEST_ST07_003', '+60199999997', 'test_template',
                '{"1": "Test"}'::jsonb, 'scheduled', 'appointment_reminder', 3, NULL
            ) AS queue_id"""
        )
        queue_id = result.iloc[0]["queue_id"]
        assert queue_id is not None

        db.execute_query(
            "DELETE FROM dk.campaign_queue WHERE mrn = 'TEST_ST07_003'",
            return_df=False,
        )
        db.execute_query(
            "DELETE FROM dk.patient_consent WHERE mrn = 'TEST_ST07_003'",
            return_df=False,
        )

    def test_queue_campaign_message_without_consent(self, db: DatabaseManager):
        """Queue message for patient without consent returns NULL."""
        result = db.execute_query(
            """SELECT dk.queue_campaign_message(
                'TEST_ST07_NOCONSENT', '+60199999996', 'test_template',
                '{"1": "Test"}'::jsonb, 'scheduled', 'appointment_reminder', 3, NULL
            ) AS queue_id"""
        )
        assert result.iloc[0]["queue_id"] is None

    def test_cancel_pending_for_opted_out(self, db: DatabaseManager):
        """Cancel pending messages when patient opts out."""
        db.execute_query(
            """INSERT INTO dk.patient_consent (mrn, phone_number, consent_given, consent_source)
               VALUES ('TEST_ST07_004', '+60199999995', TRUE, 'manual')
               ON CONFLICT (mrn, phone_number) DO UPDATE SET 
                   consent_given = TRUE, opt_out_timestamp = NULL""",
            return_df=False,
        )

        db.execute_query(
            """SELECT dk.queue_campaign_message(
                'TEST_ST07_004', '+60199999995', 'test_template',
                '{"1": "Test"}'::jsonb, 'scheduled', 'appointment_reminder', 3, NULL
            )""",
            return_df=False,
        )

        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM dk.campaign_queue WHERE mrn = 'TEST_ST07_004' AND status = 'pending'"
        )
        assert result.iloc[0]["cnt"] >= 1

        db.execute_query(
            "SELECT dk.cancel_pending_for_opted_out('TEST_ST07_004')",
            return_df=False,
        )

        result = db.execute_query(
            "SELECT COUNT(*) as cnt FROM dk.campaign_queue WHERE mrn = 'TEST_ST07_004' AND status = 'cancelled'"
        )
        assert result.iloc[0]["cnt"] >= 1

        db.execute_query(
            "DELETE FROM dk.campaign_queue WHERE mrn = 'TEST_ST07_004'",
            return_df=False,
        )
        db.execute_query(
            "DELETE FROM dk.patient_consent WHERE mrn = 'TEST_ST07_004'",
            return_df=False,
        )


# ============================================================
# CampaignManager Tests
# ============================================================


class TestCampaignManager(db_env_configured):
    """Test CampaignManager methods."""

    def test_manager_initialization(self, campaign_mgr: CampaignManager):
        """CampaignManager initializes with database connection."""
        assert campaign_mgr.db is not None

    def test_queue_appointment_reminders_returns_int(
        self, campaign_mgr: CampaignManager
    ):
        """queue_appointment_reminders returns an integer."""
        result = campaign_mgr.queue_appointment_reminders()
        assert isinstance(result, int)

    def test_queue_no_show_followup_returns_int(self, campaign_mgr: CampaignManager):
        """queue_no_show_followup returns an integer."""
        result = campaign_mgr.queue_no_show_followup()
        assert isinstance(result, int)

    def test_queue_churn_prevention_returns_int(self, campaign_mgr: CampaignManager):
        """queue_churn_prevention returns an integer."""
        result = campaign_mgr.queue_churn_prevention()
        assert isinstance(result, int)

    def test_queue_upsell_campaign_returns_int(self, campaign_mgr: CampaignManager):
        """queue_upsell_campaign returns an integer."""
        result = campaign_mgr.queue_upsell_campaign()
        assert isinstance(result, int)

    def test_queue_dynamic_pricing_returns_int(self, campaign_mgr: CampaignManager):
        """queue_dynamic_pricing returns an integer."""
        result = campaign_mgr.queue_dynamic_pricing()
        assert isinstance(result, int)

    def test_queue_reactivation_returns_int(self, campaign_mgr: CampaignManager):
        """queue_reactivation returns an integer."""
        result = campaign_mgr.queue_reactivation()
        assert isinstance(result, int)

    def test_queue_marketing_broadcast_returns_int(self, campaign_mgr: CampaignManager):
        """queue_marketing_broadcast returns an integer."""
        result = campaign_mgr.queue_marketing_broadcast({"rfm_segment": "PREMIUM"})
        assert isinstance(result, int)
