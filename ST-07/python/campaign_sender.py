"""
ST-07: Automation & Campaigns
Campaign Queue Processor

Processes pending items from dk.campaign_queue and sends via WhatsApp API.
Used by both pgAgent (batch processing) and FastAPI (event-driven sends).

Usage:
    python ST-07/python/campaign_sender.py              # Process queue (default batch=50)
    python ST-07/python/campaign_sender.py --batch-size 100
    python ST-07/python/campaign_sender.py --test       # Run tests
"""

import os
import sys
import logging
import argparse
import time
from typing import Dict, Any, List, Optional

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

# Import ST-07 WhatsApp client
spec = importlib.util.spec_from_file_location(
    "whatsapp_client",
    os.path.join(project_root, "ST-07", "python", "whatsapp_client.py"),
)
wa_module = importlib.util.module_from_spec(spec)
sys.modules["whatsapp_client"] = wa_module
spec.loader.exec_module(wa_module)
WhatsAppClient = wa_module.WhatsAppClient

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def process_queue(
    db_manager: Optional[DatabaseManager] = None,
    whatsapp_client: Optional[WhatsAppClient] = None,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """
    Process pending campaign queue items.

    Fetches pending items from dk.vw_campaign_queue_pending, sends via WhatsApp API,
    and updates campaign_queue + delivery_log.

    Args:
        db_manager: DatabaseManager instance (creates one if None)
        whatsapp_client: WhatsAppClient instance (creates one if None)
        batch_size: Max items to process per call (default 50)

    Returns:
        Dict with 'sent', 'failed', 'skipped', 'errors' keys
    """
    db = db_manager or DatabaseManager.get_instance()
    client = whatsapp_client or WhatsAppClient()

    results = {
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    try:
        # Fetch pending items from view
        query = """
            SELECT queue_id, mrn, phone_number, template_name, template_params
            FROM dk.vw_campaign_queue_pending
            LIMIT :batch_size
        """
        pending_df = db.execute_query(query, params={"batch_size": batch_size})

        if pending_df.empty:
            logger.info("No pending items in campaign queue")
            return results

        logger.info(f"Processing {len(pending_df)} pending queue items...")

        for _, row in pending_df.iterrows():
            queue_id = row["queue_id"]
            mrn = row["mrn"]
            phone_number = row["phone_number"]
            template_name = row["template_name"]
            template_params = row["template_params"]

            # Mark as processing
            try:
                db.execute_query(
                    "UPDATE dk.campaign_queue SET status = 'processing' WHERE queue_id = :queue_id",
                    params={"queue_id": int(queue_id)},
                    return_df=False,
                )
            except Exception as e:
                logger.error(f"Failed to mark queue_id {queue_id} as processing: {e}")
                results["errors"].append({"queue_id": queue_id, "error": str(e)})
                results["failed"] += 1
                continue

            # Send via WhatsApp
            send_result = client.send_template(
                to=phone_number,
                template_name=template_name,
                components=template_params,
            )

            if send_result.get("success"):
                message_id = send_result.get("message_id", "")

                # Update queue status
                db.execute_query(
                    """UPDATE dk.campaign_queue 
                       SET status = 'sent', sent_at = NOW() 
                       WHERE queue_id = :queue_id""",
                    params={"queue_id": int(queue_id)},
                    return_df=False,
                )

                # Log delivery
                db.execute_query(
                    """INSERT INTO dk.delivery_log (queue_id, whatsapp_message_id, status, raw_response)
                       VALUES (:queue_id, :message_id, 'sent', :raw_response::jsonb)""",
                    params={
                        "queue_id": int(queue_id),
                        "message_id": message_id,
                        "raw_response": str(send_result),
                    },
                    return_df=False,
                )

                results["sent"] += 1
                logger.info(
                    f"Sent queue_id {queue_id} to {phone_number} ({template_name})"
                )
            else:
                error_msg = send_result.get("error", "Unknown error")

                # Update retry count or mark failed
                db.execute_query(
                    """UPDATE dk.campaign_queue 
                       SET retry_count = retry_count + 1,
                           status = CASE WHEN retry_count >= 3 THEN 'failed' ELSE 'pending' END,
                           error_message = :error_msg
                       WHERE queue_id = :queue_id""",
                    params={"queue_id": int(queue_id), "error_msg": error_msg[:500]},
                    return_df=False,
                )

                results["failed"] += 1
                logger.warning(f"Failed queue_id {queue_id}: {error_msg}")

        logger.info(
            f"Queue processing complete: {results['sent']} sent, "
            f"{results['failed']} failed, {results['skipped']} skipped"
        )

    except Exception as e:
        logger.error(f"Error processing queue: {e}")
        results["errors"].append({"error": str(e)})

    return results


def process_single_event(
    queue_id: int,
    db_manager: Optional[DatabaseManager] = None,
    whatsapp_client: Optional[WhatsAppClient] = None,
) -> Dict[str, Any]:
    """
    Process a single queue item (for event-driven sends).

    Args:
        queue_id: The queue_id to process
        db_manager: DatabaseManager instance
        whatsapp_client: WhatsAppClient instance

    Returns:
        Dict with send result
    """
    db = db_manager or DatabaseManager.get_instance()
    client = whatsapp_client or WhatsAppClient()

    # Fetch the specific queue item
    query = """
        SELECT queue_id, mrn, phone_number, template_name, template_params
        FROM dk.campaign_queue
        WHERE queue_id = :queue_id AND status = 'pending'
    """
    result_df = db.execute_query(query, params={"queue_id": queue_id})

    if result_df.empty:
        return {
            "success": False,
            "error": f"Queue item {queue_id} not found or not pending",
        }

    row = result_df.iloc[0]

    # Send via WhatsApp
    send_result = client.send_template(
        to=row["phone_number"],
        template_name=row["template_name"],
        components=row["template_params"],
    )

    if send_result.get("success"):
        message_id = send_result.get("message_id", "")

        db.execute_query(
            """UPDATE dk.campaign_queue SET status = 'sent', sent_at = NOW() WHERE queue_id = :queue_id""",
            params={"queue_id": queue_id},
            return_df=False,
        )

        db.execute_query(
            """INSERT INTO dk.delivery_log (queue_id, whatsapp_message_id, status, raw_response)
               VALUES (:queue_id, :message_id, 'sent', :raw_response::jsonb)""",
            params={
                "queue_id": queue_id,
                "message_id": message_id,
                "raw_response": str(send_result),
            },
            return_df=False,
        )

        return {"success": True, "message_id": message_id}
    else:
        db.execute_query(
            """UPDATE dk.campaign_queue 
               SET retry_count = retry_count + 1,
                   status = CASE WHEN retry_count >= 3 THEN 'failed' ELSE 'pending' END,
                   error_message = :error_msg
               WHERE queue_id = :queue_id""",
            params={
                "queue_id": queue_id,
                "error_msg": send_result.get("error", "")[:500],
            },
            return_df=False,
        )

        return {"success": False, "error": send_result.get("error", "Unknown error")}


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(description="Process campaign queue")
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Batch size (default: 50)"
    )
    parser.add_argument("--test", action="store_true", help="Run test mode")
    args = parser.parse_args()

    if args.test:
        logger.info("Test mode: checking queue status without sending")
        db = DatabaseManager.get_instance()
        query = "SELECT COUNT(*) as cnt FROM dk.vw_campaign_queue_pending"
        result = db.execute_query(query)
        count = result.iloc[0]["cnt"]
        logger.info(f"Pending items in queue: {count}")
        return

    results = process_queue(batch_size=args.batch_size)
    logger.info(f"Results: {results}")


if __name__ == "__main__":
    main()
