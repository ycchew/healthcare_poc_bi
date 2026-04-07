"""
ST-07: Automation & Campaigns
Python module for WhatsApp campaigns and automation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import os
import requests
from database import execute_query, execute_sql


def get_campaign_performance(campaign_id: Optional[int] = None) -> pd.DataFrame:
    """Get campaign performance metrics."""
    query = "SELECT * FROM dk.vw_campaign_performance WHERE 1=1"
    if campaign_id:
        query += f" AND campaign_id = {campaign_id}"
    query += " ORDER BY start_date DESC"
    return execute_query(query)


def get_campaign_patient_details(campaign_id: int) -> pd.DataFrame:
    """Get detailed patient-level campaign data."""
    query = f"SELECT * FROM dk.vw_campaign_patient_details WHERE campaign_id = {campaign_id}"
    return execute_query(query)


def get_d3_followup_queue() -> pd.DataFrame:
    """Get D+3 follow-up queue."""
    return execute_query("SELECT * FROM dk.vw_d3_followup_queue")


def get_conversion_attribution(days: int = 30) -> pd.DataFrame:
    """Get conversion attribution for recent campaigns."""
    query = f"""
    SELECT * FROM dk.vw_conversion_attribution
    WHERE converted_at >= CURRENT_DATE - INTERVAL '{days} days'
    ORDER BY converted_at DESC
    """
    return execute_query(query)


def create_d3_campaign(campaign_name: str, max_patients: int = 100) -> Optional[int]:
    """Create a D+3 follow-up campaign."""
    query = f"SELECT dk.create_d3_campaign(:name, :max_patients) AS campaign_id"
    params = {"name": campaign_name, "max_patients": max_patients}

    df = execute_query(query, params)
    if df.empty:
        return None
    return df["campaign_id"].iloc[0]


def send_whatsapp_message(
    phone: str,
    message: str,
    template_name: Optional[str] = None,
    parameters: Optional[Dict] = None,
) -> Dict:
    """Send WhatsApp message via WhatsApp Business API."""

    phone_id = os.getenv("WHATSAPP_PHONE_ID")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")

    if not phone_id or not access_token:
        return {"success": False, "error": "WhatsApp credentials not configured"}

    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Format phone number (remove non-numeric and ensure country code)
    phone = "".join(filter(str.isdigit, phone))
    if not phone.startswith("60") and len(phone) == 9:
        phone = "60" + phone

    if template_name:
        # Use template message
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(v)}
                            for k, v in (parameters or {}).items()
                        ],
                    }
                ],
            },
        }
    else:
        # Use text message
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {"body": message},
        }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "message_id": response.json().get("messages", [{}])[0].get("id"),
        }
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def send_campaign_messages(campaign_id: int, batch_size: int = 50) -> Dict:
    """Send WhatsApp messages for a campaign."""

    # Get campaign details
    campaign_query = f"""
    SELECT c.*, t.message_body, t.template_code
    FROM dk.campaigns c
    JOIN dk.whatsapp_campaign_templates t ON c.template_code = t.template_code
    WHERE c.campaign_id = {campaign_id}
    """
    campaign = execute_query(campaign_query)

    if campaign.empty:
        return {"success": False, "error": "Campaign not found"}

    # Get pending patients
    patients_query = f"""
    SELECT * FROM dk.campaign_assignments
    WHERE campaign_id = {campaign_id} AND status = 'pending'
    LIMIT {batch_size}
    """
    patients = execute_query(patients_query)

    if patients.empty:
        return {"success": True, "sent": 0, "message": "No pending patients"}

    results = {"sent": 0, "failed": 0, "errors": []}

    for _, patient in patients.iterrows():
        # Personalize message
        message = campaign["message_body"].iloc[0]
        if patient["patient_name"]:
            message = message.replace("{{patient_name}}", patient["patient_name"])

        # Send message
        result = send_whatsapp_message(
            phone=patient["phone"],
            message=message,
            template_name=campaign["template_code"].iloc[0]
            if campaign["template_code"].iloc[0]
            else None,
        )

        # Update assignment status
        if result["success"]:
            execute_sql(
                """UPDATE dk.campaign_assignments 
                   SET status = 'sent', sent_at = CURRENT_TIMESTAMP, message_id = :msg_id
                   WHERE assignment_id = :id""",
                {"msg_id": result.get("message_id"), "id": patient["assignment_id"]},
            )
            results["sent"] += 1
        else:
            execute_sql(
                """UPDATE dk.campaign_assignments 
                   SET status = 'failed', error_message = :error
                   WHERE assignment_id = :id""",
                {"error": result.get("error"), "id": patient["assignment_id"]},
            )
            results["failed"] += 1
            results["errors"].append(result.get("error"))

    return results


def update_campaign_status(campaign_id: int, status: str) -> None:
    """Update campaign status."""
    query = "UPDATE dk.campaigns SET status = :status WHERE campaign_id = :id"
    execute_sql(query, {"status": status, "id": campaign_id})


def record_conversion(assignment_id: int, order_id: str, revenue: float) -> None:
    """Record a conversion for a campaign assignment."""
    query = """
    UPDATE dk.campaign_assignments
    SET status = 'converted',
        converted_at = CURRENT_TIMESTAMP,
        conversion_order_id = :order_id,
        conversion_revenue = :revenue
    WHERE assignment_id = :id
    """
    execute_sql(query, {"order_id": order_id, "revenue": revenue, "id": assignment_id})


def get_campaign_roi(campaign_id: int) -> Dict:
    """Calculate campaign ROI."""
    query = f"""
    SELECT 
        c.campaign_id,
        c.campaign_name,
        c.campaign_type,
        COUNT(*) AS total_sent,
        COUNT(*) FILTER (WHERE status = 'converted') AS conversions,
        SUM(conversion_revenue) AS total_revenue,
        AVG(conversion_revenue) AS avg_conversion_value
    FROM dk.campaigns c
    LEFT JOIN dk.campaign_assignments ca ON c.campaign_id = ca.campaign_id
    WHERE c.campaign_id = {campaign_id}
    GROUP BY c.campaign_id, c.campaign_name, c.campaign_type
    """

    df = execute_query(query)
    if df.empty:
        return {}

    row = df.iloc[0]
    # Estimate cost at $0.05 per message
    estimated_cost = row["total_sent"] * 0.05

    return {
        "campaign_id": row["campaign_id"],
        "campaign_name": row["campaign_name"],
        "messages_sent": row["total_sent"],
        "conversions": row["conversions"],
        "conversion_rate": row["conversions"] / row["total_sent"] * 100
        if row["total_sent"] > 0
        else 0,
        "total_revenue": row["total_revenue"] or 0,
        "estimated_cost": estimated_cost,
        "roi": ((row["total_revenue"] or 0) - estimated_cost) / estimated_cost * 100
        if estimated_cost > 0
        else 0,
    }


def export_campaign_report(campaign_id: int, output_path: Optional[str] = None) -> str:
    """Export campaign report to Excel."""
    if output_path is None:
        output_path = f"./docs/output/campaign_{campaign_id}_report.xlsx"

    performance = get_campaign_performance(campaign_id)
    details = get_campaign_patient_details(campaign_id)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        performance.to_excel(writer, sheet_name="Performance", index=False)
        details.to_excel(writer, sheet_name="Patient Details", index=False)

    return output_path


def run_automated_d3_campaign(max_patients: int = 100) -> Optional[int]:
    """Run automated D+3 campaign for eligible patients."""
    # Check queue
    queue = get_d3_followup_queue()

    if queue.empty:
        print("No patients eligible for D+3 campaign")
        return None

    # Create campaign
    campaign_name = f"D3_Followup_{datetime.now().strftime('%Y%m%d')}"
    campaign_id = create_d3_campaign(campaign_name, max_patients)

    if not campaign_id:
        print("Failed to create campaign")
        return None

    print(f"Created campaign {campaign_id} with name: {campaign_name}")

    # Send messages
    results = send_campaign_messages(campaign_id)
    print(f"Sent: {results['sent']}, Failed: {results['failed']}")

    return campaign_id


if __name__ == "__main__":
    print("ST-07 Automation & Campaigns Module")
    print("=" * 50)

    queue = get_d3_followup_queue()
    print(f"\nD+3 Follow-up Queue: {len(queue)} patients")

    if not queue.empty:
        print(queue[["patient_name", "followup_priority", "last_visit_amount"]].head())
