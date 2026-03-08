"""
AppraisAI — Auth Router
=========================
POST /auth/appraiser/login   — Appraiser login via Supabase Auth
POST /auth/appraiser/logout  — Invalidate session token
GET  /auth/appraiser/me      — Return logged-in appraiser profile
"""

import os
import logging
from fastapi import APIRouter, HTTPException, Header
from supabase import create_client
from models.schemas import AppraiserLoginRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_client():
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_ANON_KEY")   # Use anon key for Auth operations
    )


def get_db():
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )


# ── POST /auth/appraiser/login ────────────────────────────────────────────────
@router.post("/appraiser/login")
async def appraiser_login(payload: AppraiserLoginRequest):
    """
    Authenticate an appraiser using Supabase email/password Auth.
    Returns a session token to be passed in the X-Appraiser-Token header.
    """
    client = get_auth_client()

    try:
        result = client.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })
    except Exception as e:
        logger.warning(f"Login failed for {payload.email}: {e}")
        raise HTTPException(401, "Invalid email or password")

    if not result.session:
        raise HTTPException(401, "Login failed — no session returned")

    user_id = result.user.id

    # Verify this user is an appraiser in our users table
    db = get_db()
    db_result = db.table("users").select("*").eq("id", user_id).execute().data
        db_user = db_result[0] if db_result else None
    if not db_user:
        # First login — insert the user record linked to Supabase Auth
        db_user = db.table("users").upsert({
            "id": user_id,
            "email": payload.email,
            "role": "appraiser",
        }, on_conflict="id").execute().data[0]

    if db_user.get("role") != "appraiser":
        raise HTTPException(403, "This account is not an appraiser account")

    if not db_user.get("is_active", True):
        raise HTTPException(403, "Appraiser account is inactive")

    return {
        "access_token": result.session.access_token,
        "token_type": "bearer",
        "expires_at": result.session.expires_at,
        "appraiser": {
            "id": db_user["id"],
            "email": db_user["email"],
            "full_name": db_user.get("full_name", ""),
            "license_number": db_user.get("license_number", ""),
            "license_state": db_user.get("license_state", ""),
        }
    }


# ── POST /auth/appraiser/logout ───────────────────────────────────────────────
@router.post("/appraiser/logout")
async def appraiser_logout(x_appraiser_token: str = Header(None)):
    if not x_appraiser_token:
        raise HTTPException(401, "No token provided")

    try:
        client = get_auth_client()
        client.auth.sign_out()
    except Exception as e:
        logger.warning(f"Logout error (non-critical): {e}")

    return {"status": "logged_out"}


# ── GET /auth/appraiser/me ────────────────────────────────────────────────────
@router.get("/appraiser/me")
async def get_me(x_appraiser_token: str = Header(None)):
    if not x_appraiser_token:
        raise HTTPException(401, "Missing token")

    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    try:
        user_resp = client.auth.get_user(x_appraiser_token)
        user_id = user_resp.user.id
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    db = get_db()
    db_user = db.table("users").select("*").eq("id", user_id).single().execute().data

    if not db_user or db_user.get("role") != "appraiser":
        raise HTTPException(403, "Not an appraiser account")

    # Get stats
    stats = db.table("orders").select("status", count="exact") \
        .eq("assigned_appraiser_id", user_id).execute()

    all_orders = db.table("orders").select("status") \
        .eq("assigned_appraiser_id", user_id).execute().data or []

    status_counts = {}
    for o in all_orders:
        s = o.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "appraiser": {
            "id": db_user["id"],
            "email": db_user["email"],
            "full_name": db_user.get("full_name", ""),
            "license_number": db_user.get("license_number", ""),
            "license_state": db_user.get("license_state", ""),
            "is_active": db_user.get("is_active", True),
        },
        "stats": {
            "total_orders": len(all_orders),
            "pending_review": status_counts.get("appraiser_review", 0),
            "certified": status_counts.get("certified", 0) + status_counts.get("delivered", 0),
        }
    }
