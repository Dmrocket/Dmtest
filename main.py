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

# FIXED: Import the actual webhook logic router, NOT just a placeholder
from app.instagram.webhooks import router as webhook_router 

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

# ✅ FIXED: Use settings.CORS_ORIGINS instead of ["*"]
# This is REQUIRED to make login work. Browsers block ["*"] when credentials are true.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTER ROUTERS ---

# 1. Webhooks (Priority)
# Mount at /api/webhooks. Since the router has /instagram, full path is /api/webhooks/instagram
app.include_router(webhook_router, prefix="/api/webhooks", tags=["Webhooks"])

# 2. Other Routers
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