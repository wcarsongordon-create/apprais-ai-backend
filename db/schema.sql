-- ═══════════════════════════════════════════════════════════════
--  AppraisAI — Supabase Database Schema
--  Run this in: Supabase Dashboard → SQL Editor → New Query
-- ═══════════════════════════════════════════════════════════════

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── USERS ─────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    full_name       TEXT,
    company         TEXT,
    phone           TEXT,
    role            TEXT NOT NULL DEFAULT 'client'
                        CHECK (role IN ('client', 'appraiser', 'admin')),
    license_number  TEXT,           -- for appraisers
    license_state   TEXT,           -- for appraisers
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── ORDERS ────────────────────────────────────────────────────
CREATE TABLE orders (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number                TEXT UNIQUE NOT NULL,
    client_id                   UUID REFERENCES users(id),

    -- Property info
    property_address            TEXT NOT NULL,
    city_state_zip              TEXT NOT NULL,
    property_type               TEXT NOT NULL,
    estimated_value             TEXT,
    gba                         TEXT,
    year_built                  TEXT,
    purpose                     TEXT NOT NULL,
    additional_notes            TEXT,

    -- Service & payment
    service_level               TEXT NOT NULL
                                    CHECK (service_level IN ('standard', 'professional', 'enterprise')),
    price_cents                 INTEGER NOT NULL,
    stripe_payment_intent_id    TEXT,
    stripe_payment_status       TEXT DEFAULT 'unpaid',

    -- Workflow status
    status                      TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN (
                                        'pending',          -- order created, awaiting payment
                                        'paid',             -- payment confirmed
                                        'ai_processing',    -- Claude is generating the draft
                                        'appraiser_review', -- draft ready, assigned to appraiser
                                        'revision',         -- appraiser requested changes
                                        'certified',        -- appraiser signed off
                                        'delivered',        -- report sent to client
                                        'cancelled'
                                    )),

    -- Assignment
    assigned_appraiser_id       UUID REFERENCES users(id),
    assigned_at                 TIMESTAMPTZ,

    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- ── APPRAISALS ────────────────────────────────────────────────
CREATE TABLE appraisals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID REFERENCES orders(id) UNIQUE NOT NULL,

    -- Research data from Claude (stored as JSON)
    research_data       JSONB,

    -- Generated files (Supabase Storage URLs)
    draft_docx_path     TEXT,       -- path in storage bucket
    certified_docx_path TEXT,

    -- Appraiser review
    appraiser_notes     TEXT,
    checklist_items     JSONB,      -- which USPAP checklist items are checked
    certified_at        TIMESTAMPTZ,
    certified_by        UUID REFERENCES users(id),

    -- Generation metadata
    ai_model_used       TEXT,
    generation_seconds  INTEGER,
    error_message       TEXT,       -- if generation failed

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── ORDER EVENTS (audit trail) ────────────────────────────────
CREATE TABLE order_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id    UUID REFERENCES orders(id) NOT NULL,
    event_type  TEXT NOT NULL,  -- 'status_change', 'payment', 'note', etc.
    description TEXT,
    actor_id    UUID REFERENCES users(id),
    metadata    JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── HELPER: auto-update updated_at ───────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_appraisals_updated_at
    BEFORE UPDATE ON appraisals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── HELPER: generate order numbers ───────────────────────────
CREATE SEQUENCE order_number_seq START 1000;

CREATE OR REPLACE FUNCTION generate_order_number()
RETURNS TEXT AS $$
BEGIN
    RETURN 'APA-' || TO_CHAR(NOW(), 'YYYY') || '-' ||
           LPAD(nextval('order_number_seq')::TEXT, 4, '0');
END;
$$ LANGUAGE plpgsql;

-- ── ROW LEVEL SECURITY ────────────────────────────────────────
ALTER TABLE users      ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders     ENABLE ROW LEVEL SECURITY;
ALTER TABLE appraisals ENABLE ROW LEVEL SECURITY;

-- Service role (your backend) bypasses RLS automatically.
-- These policies govern direct client-side Supabase calls if you add them later.

-- Clients can only see their own orders
CREATE POLICY "clients_own_orders" ON orders
    FOR SELECT USING (client_id = auth.uid());

-- Appraisers can see orders assigned to them
CREATE POLICY "appraisers_assigned_orders" ON orders
    FOR SELECT USING (assigned_appraiser_id = auth.uid());

-- ── SEED: demo appraiser account ──────────────────────────────
-- (update email/name as needed; password is set via Supabase Auth)
INSERT INTO users (email, full_name, role, license_number, license_state)
VALUES ('appraiser@apprais-ai.com', 'Demo Appraiser, MAI', 'appraiser', 'DEMO-001', 'IN')
ON CONFLICT DO NOTHING;
