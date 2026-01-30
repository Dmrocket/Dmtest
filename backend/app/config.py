"""
Configuration management using environment variables
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
from functools import lru_cache

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Instagram Automation SaaS"
    DEBUG: bool = False
    SECRET_KEY: str
    
    # Database
    DATABASE_URL: str
    DIRECT_DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Meta/Instagram
    META_APP_ID: str
    META_APP_SECRET: str
    META_VERIFY_TOKEN: str
    INSTAGRAM_GRAPH_API_VERSION: str = "v18.0"
    
    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Payment
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    
    # Trial & Subscription
    FREE_TRIAL_DAYS: int = 15
    PRO_PLAN_PRICE: float = 29.99
    
    # Rate Limiting (Instagram API)
    INSTAGRAM_RATE_LIMIT_PER_HOUR: int = 200
    DM_RATE_LIMIT_PER_DAY: int = 100
    
    # Workers
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # Admin
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str
    
    # Affiliate
    AFFILIATE_COMMISSION_RATE: float = 0.30  # 30%
    
    # Frontend URL
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Encryption
    ENCRYPTION_KEY: str  # Fernet key for token encryption
    
    model_config = SettingsConfigDict(
        env_file = "backend/.env",
        env_file_encoding = "utf-8",
        extra ="ignore",         # This stops the 'iDEBUG' crash!
        case_sensitive = True
    
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
