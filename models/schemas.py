"""
AppraisAI — Pydantic Schemas
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class OrderCreate(BaseModel):
    property_address: str
    city_state_zip: str
    property_type: str
    estimated_value: Optional[str] = None
    gba: Optional[str] = None
    year_built: Optional[str] = None
    purpose: str
    additional_notes: Optional[str] = None
    full_name: str
    company: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    service_level: str  # 'standard', 'professional', 'enterprise'


class OrderResponse(BaseModel):
    id: str
    order_number: str
    status: str
    property_address: str
    service_level: str
    price_cents: int
    created_at: datetime
    stripe_client_secret: Optional[str] = None  # returned on creation for Stripe


class OrderStatusResponse(BaseModel):
    order_number: str
    status: str
    property_address: str
    assigned_appraiser: Optional[str] = None
    draft_ready: bool
    certified: bool
    download_url: Optional[str] = None


class AppraiserCertifyRequest(BaseModel):
    order_id: str
    appraiser_notes: Optional[str] = None
    checklist_items: Optional[dict] = None


class AppraiserLoginRequest(BaseModel):
    email: EmailStr
    password: str


SERVICE_PRICES = {
    "standard":     150000,   # $1,500 in cents
    "professional": 220000,   # $2,200
    "enterprise":   0,        # custom — contact sales
}
