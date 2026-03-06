"""
AppraisAI — Appraiser Portal Router
======================================
GET  /appraisers/orders            — List all orders assigned to the logged-in appraiser
GET  /appraisers/orders/{id}       — Get full order + appraisal detail
POST /appraisers/orders/{id}/certify  — Certify a report (upload final docx)
GET  /appraisers/orders/{id}/download — Get signed URL for draft docx
POST /appraisers/orders/{id}/upload-certified — Upload the certified final .docx
"""

import os
import logging
from fastapi import APIRouter, HTTPException, Header, UploadFile, File
from supabase import create_client
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from services.storage import upload_report, get_signed_url
from services.email import send_report_delivery

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/appraisers", tags=["appraisers"])


def get_db():
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )


def verify_appraiser(x_appraiser_token: str) -> dict:
    """
    Validate appraiser session token issued by Supabase Auth.
    Returns the appraiser user record or raises 401.
    """
    if not x_appraiser_token:
        raise HTTPException(401, "Missing appraiser token")

    # Use Supabase Auth to verify the JWT and get user
    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    try:
        user_resp = client.auth.get_user(x_appraiser_token)
        user_id = user_resp.user.id
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    # Confirm this user is an appraiser
    db_user = client.table("users").select("*").eq("id", user_id).single().execute().data
    if not db_user or db_user.get("role") != "appraiser":
        raise HTTPException(403, "Not authorized as appraiser")

    return db_user


# ── GET /appraisers/orders — List assigned orders ─────────────────────────────
@router.get("/orders")
async def list_assigned_orders(x_appraiser_token: str = Header(None)):
    appraiser = verify_appraiser(x_appraiser_token)
    db = get_db()

    orders = db.table("orders") \
        .select("id, order_number, property_address, city_state_zip, property_type, status, created_at, service_level") \
        .eq("assigned_appraiser_id", appraiser["id"]) \
        .order("created_at", desc=True) \
        .execute().data

    return {"orders": orders, "appraiser_name": appraiser["full_name"]}


# ── GET /appraisers/orders/{id} — Full order detail ───────────────────────────
@router.get("/orders/{order_id}")
async def get_order_detail(order_id: str, x_appraiser_token: str = Header(None)):
    appraiser = verify_appraiser(x_appraiser_token)
    db = get_db()

    order = db.table("orders") \
        .select("*, appraisals(*)") \
        .eq("id", order_id) \
        .eq("assigned_appraiser_id", appraiser["id"]) \
        .single().execute().data

    if not order:
        raise HTTPException(404, "Order not found or not assigned to you")

    appraisal = (order.get("appraisals") or [{}])[0] if order.get("appraisals") else {}

    # Generate signed URLs
    draft_url = get_signed_url(appraisal.get("draft_docx_path"), 3600) if appraisal.get("draft_docx_path") else None
    certified_url = get_signed_url(appraisal.get("certified_docx_path"), 3600) if appraisal.get("certified_docx_path") else None

    # Get client info
    client_info = db.table("users").select("full_name, email, company, phone") \
        .eq("id", order["client_id"]).single().execute().data or {}

    # Get order events
    events = db.table("order_events") \
        .select("event_type, description, created_at") \
        .eq("order_id", order_id) \
        .order("created_at", desc=False) \
        .execute().data

    return {
        "order": order,
        "appraisal": appraisal,
        "client": client_info,
        "draft_url": draft_url,
        "certified_url": certified_url,
        "events": events,
    }


# ── GET /appraisers/orders/{id}/download-draft ────────────────────────────────
@router.get("/orders/{order_id}/download-draft")
async def download_draft(order_id: str, x_appraiser_token: str = Header(None)):
    appraiser = verify_appraiser(x_appraiser_token)
    db = get_db()

    appraisal = db.table("appraisals") \
        .select("draft_docx_path") \
        .eq("order_id", order_id) \
        .single().execute().data

    order = db.table("orders").select("assigned_appraiser_id").eq("id", order_id).single().execute().data
    if not order or order.get("assigned_appraiser_id") != appraiser["id"]:
        raise HTTPException(403, "Not your order")

    if not appraisal or not appraisal.get("draft_docx_path"):
        raise HTTPException(404, "Draft not ready yet")

    url = get_signed_url(appraisal["draft_docx_path"], 3600)
    if not url:
        raise HTTPException(500, "Could not generate download URL")

    return {"download_url": url, "expires_in": 3600}


class CertifyRequest(BaseModel):
    appraiser_notes: Optional[str] = None
    checklist_items: Optional[dict] = None


# ── POST /appraisers/orders/{id}/upload-certified — Upload final .docx ────────
@router.post("/orders/{order_id}/upload-certified")
async def upload_certified_report(
    order_id: str,
    file: UploadFile = File(...),
    x_appraiser_token: str = Header(None),
):
    appraiser = verify_appraiser(x_appraiser_token)
    db = get_db()

    # Confirm assignment
    order = db.table("orders") \
        .select("*, appraisals(id)") \
        .eq("id", order_id) \
        .eq("assigned_appraiser_id", appraiser["id"]) \
        .single().execute().data

    if not order:
        raise HTTPException(403, "Order not found or not assigned to you")

    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "Only .docx files accepted")

    file_bytes = await file.read()

    safe_addr = order["property_address"].replace(" ", "_").replace("/", "_")[:40]
    filename = f"AppraisAI_Certified_{order['order_number']}_{safe_addr}.docx"

    storage_path = await upload_report(
        file_bytes=file_bytes,
        filename=filename,
        folder=f"certified/{order_id}"
    )

    # Update appraisal record
    db.table("appraisals").update({
        "certified_docx_path": storage_path,
        "certified_at": datetime.utcnow().isoformat(),
        "certified_by": appraiser["id"],
    }).eq("order_id", order_id).execute()

    return {
        "status": "uploaded",
        "storage_path": storage_path,
        "message": "Certified report uploaded. Use /certify to finalize."
    }


# ── POST /appraisers/orders/{id}/certify — Mark as certified + notify client ──
@router.post("/orders/{order_id}/certify")
async def certify_order(
    order_id: str,
    payload: CertifyRequest,
    x_appraiser_token: str = Header(None),
):
    appraiser = verify_appraiser(x_appraiser_token)
    db = get_db()

    order = db.table("orders") \
        .select("*, appraisals(*)") \
        .eq("id", order_id) \
        .eq("assigned_appraiser_id", appraiser["id"]) \
        .single().execute().data

    if not order:
        raise HTTPException(403, "Order not found or not assigned to you")

    appraisal = (order.get("appraisals") or [{}])[0] if order.get("appraisals") else {}

    if not appraisal.get("certified_docx_path"):
        raise HTTPException(400, "Upload the certified .docx first via /upload-certified")

    # Update appraiser notes & checklist if provided
    update_data = {}
    if payload.appraiser_notes:
        update_data["appraiser_notes"] = payload.appraiser_notes
    if payload.checklist_items:
        update_data["checklist_items"] = payload.checklist_items
    if update_data:
        db.table("appraisals").update(update_data).eq("order_id", order_id).execute()

    # Update order status → certified
    db.table("orders").update({"status": "certified"}).eq("id", order_id).execute()

    db.table("order_events").insert({
        "order_id": order_id,
        "event_type": "certified",
        "actor_id": appraiser["id"],
        "description": f"Report certified by {appraiser['full_name']}"
    }).execute()

    # Generate 24-hour download link for client
    download_url = get_signed_url(appraisal["certified_docx_path"], 86400)

    # Get client info
    client = db.table("users").select("email, full_name").eq("id", order["client_id"]).single().execute().data

    if client and download_url:
        await send_report_delivery(
            to_email=client["email"],
            client_name=client["full_name"],
            order_number=order["order_number"],
            property_address=order["property_address"],
            download_url=download_url,
            appraiser_name=appraiser["full_name"],
        )

    # Mark as delivered
    db.table("orders").update({"status": "delivered"}).eq("id", order_id).execute()

    db.table("order_events").insert({
        "order_id": order_id,
        "event_type": "delivered",
        "actor_id": appraiser["id"],
        "description": f"Report delivered to client"
    }).execute()

    return {
        "status": "delivered",
        "order_number": order["order_number"],
        "message": "Report certified and delivery email sent to client."
    }


# ── POST /appraisers/orders/{id}/revision — Request changes ───────────────────
class RevisionRequest(BaseModel):
    notes: str


@router.post("/orders/{order_id}/revision")
async def request_revision(
    order_id: str,
    payload: RevisionRequest,
    x_appraiser_token: str = Header(None),
):
    appraiser = verify_appraiser(x_appraiser_token)
    db = get_db()

    order = db.table("orders") \
        .select("id, order_number, assigned_appraiser_id") \
        .eq("id", order_id) \
        .eq("assigned_appraiser_id", appraiser["id"]) \
        .single().execute().data

    if not order:
        raise HTTPException(403, "Order not found or not assigned to you")

    db.table("orders").update({"status": "revision"}).eq("id", order_id).execute()

    db.table("appraisals").update({"appraiser_notes": payload.notes}).eq("order_id", order_id).execute()

    db.table("order_events").insert({
        "order_id": order_id,
        "event_type": "revision_requested",
        "actor_id": appraiser["id"],
        "description": f"Revision requested: {payload.notes[:200]}"
    }).execute()

    return {"status": "revision", "message": "Order flagged for revision."}
