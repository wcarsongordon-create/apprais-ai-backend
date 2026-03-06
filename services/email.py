"""
AppraisAI — Email Service (Resend)
====================================
Sends transactional emails for:
  - Order confirmation to client
  - Draft ready notification to assigned appraiser
  - Certified report delivery to client
"""

import os
import logging
import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "orders@apprais-ai.com")
APP_URL    = os.getenv("APP_URL", "https://apprais-ai.com")


# ── Order Confirmation ────────────────────────────────────────────────────────

async def send_order_confirmation(
    to_email: str,
    client_name: str,
    order_number: str,
    property_address: str,
    service_level: str,
) -> None:
    price_map = {"standard": "$1,500", "professional": "$2,200", "enterprise": "Custom"}
    price = price_map.get(service_level, "")
    level = service_level.title()

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #1e293b;">
      <div style="background: #1D4ED8; padding: 32px 40px; border-radius: 8px 8px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 24px;">
          Apprais<span style="color: #84CC16;">ai</span>
        </h1>
        <p style="color: #bfdbfe; margin: 8px 0 0;">Commercial Appraisal Services</p>
      </div>

      <div style="background: #f8fafc; padding: 40px; border-radius: 0 0 8px 8px; border: 1px solid #e2e8f0;">
        <h2 style="margin: 0 0 16px; color: #1e293b;">Order Confirmed</h2>
        <p>Hi {client_name},</p>
        <p>Thank you for your order. We've received your appraisal request and our AI system will begin researching your property shortly.</p>

        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; margin: 24px 0;">
          <table style="width: 100%; border-collapse: collapse;">
            <tr>
              <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Order Number</td>
              <td style="padding: 8px 0; font-weight: 600; text-align: right;">{order_number}</td>
            </tr>
            <tr>
              <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Property</td>
              <td style="padding: 8px 0; font-weight: 600; text-align: right;">{property_address}</td>
            </tr>
            <tr>
              <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Service Level</td>
              <td style="padding: 8px 0; font-weight: 600; text-align: right;">{level} — {price}</td>
            </tr>
          </table>
        </div>

        <h3 style="color: #1D4ED8; margin-bottom: 8px;">What Happens Next</h3>
        <ol style="color: #475569; line-height: 1.8;">
          <li>Our AI researches your property and generates a draft appraisal report</li>
          <li>A Certified General Appraiser reviews, verifies, and signs the report</li>
          <li>You receive your completed USPAP-compliant appraisal via email</li>
        </ol>
        <p style="color: #64748b; font-size: 14px;">Typical turnaround is <strong>24–48 hours</strong>.</p>

        <div style="text-align: center; margin: 32px 0;">
          <a href="{APP_URL}/#portal"
             style="background: #1D4ED8; color: white; padding: 14px 32px; border-radius: 6px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            Track Your Order
          </a>
        </div>

        <p style="color: #94a3b8; font-size: 12px; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
          Questions? Reply to this email or contact support@apprais-ai.com<br>
          AppraisAI · USPAP-Compliant Commercial Appraisals
        </p>
      </div>
    </div>
    """

    try:
        resend.Emails.send({
            "from": f"AppraisAI Orders <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": f"Order Confirmed: {order_number} — {property_address}",
            "html": html,
        })
        logger.info(f"Order confirmation sent to {to_email} for {order_number}")
    except Exception as e:
        logger.error(f"Failed to send order confirmation to {to_email}: {e}")


# ── Appraiser Notification ────────────────────────────────────────────────────

async def send_appraiser_notification(
    to_email: str,
    appraiser_name: str,
    order_number: str,
    property_address: str,
) -> None:
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #1e293b;">
      <div style="background: #1D4ED8; padding: 32px 40px; border-radius: 8px 8px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 24px;">
          Apprais<span style="color: #84CC16;">ai</span>
        </h1>
        <p style="color: #bfdbfe; margin: 8px 0 0;">Appraiser Portal</p>
      </div>

      <div style="background: #f8fafc; padding: 40px; border-radius: 0 0 8px 8px; border: 1px solid #e2e8f0;">
        <h2 style="margin: 0 0 16px; color: #1e293b;">New Draft Ready for Review</h2>
        <p>Hi {appraiser_name},</p>
        <p>An AI-generated draft appraisal report is ready for your review and certification.</p>

        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; margin: 24px 0;">
          <table style="width: 100%; border-collapse: collapse;">
            <tr>
              <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Order Number</td>
              <td style="padding: 8px 0; font-weight: 600; text-align: right;">{order_number}</td>
            </tr>
            <tr>
              <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Property</td>
              <td style="padding: 8px 0; font-weight: 600; text-align: right;">{property_address}</td>
            </tr>
          </table>
        </div>

        <p>Please log in to the Appraiser Portal to:</p>
        <ul style="color: #475569; line-height: 1.8;">
          <li>Download and review the AI draft</li>
          <li>Make any corrections or annotations</li>
          <li>Upload the certified final report</li>
          <li>Complete the USPAP certification checklist</li>
        </ul>

        <div style="text-align: center; margin: 32px 0;">
          <a href="{APP_URL}/#appraiser-portal"
             style="background: #84CC16; color: #1e293b; padding: 14px 32px; border-radius: 6px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            Open Appraiser Portal
          </a>
        </div>

        <p style="color: #94a3b8; font-size: 12px; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
          AppraisAI · USPAP-Compliant Commercial Appraisals
        </p>
      </div>
    </div>
    """

    try:
        resend.Emails.send({
            "from": f"AppraisAI <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": f"New Draft Ready: {order_number} — {property_address}",
            "html": html,
        })
        logger.info(f"Appraiser notification sent to {to_email} for {order_number}")
    except Exception as e:
        logger.error(f"Failed to send appraiser notification to {to_email}: {e}")


# ── Report Delivery to Client ─────────────────────────────────────────────────

async def send_report_delivery(
    to_email: str,
    client_name: str,
    order_number: str,
    property_address: str,
    download_url: str,
    appraiser_name: str,
) -> None:
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #1e293b;">
      <div style="background: #1D4ED8; padding: 32px 40px; border-radius: 8px 8px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 24px;">
          Apprais<span style="color: #84CC16;">ai</span>
        </h1>
        <p style="color: #bfdbfe; margin: 8px 0 0;">Your Certified Appraisal Report is Ready</p>
      </div>

      <div style="background: #f8fafc; padding: 40px; border-radius: 0 0 8px 8px; border: 1px solid #e2e8f0;">
        <h2 style="margin: 0 0 16px; color: #1e293b;">Report Certified &amp; Ready for Download</h2>
        <p>Hi {client_name},</p>
        <p>Great news — your USPAP-compliant appraisal report has been certified by <strong>{appraiser_name}</strong> and is ready for download.</p>

        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; margin: 24px 0;">
          <table style="width: 100%; border-collapse: collapse;">
            <tr>
              <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Order Number</td>
              <td style="padding: 8px 0; font-weight: 600; text-align: right;">{order_number}</td>
            </tr>
            <tr>
              <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Property</td>
              <td style="padding: 8px 0; font-weight: 600; text-align: right;">{property_address}</td>
            </tr>
            <tr>
              <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Certified By</td>
              <td style="padding: 8px 0; font-weight: 600; text-align: right;">{appraiser_name}</td>
            </tr>
          </table>
        </div>

        <div style="text-align: center; margin: 32px 0;">
          <a href="{download_url}"
             style="background: #84CC16; color: #1e293b; padding: 14px 32px; border-radius: 6px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            ↓ Download Your Report (.docx)
          </a>
        </div>
        <p style="color: #64748b; font-size: 13px; text-align: center;">
          This download link expires in 24 hours. Log into the Client Portal to generate a new link anytime.
        </p>

        <p style="color: #94a3b8; font-size: 12px; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
          Questions? Contact support@apprais-ai.com<br>
          AppraisAI · USPAP-Compliant Commercial Appraisals
        </p>
      </div>
    </div>
    """

    try:
        resend.Emails.send({
            "from": f"AppraisAI <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": f"Your Appraisal Report is Ready — {order_number}",
            "html": html,
        })
        logger.info(f"Report delivery email sent to {to_email} for {order_number}")
    except Exception as e:
        logger.error(f"Failed to send report delivery to {to_email}: {e}")
