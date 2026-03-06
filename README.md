# AppraisAI Backend — Setup Guide

Full production backend for apprais-ai.com. This FastAPI app handles order intake, Stripe payments, Claude AI report generation, Supabase storage, and the appraiser portal.

---

## File Structure

```
appraisai-backend/
├── main.py                         ← FastAPI app entry point
├── Procfile                        ← Railway/Render start command
├── requirements.txt
├── .env.example                    ← Copy to .env and fill in keys
├── generate_appraisal_core.py      ← YOU MUST ADD THIS (see Step 3)
├── db/
│   └── schema.sql                  ← Run this in Supabase SQL Editor
├── models/
│   └── schemas.py                  ← Pydantic request/response models
├── routers/
│   ├── orders.py                   ← POST /orders, webhook, status
│   ├── appraisers.py               ← Appraiser portal endpoints
│   └── auth.py                     ← Appraiser login/logout
└── services/
    ├── claude_service.py           ← Anthropic API (research + JSON)
    ├── generator.py                ← .docx report generation wrapper
    ├── storage.py                  ← Supabase Storage upload/download
    └── email.py                    ← Resend transactional email
```

---

## Step 1 — Supabase Setup

1. Go to [supabase.com](https://supabase.com) and create a new project
2. In your project: **SQL Editor → New Query**
3. Paste the entire contents of `db/schema.sql` and click **Run**
4. Go to **Storage → New Bucket**, name it `appraisal-reports`, set to **Private**
5. Go to **Authentication → Users** and create your appraiser account:
   - Click "Add User" and set their email + password
   - Copy the user's UUID
6. In SQL Editor, run this to link the Supabase Auth user to your appraisers table:
   ```sql
   UPDATE users SET id = '<paste-uuid-here>' WHERE email = 'appraiser@apprais-ai.com';
   ```
   *(or insert a new row with that UUID and role = 'appraiser')*
7. Copy your keys from **Settings → API**:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY` (public/anon key)
   - `SUPABASE_SERVICE_ROLE_KEY` (service role — keep secret!)

---

## Step 2 — Get Your API Keys

| Service | Where to get it |
|---------|----------------|
| **Anthropic** | console.anthropic.com → API Keys |
| **Stripe** | dashboard.stripe.com → Developers → API Keys |
| **Resend** | resend.com → API Keys |

For Stripe, also create a Webhook:
- Dashboard → Developers → Webhooks → Add endpoint
- URL: `https://your-backend.railway.app/orders/webhook`
- Event: `payment_intent.succeeded`
- Copy the **Signing Secret** → `STRIPE_WEBHOOK_SECRET`

---

## Step 3 — Add Your Appraisal Generation Script

The `services/generator.py` expects a file called `generate_appraisal_core.py` in the root of this folder.

**To create it:**
1. Take your existing `generate_appraisal.py` script
2. Copy it to `appraisai-backend/generate_appraisal_core.py`
3. **Delete everything from the top of the file down to (and including) the DATA SECTION** — all the lines that set `PROPERTY_ADDRESS = "..."`, `CITY = "..."`, etc.
4. Keep everything from the document-building code onward (the part that starts creating the `Document()`)
5. Make sure the script writes its output to the `OUTPUT_PATH` variable (which `generator.py` will inject)

The generator will inject all the data variables into the script's namespace before executing it.

---

## Step 4 — Configure Environment Variables

```bash
cp .env.example .env
```

Then edit `.env` and fill in all the values:

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...
ANTHROPIC_API_KEY=sk-ant-...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
RESEND_API_KEY=re_...
FROM_EMAIL=orders@apprais-ai.com
APP_URL=https://apprais-ai.com
FRONTEND_URL=https://apprais-ai.com
STORAGE_BUCKET=appraisal-reports
```

---

## Step 5 — Deploy to Railway

1. Go to [railway.app](https://railway.app) and create a new project
2. Click **"Deploy from GitHub repo"** and connect this folder
   - (Push the `appraisai-backend/` folder to a new GitHub repo first)
3. In Railway: **Variables** → add all your `.env` values
4. Railway will auto-detect Python and use the `Procfile` to start:
   ```
   web: uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
5. Copy your Railway app URL (e.g. `https://appraisai-backend.up.railway.app`)

---

## Step 6 — Update the Frontend

Open `apprais-ai.html` and update the two config values at the top of the `<script>` block:

```javascript
const API_BASE  = 'https://appraisai-backend.up.railway.app';  // ← your Railway URL
const STRIPE_PK = 'pk_live_your-publishable-key-here';          // ← Stripe publishable key
```

Then upload `apprais-ai.html` to your GoDaddy hosting (via File Manager or FTP) to replace the existing site.

---

## Step 7 — Test the Full Flow

1. Visit your site, click **Order Your Appraisal**, fill out the form
2. Use Stripe's test card: `4242 4242 4242 4242`, any future expiry, any CVC
3. After payment, check Railway logs — you should see Claude research starting
4. In about 60–120 seconds, check Supabase → `orders` table — status should change to `appraiser_review`
5. Log into the Appraiser Portal with the credentials you created in Step 1
6. Download the AI draft, review it, upload your certified version, click Certify
7. The client receives a delivery email with a download link

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/orders` | Submit new order |
| POST | `/orders/webhook` | Stripe payment webhook |
| GET | `/orders/{id}/status` | Poll order status |
| POST | `/auth/appraiser/login` | Appraiser sign in |
| POST | `/auth/appraiser/logout` | Appraiser sign out |
| GET | `/auth/appraiser/me` | Appraiser profile + stats |
| GET | `/appraisers/orders` | List assigned orders |
| GET | `/appraisers/orders/{id}` | Order + appraisal detail |
| GET | `/appraisers/orders/{id}/download-draft` | Signed URL for draft |
| POST | `/appraisers/orders/{id}/upload-certified` | Upload certified .docx |
| POST | `/appraisers/orders/{id}/certify` | Certify + deliver to client |
| POST | `/appraisers/orders/{id}/revision` | Flag for revision |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive API docs (Swagger) |

---

## Order Status Flow

```
pending → paid → ai_processing → appraiser_review → certified → delivered
                                         ↕
                                      revision
```

---

## Local Development

```bash
cd appraisai-backend
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn main:app --reload
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

For local Stripe webhooks, use the Stripe CLI:
```bash
stripe listen --forward-to localhost:8000/orders/webhook
```
