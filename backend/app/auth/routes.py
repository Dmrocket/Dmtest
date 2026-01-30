"""
Authentication routes and Instagram OAuth integration
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr, Field
import secrets
import httpx

from app.database import get_db
from app.models import User, UserRole, SubscriptionStatus
from app.auth.utils import (
    hash_password, 
    verify_password, 
    create_access_token, 
    create_refresh_token,
    verify_token,
    encrypt_token,
    decrypt_token
)
from app.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

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

class InstagramAuthCallback(BaseModel):
    code: str
    state: str

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

# Dependency to get current user
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id: int = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
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
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Handle referral code
    referred_by_user_id = None
    if user_data.referral_code:
        referrer = db.query(User).filter(User.referral_code == user_data.referral_code).first()
        if referrer:
            referred_by_user_id = referrer.id
    
    # Create new user
    trial_end = datetime.utcnow() + timedelta(days=settings.FREE_TRIAL_DAYS)
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
        subscription_status=SubscriptionStatus.TRIAL

    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Create referral record if applicable
    if referred_by_user_id:
        from app.models import Referral
        referral = Referral(
            referrer_id=referred_by_user_id,
            referred_user_id=new_user.id
        )
        db.add(referral)
        db.commit()
    
    # Generate tokens
    access_token = create_access_token({"sub": new_user.id})
    refresh_token = create_refresh_token({"sub": new_user.id})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )

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
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Generate tokens
    access_token = create_access_token({"sub": user.id})
    refresh_token = create_refresh_token({"sub": user.id})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current user profile"""
    return current_user

@router.get("/instagram/auth-url")
async def get_instagram_auth_url(current_user: User = Depends(get_current_active_user)):
    """Get Instagram OAuth authorization URL"""
    
    state = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.INSTAGRAM_REDIRECT_URI}"
    
    # Instagram OAuth URL
    auth_url = (
        f"https://api.instagram.com/oauth/authorize"
        f"?client_id={settings.META_APP_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=instagram_basic,instagram_manage_messages,instagram_manage_comments"
        f"&response_type=code"
        f"&state={state}"
    )
    
    return {"auth_url": auth_url, "state": state}

@router.post("/instagram/callback")
async def instagram_callback(
    callback_data: InstagramAuthCallback,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Handle Instagram OAuth callback"""
    
    redirect_uri = f"{settings.INSTAGRAM_REDIRECT_URI}"
    
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.instagram.com/oauth/access_token",
            data={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": callback_data.code
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        user_id = token_data.get("user_id")
        
        # Get long-lived token
        long_lived_response = await client.get(
            f"https://graph.instagram.com/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": settings.META_APP_SECRET,
                "access_token": access_token
            }
        )
        
        if long_lived_response.status_code == 200:
            long_lived_data = long_lived_response.json()
            access_token = long_lived_data.get("access_token")
            expires_in = long_lived_data.get("expires_in", 5184000)  # 60 days default
        else:
            expires_in = 3600  # 1 hour for short-lived
        
        # Get user profile
        profile_response = await client.get(
            f"https://graph.instagram.com/me",
            params={
                "fields": "id,username",
                "access_token": access_token
            }
        )
        
        profile_data = profile_response.json()
        username = profile_data.get("username")
    
    # Encrypt and store token
    encrypted_token = encrypt_token(access_token)
    token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
    
    current_user.instagram_user_id = user_id
    current_user.instagram_username = username
    current_user.encrypted_access_token = encrypted_token
    current_user.token_expires_at = token_expiry
    
    db.commit()
    
    return {
        "message": "Instagram account connected successfully",
        "username": username
    }

@router.post("/refresh")
async def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    """Refresh access token"""
    
    payload = verify_token(refresh_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid user")
    
    # Generate new tokens
    new_access_token = create_access_token({"sub": user.id})
    new_refresh_token = create_refresh_token({"sub": user.id})
    
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token
    )
