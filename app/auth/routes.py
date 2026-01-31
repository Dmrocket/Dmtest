"""
Authentication routes and Instagram Native Business OAuth integration
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr, Field
import secrets
import logging
from app.database import get_db
from app.models import User, UserRole, SubscriptionStatus
from app.auth.utils import (
    hash_password, 
    verify_password, 
    create_access_token, 
    create_refresh_token,
    verify_token
)
from app.config import settings

# Initialize logging to capture auth failures in Railway
logger = logging.getLogger(__name__)

router = APIRouter()

# Using a more flexible tokenUrl to handle different deployment environments
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

# Pydantic schemas
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    full_name: str
    referral_code: str | None = None
    business_name: str | None = None
    country: str | None = None
    category: str | None = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    instagram_username: str | None
    subscription_status: str
    trial_end_date: datetime | None
    referral_code: str
    
    class Config:
        from_attributes = True

# Robust Dependency to get current user
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        logger.error("Auth Failure: No token provided in header")
        raise credentials_exception

    payload = verify_token(token)
    if payload is None:
        logger.error("Auth Failure: Token verification/decode failed (Secret mismatch?)")
        raise credentials_exception
    
    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        logger.error("Auth Failure: 'sub' claim missing from token payload")
        raise credentials_exception
    
    try:
        user_id = int(user_id_raw)
        user = db.query(User).filter(User.id == user_id).first()
    except (ValueError, TypeError):
        logger.error(f"Auth Failure: Invalid User ID format in token: {user_id_raw}")
        raise credentials_exception

    if user is None:
        logger.error(f"Auth Failure: User ID {user_id} not found in database")
        raise credentials_exception
    
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Register a new user"""
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    referred_by_user_id = None
    if user_data.referral_code:
        referrer = db.query(User).filter(User.referral_code == user_data.referral_code).first()
        if referrer:
            referred_by_user_id = referrer.id
    
    now = datetime.utcnow()
    trial_end = now + timedelta(days=settings.FREE_TRIAL_DAYS)
    new_user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        business_name=user_data.business_name,
        country=user_data.country,
        category=user_data.category,
        referral_code=secrets.token_urlsafe(8),
        referred_by_user_id=referred_by_user_id,
        trial_end_date=trial_end,
        subscription_status=SubscriptionStatus.TRIAL,
        last_login=now 
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    if referred_by_user_id:
        from app.models import Referral
        referral = Referral(referrer_id=referred_by_user_id, referred_user_id=new_user.id)
        db.add(referral)
        db.commit()
    
    access_token = create_access_token({"sub": str(new_user.id)})
    refresh_token = create_refresh_token({"sub": str(new_user.id)})
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login with email and password"""
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@router.post("/refresh")
async def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    payload = verify_token(refresh_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid user")
    
    return TokenResponse(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)})
    )