"""
ST-07: Automation & Campaigns
WhatsApp Cloud API Client

Direct integration with Meta WhatsApp Cloud API (no BSP).
Handles template message sending, webhook verification, rate limiting, and retries.

Usage:
    from whatsapp_client import WhatsAppClient
    client = WhatsAppClient()
    result = client.send_template(
        to="+60123456789",
        template_name="appointment_reminder",
        components={"1": "John", "2": "2026-04-05", "3": "10:00", "4": "KLCC"}
    )
"""

import os
import sys
import time
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv

# Add project root to path for imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv(override=True)

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """
    Direct Meta WhatsApp Cloud API client.

    Uses httpx for HTTP requests (already in requirements.txt as httpx>=0.25.0).
    Implements rate limiting, exponential backoff retries, and webhook signature verification.
    """

    BASE_URL = "https://graph.facebook.com"

    def __init__(
        self,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        verify_token: Optional[str] = None,
        api_version: str = "v21.0",
        tier_limit: Optional[int] = None,
    ):
        """
        Initialize WhatsApp client.

        Args:
            phone_number_id: Meta phone number ID (from .env: WHATSAPP_PHONE_NUMBER_ID)
            access_token: Meta Cloud API access token (from .env: WHATSAPP_ACCESS_TOKEN)
            verify_token: Webhook verification token (from .env: WHATSAPP_VERIFY_TOKEN)
            api_version: WhatsApp API version (default v21.0)
            tier_limit: Daily send limit (from .env: WHATSAPP_TIER_LIMIT, default 250)
        """
        self.phone_number_id = (
            phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        ).strip()
        self.access_token = (
            access_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        ).strip()
        self.verify_token = (
            verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        ).strip()
        self.api_version = api_version or os.getenv("WHATSAPP_API_VERSION", "v21.0")
        self.tier_limit = tier_limit or int(os.getenv("WHATSAPP_TIER_LIMIT", "250"))

        self._base_url = f"{self.BASE_URL}/{self.api_version}"
        self._messages_url = f"{self._base_url}/{self.phone_number_id}/messages"

        # Track daily send count (resets at midnight)
        self._daily_send_count = 0
        self._send_count_date = time.strftime("%Y-%m-%d")

        if not self.phone_number_id or not self.access_token:
            logger.warning(
                "WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN not set. "
                "WhatsApp client will operate in dry-run mode."
            )

    def _reset_daily_count_if_new_day(self):
        """Reset daily send counter if we've crossed midnight."""
        today = time.strftime("%Y-%m-%d")
        if today != self._send_count_date:
            self._daily_send_count = 0
            self._send_count_date = today

    def can_send(self) -> bool:
        """Check if we're within the daily tier limit."""
        self._reset_daily_count_if_new_day()
        return self._daily_send_count < self.tier_limit

    def _retry_with_backoff(
        self,
        func,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Execute function with exponential backoff retry.

        Args:
            func: Callable that returns Dict[str, Any] and may raise httpx.HTTPStatusError
            max_retries: Maximum number of retries (default 3)
            base_delay: Base delay in seconds (default 1.0)

        Returns:
            Result from func or error dict
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                result = func()
                return result
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"Rate limit hit (429). Retrying in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                elif e.response.status_code >= 500:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"Server error ({e.response.status_code}). Retrying in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                else:
                    raise
            except httpx.RequestError as e:
                last_error = e
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Request error: {e}. Retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)

        error_msg = str(last_error) if last_error else "Unknown error"
        return {
            "success": False,
            "error": f"All {max_retries} retries exhausted: {error_msg}",
        }

    def send_template(
        self,
        to: str,
        template_name: str,
        components: Dict[str, str],
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp template message.

        Args:
            to: Recipient phone number in E.164 format (e.g., +60123456789)
            template_name: Approved template name (must match Meta-registered name)
            components: Template variables as dict {"1": "value1", "2": "value2", ...}
            language: Template language code (default 'en')

        Returns:
            Dict with 'success' (bool), 'message_id' (str if success), 'error' (str if failed)
        """
        if not self.can_send():
            logger.error(
                f"Daily tier limit ({self.tier_limit}) reached. Message not sent."
            )
            return {
                "success": False,
                "error": f"Daily tier limit ({self.tier_limit}) reached",
            }

        if not self.phone_number_id or not self.access_token:
            logger.warning(f"DRY RUN: Would send template '{template_name}' to {to}")
            return {
                "success": True,
                "message_id": f"dry_run_{int(time.time())}",
                "dry_run": True,
            }

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": value}
                            for key, value in sorted(
                                components.items(), key=lambda x: x[0]
                            )
                        ],
                    }
                ],
            },
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        def _do_send():
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    self._messages_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

        try:
            result = self._retry_with_backoff(_do_send)

            if "error" in result and "success" not in result:
                return {
                    "success": False,
                    "error": result.get("error", {}).get("message", str(result)),
                    "error_code": result.get("error", {}).get("code"),
                }

            message_id = result.get("messages", [{}])[0].get("id", "")
            self._daily_send_count += 1
            logger.info(
                f"Message sent to {to} (template: {template_name}, id: {message_id})"
            )

            return {
                "success": True,
                "message_id": message_id,
                "raw_response": result,
            }

        except Exception as e:
            logger.error(f"Failed to send template '{template_name}' to {to}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """
        Verify WhatsApp webhook signature (X-Hub-Signature-256).

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        if not self.verify_token:
            logger.warning(
                "WHATSAPP_VERIFY_TOKEN not set - skipping signature verification"
            )
            return True

        expected_signature = hmac.new(
            self.verify_token.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(f"sha256={expected_signature}", signature)

    def parse_webhook_event(self, payload: Dict[str, Any]) -> list:
        """
        Parse WhatsApp webhook payload into structured events.

        Args:
            payload: Full webhook JSON payload from Meta

        Returns:
            List of parsed event dicts with keys:
                - event_type: 'sent', 'delivered', 'read', 'failed', 'reply', 'opt_out'
                - message_id: Meta message ID
                - phone_number: Customer phone number
                - timestamp: Event timestamp
                - raw: Original event data
        """
        events = []

        try:
            entry = payload.get("entry", [])
            for entry_item in entry:
                changes = entry_item.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    statuses = value.get("statuses", [])
                    messages = value.get("messages", [])

                    for status in statuses:
                        event = {
                            "event_type": status.get("status", "unknown"),
                            "message_id": status.get("id", ""),
                            "phone_number": status.get("recipient_id", ""),
                            "timestamp": status.get("timestamp", ""),
                            "raw": status,
                        }

                        if status.get("errors"):
                            event["event_type"] = "failed"
                            event["error"] = status["errors"][0].get("message", "")

                        events.append(event)

                    for message in messages:
                        event = {
                            "event_type": "reply",
                            "message_id": message.get("id", ""),
                            "phone_number": message.get("from", ""),
                            "timestamp": message.get("timestamp", ""),
                            "text": message.get("text", {}).get("body", ""),
                            "raw": message,
                        }

                        text = event.get("text", "").upper().strip()
                        if text in ("STOP", "UNSUBSCRIBE", "OPTOUT", "OPT-OUT"):
                            event["event_type"] = "opt_out"

                        events.append(event)

        except Exception as e:
            logger.error(f"Error parsing webhook event: {e}")

        return events

    def get_daily_send_count(self) -> int:
        """Get current daily send count."""
        self._reset_daily_count_if_new_day()
        return self._daily_send_count
