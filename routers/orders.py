"""
AppraisAI — Orders Router
===========================
POST /orders          — Submit a new appraisal order
GET  /orders/{id}     — Get order status (for client polling)
POST /orders/webhook  — Stripe payment webhook
"""

import os
import logging
import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, File
from typing import List, Optional
from supabase import create_client
import stripe
from models.schemas import OrderCreate, OrderResponse, OrderStatusResponse, SERVICE_PRICES
from services.claude_service import research_property, extract_generation_params
from services.generator import generate_report
from services.storage import upload_report, upload_order_document, download_file_bytes
from services.document_extractor import extract_text_from_bytes
from services.email import send_order_confirmation, send_appraiser_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["orders"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def get_db():
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )


# ── POST /orders — Submit a new order ────────────────────────────────────────
@router.post("", response_model=OrderResponse)
async def create_order(payload: OrderCreate, background_tasks: BackgroundTasks):
    db = get_db()

    price_cents = SERVICE_PRICES.get(payload.service_level, 0)
    if price_cents == 0 and payload.service_level != "enterprise":
        raise HTTPException(400, "Invalid service level")

    # 1. Upsert client user record
    user_res = db.table("users").upsert(
        {"email": payload.email, "full_name": payload.full_name,
         "company": payload.company, "phone": payload.phone, "role": "client"},
        on_conflict="email"
    ).execute()
    client_id = user_res.data[0]["id"]

    # 2. Generate order number
    order_num_res = db.rpc("generate_order_number").execute()
    order_number = order_num_res.data

    # 3. Create order record
    order_res = db.table("orders").insert({
        "order_number":      order_number,
        "client_id":         client_id,
        "property_address":  payload.property_address,
        "city_state_zip":    payload.city_state_zip,
        "property_type":     payload.property_type,
        "estimated_value":   payload.estimated_value,
        "gba":               payload.gba,
        "year_built":        payload.year_built,
        "purpose":           payload.purpose,
        "additional_notes":  payload.additional_notes,
        "service_level":     payload.service_level,
        "price_cents":       price_cents,
        "status":            "pending",
    }).execute()
    order = order_res.data[0]
    order_id = order["id"]

    # 4. Create Stripe PaymentIntent (skip for enterprise)
    stripe_client_secret = None
    if price_cents > 0:
        intent = stripe.PaymentIntent.create(
            amount=price_cents,
            currency="usd",
            metadata={"order_id": order_id, "order_number": order_number},
            description=f"AppraisAI {payload.service_level.title()} Appraisal — {order_number}",
        )
        db.table("orders").update({
            "stripe_payment_intent_id": intent.id
        }).eq("id", order_id).execute()
        stripe_client_secret = intent.client_secret

    # 5. Log event
    db.table("order_events").insert({
        "order_id": order_id, "event_type": "order_created",
        "description": f"Order {order_number} submitted by {payload.email}"
    }).execute()

    # 6. Send confirmation email
    background_tasks.add_task(
        send_order_confirmation,
        to_email=payload.email,
        client_name=payload.full_name,
        order_number=order_number,
        property_address=payload.property_address,
        service_level=payload.service_level,
    )

    return OrderResponse(
        id=order_id,
        order_number=order_number,
        status="pending",
        property_address=payload.property_address,
        service_level=payload.service_level,
        price_cents=price_cents,
        created_at=order["created_at"],
        stripe_client_secret=stripe_client_secret,
    )


# ── Stripe Webhook — confirm payment → kick off AI generation ─────────────
@router.post("/webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, os.getenv("STRIPE_WEBHOOK_SECRET")
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid Stripe signature")

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        order_id = intent["metadata"].get("order_id")
        if order_id:
            db = get_db()
            db.table("orders").update({
                "stripe_payment_status": "paid",
                "status": "paid"
            }).eq("id", order_id).execute()

            db.table("order_events").insert({
                "order_id": order_id, "event_type": "payment_received",
                "description": f"Stripe payment confirmed: {intent['id']}"
            }).execute()

            # Kick off AI generation in the background
            order = db.table("orders").select("*").eq("id", order_id).single().execute().data
            background_tasks.add_task(run_ai_generation, order_id, order)

    return {"status": "ok"}


# ── GET /orders/{order_id}/status — Poll from frontend ───────────────────────
@router.get("/{order_id}/status", response_model=OrderStatusResponse)
async def get_order_status(order_id: str):
    db = get_db()
    order = db.table("orders").select("*, appraisals(*)").eq("id", order_id).single().execute().data

    if not order:
        raise HTTPException(404, "Order not found")

    appraisal = (order.get("appraisals") or [{}])[0] if order.get("appraisals") else {}
    download_url = None

    if appraisal.get("certified_docx_path"):
        # Generate a signed URL valid for 1 hour
        signed = get_db().storage.from_(os.getenv("STORAGE_BUCKET", "appraisal-reports")) \
            .create_signed_url(appraisal["certified_docx_path"], 3600)
        download_url = signed.get("signedURL")
    elif appraisal.get("draft_docx_path") and order["status"] == "appraiser_review":
        signed = get_db().storage.from_(os.getenv("STORAGE_BUCKET", "appraisal-reports")) \
            .create_signed_url(appraisal["draft_docx_path"], 3600)
        download_url = signed.get("signedURL")

    appraiser_name = None
    if order.get("assigned_appraiser_id"):
        appraiser = db.table("users").select("full_name").eq("id", order["assigned_appraiser_id"]).single().execute().data
        if appraiser:
            appraiser_name = appraiser["full_name"]

    return OrderStatusResponse(
        order_number=order["order_number"],
        status=order["status"],
        property_address=order["property_address"],
        assigned_appraiser=appraiser_name,
        draft_ready=order["status"] in ("appraiser_review", "certified", "delivered"),
        certified=order["status"] in ("certified", "delivered"),
        download_url=download_url,
    )



# ── POST /orders/{order_id}/documents — Upload client documents ────────────────────
@router.post("/{order_id}/documents")
async def upload_order_documents(
    order_id: str,
    doc_type: str = "general",
    files: List[UploadFile] = File(...),
):
    """
    Upload income statements, lease documents, expense reports, etc.
    for an existing order. Call this right after order creation,
    before AI generation completes.
    doc_type: 'income', 'expenses', or 'general'
    """
    db = get_db()
    order_res = db.table("orders").select("id").eq("id", order_id).execute()
    if not order_res.data:
        raise HTTPException(status_code=404, detail="Order not found")

    uploaded = []
    for file in files:
        file_bytes = await file.read()
        storage_path = await upload_order_document(
            file_bytes=file_bytes,
            filename=file.filename,
            order_id=order_id,
            doc_type=doc_type,
        )
        db.table("order_documents").insert({
            "order_id": order_id,
            "filename": file.filename,
            "storage_path": storage_path,
            "doc_type": doc_type,
            "file_size_bytes": len(file_bytes),
        }).execute()
        uploaded.append({"filename": file.filename, "storage_path": storage_path})

    return {"uploaded": uploaded, "count": len(uploaded)}


# ── Background task: run Claude research + generate .docx ────────────────────
async def run_ai_generation(order_id: str, order: dict):
    db = get_db()

    try:
        # Mark as AI processing
        db.table("orders").update({"status": "ai_processing"}).eq("id", order_id).execute()
        db.table("order_events").insert({
            "order_id": order_id, "event_type": "ai_processing_started",
            "description": "Claude AI research and report generation initiated"
        }).execute()

        # ── Fetch client-uploaded documents and extract text ──────────────────────
        document_texts = []
        try:
            docs_res = db.table("order_documents").select("*").eq("order_id", order_id).execute()
            for doc in (docs_res.data or []):
                try:
                    file_bytes = await download_file_bytes(doc["storage_path"])
                    text = extract_text_from_bytes(file_bytes, doc["filename"])
                    document_texts.append({
                        "filename": doc["filename"],
                        "doc_type": doc.get("doc_type", "general"),
                        "text": text,
                    })
                    logger.info(f"Extracted text from {doc['filename']} ({len(text)} chars)")
                except Exception as doc_err:
                    logger.warning(f"Could not process document {doc['filename']}: {doc_err}")
        except Exception as e:
            logger.warning(f"Could not load order documents for {order_id}: {e}")

                # Parse city/state/zip from combined field
        city_state_zip = order.get("city_state_zip", "")
        parts = city_state_zip.rsplit(",", 1)
        city = parts[0].strip() if parts else city_state_zip
        state_zip = parts[1].strip() if len(parts) > 1 else ""
        state_parts = state_zip.split()
        state = state_parts[0] if state_parts else ""
        zip_code = state_parts[1] if len(state_parts) > 1 else ""

        # 1. Call Claude to research the property
        research_data = await research_property(
            address=order["property_address"],
            city=city, state=state, zip_code=zip_code,
            property_type=order["property_type"],
            purpose=order.get("purpose", "general valuation"),
            estimated_value=order.get("estimated_value", ""),
            gba=order.get("gba", ""),
            year_built=order.get("year_built", ""),
            document_texts=document_texts if document_texts else None,
        )

        # Save research data
        db.table("appraisals").upsert({
            "order_id": order_id,
            "research_data": research_data,
            "ai_model_used": research_data.get("_meta", {}).get("model", ""),
            "generation_seconds": research_data.get("_meta", {}).get("generation_seconds", 0),
        }, on_conflict="order_id").execute()

        # 2. Generate the .docx
        params = extract_generation_params(research_data)
        # Set client info and intended use from order
        params["intended_use"] = order.get("purpose", "general valuation")
        params["report_type"] = "Appraisal Report"

        safe_addr = order["property_address"].replace(" ", "_").replace("/", "_")[:40]
        output_filename = f"AppraisAI_Draft_{order['order_number']}_{safe_addr}.docx"
        output_path = f"/tmp/{output_filename}"

        docx_bytes = generate_report(**params, output_path=output_path)

        # 3. Upload to Supabase Storage
        storage_path = await upload_report(
            file_bytes=docx_bytes,
            filename=output_filename,
            folder=f"drafts/{order_id}"
        )

        # 4. Update appraisal record with file path
        db.table("appraisals").update({
            "draft_docx_path": storage_path
        }).eq("order_id", order_id).execute()

        # 5. Assign to an available appraiser (round-robin from active appraisers)
        appraiser = db.table("users") \
            .select("id, full_name") \
            .eq("role", "appraiser") \
            .eq("is_active", True) \
            .limit(1).execute().data

        appraiser_id = appraiser[0]["id"] if appraiser else None
        appraiser_name = appraiser[0]["full_name"] if appraiser else "Unassigned"

        db.table("orders").update({
            "status": "appraiser_review",
            "assigned_appraiser_id": appraiser_id,
        }).eq("id", order_id).execute()

        db.table("order_events").insert({
            "order_id": order_id, "event_type": "draft_generated",
            "description": f"AI draft generated and assigned to {appraiser_name}"
        }).execute()

        # 6. Notify appraiser
        if appraiser_id and appraiser:
            appraiser_email = db.table("users").select("email").eq("id", appraiser_id).single().execute().data
            if appraiser_email:
                await send_appraiser_notification(
                    to_email=appraiser_email["email"],
                    appraiser_name=appraiser_name,
                    order_number=order["order_number"],
                    property_address=order["property_address"],
                )

        logger.info(f"AI generation complete for order {order['order_number']}")

    except Exception as e:
        logger.error(f"AI generation failed for order {order_id}: {e}")
        db.table("orders").update({"status": "paid"}).eq("id", order_id).execute()
        db.table("appraisals").upsert({
            "order_id": order_id,
            "error_message": str(e)
        }, on_conflict="order_id").execute()
        db.table("order_events").insert({
            "order_id": order_id, "event_type": "ai_generation_failed",
            "description": str(e)
        }).execute()


