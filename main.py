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

# Routers
from app.auth.routes import router as auth_router
from app.automations.routes import router as automations_router
# FIXED: Added the missing import for instagram_router
from app.instagram.routes import router as instagram_router
# FIXED: Kept the webhook import (removed duplicate)
from app.instagram.webhooks import router as webhook_router 
from app.payments.routes import router as payments_router
from app.affiliates.routes import router as affiliates_router
from app.admin.routes import router as admin_router
from app.config import settings

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
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    settings.FRONTEND_URL,
    "https://dmrocket.co",
    "https://www.dmrocket.co",
    "https://app.dmrocket.co",
]
# Clean up null values from settings
origins = [o for o in origins if o]

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
        content={"detail": "An internal server error occurred. Our team has been notified."}
    )

# Standardized API Routes
# This router handles /api/webhooks/instagram (The one failing verification)
app.include_router(webhook_router, prefix="/api/webhooks", tags=["Webhooks"])

# This router handles /api/instagram/media, etc. (The one that caused NameError)
app.include_router(instagram_router, prefix="/api/instagram", tags=["Instagram"])

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