"""
Instagram Automation SaaS - FastAPI Backend
Main application entry point
"""
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from contextlib import asynccontextmanager
import logging
from datetime import datetime

# --- IMPORTS ---
from app.auth.routes import router as auth_router
from app.automations.routes import router as automations_router
from app.payments.routes import router as payments_router
from app.affiliates.routes import router as affiliates_router
from app.admin.routes import router as admin_router
from app.instagram.routes import router as instagram_router
from app.config import settings

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DMROCKET API BOOTING UP...")
    yield
    logger.info("DMROCKET API SHUTTING DOWN...")

app = FastAPI(title="DMRocket API", version="1.0.0", lifespan=lifespan)

# CORS: Allow all for now to prevent frontend issues
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- NUCLEAR WEBHOOK VERIFICATION ---
# We handle this directly in main.py to prevent 404s
@app.get("/api/webhooks/instagram")
@app.get("/api/webhooks/instagram/")
async def verify_webhook_direct(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    # 1. Check Env Variable (Railway Variable)
    # 2. Check Hardcoded Backup
    AUTHORIZED = (token == os.getenv("META_VERIFY_TOKEN")) or (token == "DMRocket_Secure_2026")
    
    if mode == "subscribe" and AUTHORIZED:
        return PlainTextResponse(content=challenge, status_code=200)
    
    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/api/webhooks/instagram")
@app.post("/api/webhooks/instagram/")
async def handle_webhook_direct(request: Request):
    return {"status": "received"}
# ------------------------------------

# Register other routers
app.include_router(instagram_router, prefix="/api/instagram", tags=["Instagram"])
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(automations_router, prefix="/api/automations", tags=["Automations"])
app.include_router(payments_router, prefix="/api/payments", tags=["Payments"])
app.include_router(affiliates_router, prefix="/api/affiliates", tags=["Affiliates"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/")
def read_root():
    return {"message": "DMRocket API 🚀"}