"""
Authentication routes and Instagram OAuth integration
"""
from xmlrpc import client
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
    
    # Extract 'sub' and force to string for uniform processing
    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        logger.error("Auth Failure: 'sub' claim missing from token payload")
        raise credentials_exception
    
    try:
        # Convert to int for Postgres primary key lookup
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
    
    # Use string for sub to ensure JWT standard compliance
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
# INSTAGRAM BUSINESS LOGIN
# ============================================================================

@router.get("/facebook/login")
async def facebook_login():
    """
    Redirects user to the Facebook/Instagram Business Login flow.
    Fix: Use the Facebook OAuth Dialog endpoint for Business/Graph API support.
    """
    state = secrets.token_urlsafe(32)
    # Required scopes for DM automation and Page linking
    scope = (
        "public_profile,"
        "email,"
        "instagram_basic,"
        "instagram_manage_messages,"
        "instagram_manage_comments,"
        "pages_show_list,"
        "pages_read_engagement,"
        "pages_manage_metadata"
    )
    
    encoded_redirect_uri = quote(settings.FACEBOOK_REDIRECT_URI, safe="")

    # ✅ CORRECT ENDPOINT: For Business Apps, use the Facebook OAuth dialog.
    # This prevents the "Invalid platform app" error seen with instagram.com endpoints.
    auth_url = (
        "https://www.facebook.com/v19.0/dialog/oauth"
        f"?client_id={settings.META_APP_ID}"
        f"&redirect_uri={encoded_redirect_uri}"
        f"&state={state}"
        f"&scope={scope}"
        "&response_type=code"
    )

    return RedirectResponse(auth_url)
    

@router.get("/facebook/callback")
async def facebook_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    """
    Step 2: Facebook redirects here. 
    Exchange code for tokens and link the Instagram Business Account.
    """
    logger.info("Facebook/Instagram OAuth callback received")

    async with httpx.AsyncClient() as client:
        # 1️⃣ Exchange code → Short-Lived Access Token (1 hour)
        token_resp = await client.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
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
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "fb_exchange_token": short_lived_token
            }
        )
        
        long_lived_data = long_lived_resp.json()
        long_lived_token = long_lived_data.get("access_token", short_lived_token)

        # 3️⃣ Get Facebook Pages and find the connected Instagram Account
        # Optimize: Fetch accounts and their connected IG account in one call
        pages_resp = await client.get(
            "https://graph.facebook.com/v19.0/me/accounts",
            params={
                "fields": "name,access_token,connected_instagram_account{id,username}",
                "access_token": long_lived_token
            },
        )
        
        pages_data = pages_resp.json()
        pages = pages_data.get("data", []) 

        ig_user_id = None
        ig_username = None
        final_page_token = None

        # 4️⃣ Identify the linked Instagram account
        for page in pages:
            ig_account = page.get("connected_instagram_account")
            if ig_account:
                ig_user_id = ig_account.get("id")
                ig_username = ig_account.get("username")
                final_page_token = page.get("access_token")
                break 

        if not ig_user_id:
            logger.error("No Instagram Business account found linked to the user's Pages.")
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/dashboard?error=no_ig_account")

        # 5️⃣ Success! Redirect to frontend.
        # Ensure you include 'connected=true' and the account details
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