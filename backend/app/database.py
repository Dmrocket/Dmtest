from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool  # Add this import
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from app.config import settings

# Create database engine optimized for Supabase Pooler (Port 6543)
engine = create_engine(
    settings.DATABASE_URL,
    # 1. Use NullPool to delegate pooling to Supabase's Supavisor
    poolclass=NullPool,
    
    # 2. Disable prepared statements for Transaction Mode compatibility
    # For psycopg2 (synchronous), use connect_args to pass parameters
    connect_args={
        "options": "-c statement_timeout=30000", # Example safety timeout
    },
    
    # pool_pre_ping is still good for health checks
    pool_pre_ping=True, 
    echo=settings.DEBUG
)

# Note: pool_size and max_overflow are removed because NullPool ignores them

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
