"""
Configuration management using environment variables
"""
import os  # ✅ Added import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from functools import lru_cache

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Instagram Automation SaaS"
    DEBUG: bool = False
    SECRET_KEY: str 
    
    # API URL
    API_URL: str = "http://localhost:8000"
    
    # Database
    DATABASE_URL: str
    DIRECT_DATABASE_URL: str
    
    # ✅ FIXED: Redis & Workers Configuration
    # Uses the Railway 'REDIS_URL' env variable. Falls back to localhost only for local dev.
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Workers (Celery)
    # Defaults to the REDIS_URL if specific Celery vars aren't set
    CELERY_BROKER_URL: Optional[str] = os.getenv("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND: Optional[str] = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
    
    # Meta/Instagram
    META_APP_ID: str
    META_APP_SECRET: str
    META_VERIFY_TOKEN: str
    INSTAGRAM_GRAPH_API_VERSION: str = "v18.0"
    INSTAGRAM_REDIRECT_URI: str = "https://dmtest-production.up.railway.app/api/instagram/callback"
    
    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Payment
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    
    # Trial & Subscription
    FREE_TRIAL_DAYS: int = 15
    PRO_PLAN_PRICE: float = 29.99
    
    # Rate Limiting
    INSTAGRAM_RATE_LIMIT_PER_HOUR: int = 200
    DM_RATE_LIMIT_PER_DAY: int = 100
    
    # CORS Origins
    # We keep this for reference, but main.py will use the regex now
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000", 
        "http://localhost:5173", 
        "https://app.dmrocket.co", 
        "https://dmrocket.co",
        "https://www.dmrocket.co"
    ]
    
    # Admin
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str
    
    # Affiliate
    AFFILIATE_COMMISSION_RATE: float = 0.30
    
    # Frontend URL
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Encryption
    ENCRYPTION_KEY: str
    
    model_config = SettingsConfigDict(
        env_file = (".env", "backend/.env"), 
        env_file_encoding = "utf-8",
        extra ="ignore",         
        case_sensitive = True
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()