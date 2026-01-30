"""
Instagram Automation SaaS - FastAPI Backend
Main application entry point
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from datetime import datetime

# --- IMPORTS ---
from app.auth.routes import router as auth_router
from app.automations.routes import router as automations_router
from app.payments.routes import router as payments_router
from app.affiliates.routes import router as affiliates_router
from app.admin.routes import router as admin_router
from app.config import settings

# FIX 1: Import the standard Instagram API routes
from app.instagram.routes import router as instagram_router

# FIX 2: Import the Webhook routes (from the file we just fixed)
from app.instagram.webhooks import router as webhook_router 

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DMROCKET API BOOTING UP...")
    yield
    logger.info("DMROCKET API SHUTTING DOWN...")

app = FastAPI(title="DMRocket API", version="1.0.0", lifespan=lifespan)

# CORS Configuration
origins = ["*"] # Allow all for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handling
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Internal Server Error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500, 
        content={"detail": "An internal server error occurred."}
    )

# --- REGISTER ROUTERS ---

# 1. Webhooks Router
# Creates route: /api/webhooks/instagram (AND /api/webhooks/instagram/)
app.include_router(webhook_router, prefix="/api/webhooks", tags=["Webhooks"])

# 2. Instagram API Router
# Creates route: /api/instagram/media, etc.
app.include_router(instagram_router, prefix="/api/instagram", tags=["Instagram"])

# 3. Other Routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(automations_router, prefix="/api/automations", tags=["Automations"])
app.include_router(payments_router, prefix="/api/payments", tags=["Payments"])
app.include_router(affiliates_router, prefix="/api/affiliates", tags=["Affiliates"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])

@app.get("/health")
def health_check():
    """Service health verification endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@app.get("/")
def read_root():
    """API Root documentation link"""
    return {"message": "DMRocket API 🚀", "docs": "/docs", "status": "online"}