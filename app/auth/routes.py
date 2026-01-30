"""
Authentication routes and Instagram Native Business OAuth integration
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr, Field
import secrets
import httpx
import logging
from urllib.parse import quote
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

# ============================================================================
# NATIVE INSTAGRAM BUSINESS LOGIN (FOR DM AUTOMATION)
# ============================================================================

@router.get("/facebook/login")
async def facebook_login():
    """
    Redirects user to the Native Instagram Login flow.
    Uses the modern Instagram Business Login protocol for native branding.
    """
    state = secrets.token_urlsafe(32)
    # Native scopes for Instagram Business Login
    scope = (
        "instagram_business_basic,"
        "instagram_business_manage_messages,"
        "instagram_business_manage_comments,"
        "instagram_business_content_publish"
    )
    
    encoded_redirect_uri = quote(settings.FACEBOOK_REDIRECT_URI, safe="")

    # ✅ FIXED ENDPOINT: Native Instagram Login
    auth_url = (
        "https://www.instagram.com/oauth/authorize"
        "?force_reauth=true"
        f"&client_id={settings.META_APP_ID}"
        f"&redirect_uri={encoded_redirect_uri}"
        "&response_type=code"
        f"&scope={scope}"
        f"&state={state}" 
    )

    return RedirectResponse(auth_url)
    

@router.get("/facebook/callback")
async def facebook_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    """
    Step 2: Instagram redirects here. 
    Exchanges code for a Long-Lived User Token and links the account.
    """
    logger.info("Instagram Native OAuth callback received")

    # Clean the code: Instagram appends '#_' which can break token exchange
    if code and code.endswith("#_"):
        code = code[:-2]

    async with httpx.AsyncClient() as client:
        # 1️⃣ Exchange code → Short-Lived Access Token (1 hour)
        # For Business Login, we hit the graph.instagram.com endpoint
        token_resp = await client.post(
            "https://api.instagram.com/oauth/access_token",
            data={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": settings.FACEBOOK_REDIRECT_URI,
                "code": code,
            },
        )

        token_data = token_resp.json()
        short_lived_token = token_data.get("access_token")

        if not short_lived_token:
            logger.error(f"Token exchange failed: {token_data}")
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/dashboard?connected=false&error=token_failed"
            )

        # 2️⃣ Exchange Short-Lived → Long-Lived Token (60 Days)
        long_lived_resp = await client.get(
            "https://graph.instagram.com/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": settings.META_APP_SECRET,
                "access_token": short_lived_token
            }
        )
        
        long_lived_data = long_lived_resp.json()
        long_lived_token = long_lived_data.get("access_token", short_lived_token)

        # 3️⃣ Fetch Instagram Account Info
        profile_resp = await client.get(
            "https://graph.instagram.com/v19.0/me",
            params={
                "fields": "id,username",
                "access_token": long_lived_token
            },
        )
        
        profile_data = profile_resp.json()
        ig_user_id = profile_data.get("id")
        ig_username = profile_data.get("username")

        if not ig_user_id:
            logger.error("Failed to retrieve Instagram ID from profile.")
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/dashboard?error=profile_failed")

        # 4️⃣ Success! Redirect to frontend
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/dashboard?connected=true&ig_username={ig_username}&ig_id={ig_user_id}"
        )

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