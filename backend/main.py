"""
Instagram Automation SaaS - FastAPI Backend
Main application entry point - Optimized for Stage 2 Scaling
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
from app.instagram.routes import router as instagram_router
from app.instagram.webhooks import router as webhook_router
from app.payments.routes import router as payments_router
from app.affiliates.routes import router as affiliates_router
from app.admin.routes import router as admin_router

from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Initializing Instagram Automation SaaS API...")
    
    # NOTE: Database tables are now managed by Alembic in the CI/CD pipeline.
    # We do NOT use create_all here to avoid race conditions.
    
    # NOTE: Background workers (Celery/Redis) are started as a separate 
    # service in Railway, not within the API process.
    
    yield
    logger.info("Shutting down Instagram Automation SaaS...")

app = FastAPI(
    title="Instagram Automation SaaS API",
    version="1.0.0",
    description="Production-ready Instagram comment-to-DM automation platform",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# Health & Root endpoints...

# Include routers
# CRITICAL: Webhooks are listed first for priority processing
app.include_router(webhook_router, prefix="/api/webhooks", tags=["Webhooks"])
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(automations_router, prefix="/api/automations", tags=["Automations"])
app.include_router(instagram_router, prefix="/api/instagram", tags=["Instagram"])
app.include_router(payments_router, prefix="/api/payments", tags=["Payments"])
app.include_router(affiliates_router, prefix="/api/affiliates", tags=["Affiliates"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        # In production (Stage 2), use a process manager like Gunicorn 
        # or handle scaling via Railway replicas instead of internal workers.
        workers=1 
    )
