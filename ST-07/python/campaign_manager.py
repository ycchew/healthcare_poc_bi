"""
ST-07: Automation & Campaigns
Campaign Manager - Campaign Orchestration

Intelligence layer connecting ST-03 (Patient Intelligence) and ST-05 (ML Predictions)
outputs to WhatsApp campaign queue.

Usage:
    from campaign_manager import CampaignManager
    mgr = CampaignManager()
    mgr.queue_appointment_reminders()
    mgr.queue_churn_prevention()
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from dotenv import load_dotenv

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import ST-01 database module
import importlib.util

spec = importlib.util.spec_from_file_location(
    "database", os.path.join(project_root, "ST-01", "python", "database.py")
)
database_module = importlib.util.module_from_spec(spec)
sys.modules["database"] = database_module
spec.loader.exec_module(database_module)
DatabaseManager = database_module.DatabaseManager

load_dotenv(override=True)

logger = logging.getLogger(__name__)


class CampaignManager:
    """
    Campaign orchestration layer.

    Each queue_* method:
    1. Queries target patients from relevant views/tables
    2. Filters by consent status (via dk.queue_campaign_message function)
    3. Maps to appropriate template + parameters
    4. Inserts into dk.campaign_queue
    5. Returns count of queued messages
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def queue_appointment_reminders(self) -> int:
        """
        Queue D-1 appointment reminders.
        Queries tomorrow's appointments from dk.collection joined with dk.patient.
        """
        query = """
            SELECT DISTINCT ON (c.mrn)
                c.mrn,
                p.phone_number,
                p.name AS patient_name,
                c.date AS appointment_date,
                c.time AS appointment_time,
                c.branch
            FROM dk.collection c
            INNER JOIN dk.patient p ON c.mrn = p.mrn AND c.location = p.location
            WHERE c.date::DATE = CURRENT_DATE + INTERVAL '1 day'
              AND c.mrn IS NOT NULL
              AND p.phone_number IS NOT NULL
            ORDER BY c.mrn, c.date DESC
        """
        df = self.db.execute_query(query)
        if df.empty:
            logger.info("No appointments found for tomorrow")
            return 0

        queued = 0
        for _, row in df.iterrows():
            phone = str(row["phone_number"]).strip()
            if not phone.startswith("+"):
                phone = f"+60{phone.lstrip('0')}"

            result = self.db.execute_query(
                """SELECT dk.queue_campaign_message(
                    :mrn, :phone, 'appointment_reminder',
                    :params::jsonb, 'scheduled', 'appointment_reminder', 2, :scheduled_at
                ) AS queue_id""",
                params={
                    "mrn": str(row["mrn"]),
                    "phone": phone,
                    "params": {
                        "1": str(row["patient_name"])
                        if row["patient_name"]
                        else "Patient",
                        "2": str(row["appointment_date"])[:10],
                        "3": str(row["appointment_time"])
                        if row["appointment_time"]
                        else "scheduled time",
                        "4": str(row["branch"]) if row["branch"] else "branch",
                    },
                    "scheduled_at": datetime.now() + timedelta(hours=8),
                },
            )
            if (
                result is not None
                and not result.empty
                and result.iloc[0]["queue_id"] is not None
            ):
                queued += 1

        logger.info(f"Queued {queued} appointment reminders for tomorrow")
        return queued

    def queue_no_show_followup(self, mrn: Optional[str] = None) -> int:
        """
        Queue no-show follow-up messages.
        If mrn provided, single patient; else batch for today's no-shows.
        """
        mrn_filter = f"AND c.mrn = '{mrn}'" if mrn else ""

        query = f"""
            SELECT DISTINCT ON (c.mrn)
                c.mrn,
                p.phone_number,
                p.name AS patient_name,
                c.date AS missed_date,
                c.branch
            FROM dk.collection c
            INNER JOIN dk.patient p ON c.mrn = p.mrn AND c.location = p.location
            WHERE c.date::DATE = CURRENT_DATE
              AND c.mrn IS NOT NULL
              AND p.phone_number IS NOT NULL
              {mrn_filter}
            ORDER BY c.mrn, c.date DESC
        """
        df = self.db.execute_query(query)
        if df.empty:
            logger.info("No no-show patients found")
            return 0

        queued = 0
        for _, row in df.iterrows():
            phone = str(row["phone_number"]).strip()
            if not phone.startswith("+"):
                phone = f"+60{phone.lstrip('0')}"

            result = self.db.execute_query(
                """SELECT dk.queue_campaign_message(
                    :mrn, :phone, 'no_show_followup',
                    :params::jsonb, 'scheduled', 'no_show_followup', 1, NULL
                ) AS queue_id""",
                params={
                    "mrn": str(row["mrn"]),
                    "phone": phone,
                    "params": {
                        "1": str(row["patient_name"])
                        if row["patient_name"]
                        else "Patient",
                        "2": str(row["missed_date"])[:10],
                        "3": "Call us to reschedule",
                    },
                },
            )
            if (
                result is not None
                and not result.empty
                and result.iloc[0]["queue_id"] is not None
            ):
                queued += 1

        logger.info(f"Queued {queued} no-show follow-ups")
        return queued

    def queue_churn_prevention(self) -> int:
        """
        Queue churn prevention messages for high-risk patients.
        Targets from dk.ml_predictions WHERE churn_risk = 'high'.
        """
        query = """
            SELECT 
                mp.mrn,
                p.phone_number,
                p.name AS patient_name,
                mp.predicted_churn_probability,
                mp.churn_risk
            FROM dk.ml_predictions mp
            INNER JOIN dk.patient p ON mp.mrn = p.mrn
            WHERE mp.churn_risk = 'high'
              AND p.phone_number IS NOT NULL
        """
        df = self.db.execute_query(query)
        if df.empty:
            logger.info("No high churn risk patients found")
            return 0

        queued = 0
        for _, row in df.iterrows():
            phone = str(row["phone_number"]).strip()
            if not phone.startswith("+"):
                phone = f"+60{phone.lstrip('0')}"

            result = self.db.execute_query(
                """SELECT dk.queue_campaign_message(
                    :mrn, :phone, 'churn_prevention',
                    :params::jsonb, 'scheduled', 'churn_prevention', 2, NULL
                ) AS queue_id""",
                params={
                    "mrn": str(row["mrn"]),
                    "phone": phone,
                    "params": {
                        "1": str(row["patient_name"])
                        if row["patient_name"]
                        else "Patient",
                        "2": "a while",
                        "3": "10% off your next visit",
                    },
                },
            )
            if (
                result is not None
                and not result.empty
                and result.iloc[0]["queue_id"] is not None
            ):
                queued += 1

        logger.info(f"Queued {queued} churn prevention messages")
        return queued

    def queue_upsell_campaign(self) -> int:
        """
        Queue upsell recommendations.
        Targets from dk.ml_predictions WHERE upsell_probability is high.
        """
        query = """
            SELECT 
                mp.mrn,
                p.phone_number,
                p.name AS patient_name,
                mp.predicted_upsell_probability
            FROM dk.ml_predictions mp
            INNER JOIN dk.patient p ON mp.mrn = p.mrn
            WHERE mp.predicted_upsell_probability > 0.7
              AND p.phone_number IS NOT NULL
        """
        df = self.db.execute_query(query)
        if df.empty:
            logger.info("No upsell targets found")
            return 0

        queued = 0
        for _, row in df.iterrows():
            phone = str(row["phone_number"]).strip()
            if not phone.startswith("+"):
                phone = f"+60{phone.lstrip('0')}"

            result = self.db.execute_query(
                """SELECT dk.queue_campaign_message(
                    :mrn, :phone, 'upsell_recommendation',
                    :params::jsonb, 'scheduled', 'upsell_recommendation', 3, NULL
                ) AS queue_id""",
                params={
                    "mrn": str(row["mrn"]),
                    "phone": phone,
                    "params": {
                        "1": str(row["patient_name"])
                        if row["patient_name"]
                        else "Patient",
                        "2": "our premium skincare package",
                    },
                },
            )
            if (
                result is not None
                and not result.empty
                and result.iloc[0]["queue_id"] is not None
            ):
                queued += 1

        logger.info(f"Queued {queued} upsell recommendations")
        return queued

    def queue_dynamic_pricing(self) -> int:
        """
        Queue dynamic pricing offers.
        Targets from dk.dynamic_pricing_offers.
        """
        query = """
            SELECT 
                dpo.mrn,
                p.phone_number,
                p.name AS patient_name,
                dpo.discount_pct,
                dpo.valid_until,
                dpo.priority
            FROM dk.dynamic_pricing_offers dpo
            INNER JOIN dk.patient p ON dpo.mrn = p.mrn
            WHERE dpo.valid_until >= CURRENT_DATE
              AND p.phone_number IS NOT NULL
        """
        df = self.db.execute_query(query)
        if df.empty:
            logger.info("No dynamic pricing offers to send")
            return 0

        queued = 0
        for _, row in df.iterrows():
            phone = str(row["phone_number"]).strip()
            if not phone.startswith("+"):
                phone = f"+60{phone.lstrip('0')}"

            result = self.db.execute_query(
                """SELECT dk.queue_campaign_message(
                    :mrn, :phone, 'dynamic_pricing_offer',
                    :params::jsonb, 'scheduled', 'dynamic_pricing_offer', 3, NULL
                ) AS queue_id""",
                params={
                    "mrn": str(row["mrn"]),
                    "phone": phone,
                    "params": {
                        "1": str(row["patient_name"])
                        if row["patient_name"]
                        else "Patient",
                        "2": f"{row['discount_pct']}% off",
                        "3": str(row["valid_until"])[:10]
                        if row["valid_until"]
                        else "this month",
                    },
                },
            )
            if (
                result is not None
                and not result.empty
                and result.iloc[0]["queue_id"] is not None
            ):
                queued += 1

        logger.info(f"Queued {queued} dynamic pricing offers")
        return queued

    def queue_reactivation(self) -> int:
        """
        Queue patient reactivation messages.
        Targets dormant patients (no visits in 90+ days) from dk.patient.
        """
        query = """
            SELECT 
                p.mrn,
                p.phone_number,
                p.name AS patient_name,
                MAX(c.date) AS last_visit
            FROM dk.patient p
            LEFT JOIN dk.collection c ON p.mrn = c.mrn AND p.location = c.location
            WHERE p.phone_number IS NOT NULL
            GROUP BY p.mrn, p.phone_number, p.name
            HAVING MAX(c.date) < CURRENT_DATE - INTERVAL '90 days'
               OR MAX(c.date) IS NULL
            LIMIT 100
        """
        df = self.db.execute_query(query)
        if df.empty:
            logger.info("No dormant patients found for reactivation")
            return 0

        queued = 0
        for _, row in df.iterrows():
            phone = str(row["phone_number"]).strip()
            if not phone.startswith("+"):
                phone = f"+60{phone.lstrip('0')}"

            months_away = 3
            if row["last_visit"]:
                months_away = max(
                    1, int((datetime.now() - row["last_visit"]).days / 30)
                )

            result = self.db.execute_query(
                """SELECT dk.queue_campaign_message(
                    :mrn, :phone, 'reactivation',
                    :params::jsonb, 'scheduled', 'reactivation', 4, NULL
                ) AS queue_id""",
                params={
                    "mrn": str(row["mrn"]),
                    "phone": phone,
                    "params": {
                        "1": str(row["patient_name"])
                        if row["patient_name"]
                        else "Patient",
                        "2": str(months_away),
                        "3": "Come back and get 15% off your next visit!",
                    },
                },
            )
            if (
                result is not None
                and not result.empty
                and result.iloc[0]["queue_id"] is not None
            ):
                queued += 1

        logger.info(f"Queued {queued} reactivation messages")
        return queued

    def queue_marketing_broadcast(
        self,
        segment_filters: Dict[str, Any],
        template_name: str = "marketing_broadcast",
    ) -> int:
        """
        Queue manual marketing broadcast to RFM/CLTV segments.

        Args:
            segment_filters: Dict with filter keys like 'rfm_segment', 'cltv_tier', 'branch'
                Example: {"rfm_segment": "PREMIUM", "cltv_tier": "HIGH"}
            template_name: Template to use (default 'marketing_broadcast')

        Returns:
            Count of queued messages
        """
        base_query = """
            SELECT DISTINCT
                p.mrn,
                p.phone_number,
                p.name AS patient_name,
                r.rfm_segment,
                r.cltv_tier
            FROM dk.patient p
            INNER JOIN dk.mvw_patient_rfm r ON p.mrn = r.mrn
            WHERE p.phone_number IS NOT NULL
        """
        conditions = []
        params = {}

        if "rfm_segment" in segment_filters:
            conditions.append("r.rfm_segment = :rfm_segment")
            params["rfm_segment"] = segment_filters["rfm_segment"]

        if "cltv_tier" in segment_filters:
            conditions.append("r.cltv_tier = :cltv_tier")
            params["cltv_tier"] = segment_filters["cltv_tier"]

        if conditions:
            base_query += " AND " + " AND ".join(conditions)

        df = self.db.execute_query(base_query, params=params)
        if df.empty:
            logger.info(f"No patients match segment filters: {segment_filters}")
            return 0

        campaign_body = segment_filters.get("message", "Check out our latest offers!")

        queued = 0
        for _, row in df.iterrows():
            phone = str(row["phone_number"]).strip()
            if not phone.startswith("+"):
                phone = f"+60{phone.lstrip('0')}"

            result = self.db.execute_query(
                """SELECT dk.queue_campaign_message(
                    :mrn, :phone, :template_name,
                    :params::jsonb, 'manual', 'marketing_broadcast', 3, NULL
                ) AS queue_id""",
                params={
                    "mrn": str(row["mrn"]),
                    "phone": phone,
                    "template_name": template_name,
                    "params": {
                        "1": str(row["patient_name"])
                        if row["patient_name"]
                        else "Patient",
                        "2": campaign_body,
                    },
                },
            )
            if (
                result is not None
                and not result.empty
                and result.iloc[0]["queue_id"] is not None
            ):
                queued += 1

        logger.info(f"Queued {queued} marketing broadcast messages")
        return queued

    def process_opt_out(self, mrn: str, phone: str) -> None:
        """
        Process patient opt-out: update consent and cancel pending messages.

        Args:
            mrn: Patient MRN
            phone: Patient phone number
        """
        # Update consent
        self.db.execute_query(
            """UPDATE dk.patient_consent 
               SET opt_out_timestamp = NOW(), consent_given = FALSE
               WHERE mrn = :mrn AND phone_number = :phone""",
            params={"mrn": mrn, "phone": phone},
            return_df=False,
        )

        # Cancel pending messages
        self.db.execute_query(
            "SELECT dk.cancel_pending_for_opted_out(:mrn)",
            params={"mrn": mrn},
            return_df=False,
        )

        logger.info(f"Processed opt-out for MRN {mrn}, phone {phone}")
