"""
ST-07: Automation & Campaigns
FastAPI Webhook Handler

Lightweight FastAPI app for:
- WhatsApp webhook callbacks (delivery receipts, read receipts, replies, opt-outs)
- Event-driven campaign triggers (no-show follow-ups, etc.)

Usage:
    uvicorn ST-07.python.webhook_handler:app --host 0.0.0.0 --port 8007

Endpoints:
    GET  /webhook/whatsapp     - Meta verification challenge
    POST /webhook/whatsapp     - WhatsApp webhook events
    POST /api/v1/events/no-show - Trigger no-show follow-up
    GET  /health               - Health check
"""

import os
import sys
import logging
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse

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

# Import ST-07 modules
spec = importlib.util.spec_from_file_location(
    "whatsapp_client",
    os.path.join(project_root, "ST-07", "python", "whatsapp_client.py"),
)
wa_module = importlib.util.module_from_spec(spec)
sys.modules["whatsapp_client"] = wa_module
spec.loader.exec_module(wa_module)
WhatsAppClient = wa_module.WhatsAppClient

spec = importlib.util.spec_from_file_location(
    "campaign_manager",
    os.path.join(project_root, "ST-07", "python", "campaign_manager.py"),
)
cm_module = importlib.util.module_from_spec(spec)
sys.modules["campaign_manager"] = cm_module
spec.loader.exec_module(cm_module)
CampaignManager = cm_module.CampaignManager

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="ST-07 Campaign Webhooks", version="1.0.0")

# Initialize dependencies
db = DatabaseManager.get_instance()
wa_client = WhatsAppClient()
campaign_mgr = CampaignManager(db_manager=db)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "st07-campaign-webhooks"}


@app.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = None,
    hub_token: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None,
):
    """
    Meta webhook verification challenge.
    GET request with hub.verify_token must match WHATSAPP_VERIFY_TOKEN.
    """
    if hub_mode == "subscribe" and hub_verify_token == wa_client.verify_token:
        logger.info("Webhook verified successfully")
        return int(hub_challenge)
    else:
        logger.warning("Webhook verification failed")
        raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook/whatsapp")
async def handle_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    """
    Handle WhatsApp webhook events.
    Processes delivery receipts, read receipts, replies, and opt-outs.
    Must return 200 OK within 3 seconds (Meta requirement).
    """
    body = await request.body()
    payload = await request.json()

    # Verify signature
    if not wa_client.verify_webhook_signature(
        body.decode("utf-8"), x_hub_signature_256 or ""
    ):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse events
    events = wa_client.parse_webhook_event(payload)

    # Process events (do this asynchronously to meet 3s requirement)
    for event in events:
        event_type = event.get("event_type", "")
        message_id = event.get("message_id", "")
        phone_number = event.get("phone_number", "")

        if event_type in ("sent", "delivered", "read", "failed"):
            # Find queue_id by whatsapp_message_id
            result = db.execute_query(
                """SELECT queue_id FROM dk.delivery_log 
                   WHERE whatsapp_message_id = :message_id LIMIT 1""",
                params={"message_id": message_id},
            )

            if result is not None and not result.empty:
                queue_id = int(result.iloc[0]["queue_id"])
                db.execute_query(
                    """SELECT dk.update_delivery_status(
                        :queue_id, :message_id, :status, :raw_response::jsonb
                    )""",
                    params={
                        "queue_id": queue_id,
                        "message_id": message_id,
                        "status": event_type,
                        "raw_response": str(event.get("raw", {})),
                    },
                    return_df=False,
                )
                logger.info(
                    f"Updated delivery status: queue_id={queue_id}, status={event_type}"
                )

        elif event_type == "opt_out":
            # Find mrn by phone number
            result = db.execute_query(
                """SELECT mrn FROM dk.patient_consent WHERE phone_number = :phone LIMIT 1""",
                params={"phone": phone_number},
            )
            if result is not None and not result.empty:
                mrn = str(result.iloc[0]["mrn"])
                campaign_mgr.process_opt_out(mrn, phone_number)
                logger.info(f"Processed opt-out for phone {phone_number}")

        elif event_type == "reply":
            logger.info(f"Patient reply from {phone_number}: {event.get('text', '')}")
            # Could trigger follow-up actions here in the future

    # Must return 200 quickly
    return JSONResponse(content={"success": True})


@app.post("/api/v1/events/no-show")
async def trigger_no_show(request: Request):
    """
    Trigger no-show follow-up for a specific patient.
    Called by booking system or manually.

    Body: {"mrn": "PATIENT001"}
    """
    body = await request.json()
    mrn = body.get("mrn")

    if not mrn:
        raise HTTPException(status_code=400, detail="mrn is required")

    count = campaign_mgr.queue_no_show_followup(mrn=mrn)

    if count > 0:
        return {"success": True, "queued": count, "mrn": mrn}
    else:
        return {
            "success": False,
            "error": "Patient not found or no consent",
            "mrn": mrn,
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8007)
