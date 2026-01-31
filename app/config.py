"""
Configuration management using environment variables
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from functools import lru_cache

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Instagram Automation SaaS"
    DEBUG: bool = False
    SECRET_KEY: str # General app secret
    
    # API URL - REQUIRED for Instagram Callbacks
    # Set this to https://dmtest-production.up.railway.app in Railway
    API_URL: str = "http://localhost:8000"
    
    # Database (Alembic will use DIRECT_DATABASE_URL)
    DATABASE_URL: str
    DIRECT_DATABASE_URL: str
    
    # Redis
    REDIS_URL: str 
    
    # Meta/Instagram
    META_APP_ID: str
    META_APP_SECRET: str
    META_VERIFY_TOKEN: str
    INSTAGRAM_GRAPH_API_VERSION: str = "v18.0"
    
    # This must match exactly what you put in the Facebook App Dashboard
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
    
    # Rate Limiting (Instagram API)
    INSTAGRAM_RATE_LIMIT_PER_HOUR: int = 200
    DM_RATE_LIMIT_PER_DAY: int = 100
    
    
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "https://app.dmrocket.co", "https://dmrocket.co"]
    
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
def model_post_init(self, __context):
    if not self.REDIS_URL:
            raise RuntimeError("REDIS_URL is not set")

        # Automatically wire Celery to Redis
    self.CELERY_BROKER_URL = self.REDIS_URL
    self.CELERY_RESULT_BACKEND = self.REDIS_URL

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()