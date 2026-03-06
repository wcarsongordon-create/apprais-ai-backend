"""
AppraisAI — FastAPI Application Entry Point
=============================================
Run locally:   uvicorn main:app --reload
Deploy:        Railway / Render will run this automatically via Procfile or start command.
"""

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AppraisAI API",
    description="USPAP-compliant commercial appraisal generation platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS — allow your frontend domain + localhost for dev ─────────────────────
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://apprais-ai.com")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:5500",  # VS Code Live Server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from routers.orders     import router as orders_router
from routers.appraisers import router as appraisers_router
from routers.auth       import router as auth_router

app.include_router(orders_router)
app.include_router(appraisers_router)
app.include_router(auth_router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "AppraisAI API", "version": "1.0.0"}


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/", tags=["root"])
async def root():
    return {
        "message": "AppraisAI API — see /docs for endpoints",
        "docs": "/docs",
    }
