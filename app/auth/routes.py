"""
Authentication routes and Instagram Business OAuth integration
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
    verify_token
)
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

# ... (Keeping your Pydantic schemas and get_current_user dependencies exactly as they were) ...

# ============================================================================
# INSTAGRAM-BRANDED BUSINESS LOGIN
# ============================================================================

@router.get("/facebook/login")
async def facebook_login():
    """
    Redirects user to the Instagram Business Login flow.
    Fix: Uses the instagram.com/oauth/authorize endpoint for native branding.
    """
    state = secrets.token_urlsafe(32)
    
    # 🚀 2026 Native Instagram Scopes
    # These provide the "Instagram Look" while enabling DM automation
    scope = (
        "instagram_business_basic,"
        "instagram_business_manage_messages,"
        "instagram_business_manage_comments,"
        "instagram_business_content_publish"
    )
    
    encoded_redirect_uri = quote(settings.FACEBOOK_REDIRECT_URI, safe="")

    # ✅ USING THE INSTAGRAM.COM ENDPOINT
    # This forces the Instagram login UI instead of the Facebook dialog.
    auth_url = (
        "https://www.instagram.com/oauth/authorize"
        f"?client_id={settings.META_APP_ID}"
        f"&redirect_uri={encoded_redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&state={state}"
        "&force_reauth=true"
    )

    return RedirectResponse(auth_url)

@router.get("/facebook/callback")
async def facebook_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    Exchanges Instagram auth code for tokens.
    """
    logger.info("Instagram Business callback received.")

    async with httpx.AsyncClient() as client:
        # 1. Exchange code for Short-Lived Access Token
        # NOTE: Token exchange for Business Login still uses graph.facebook.com
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
        short_token = token_data.get("access_token")

        if not short_token:
            logger.error(f"Auth failed: {token_data}")
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/dashboard?error=auth_failed")

        # 2. Upgrade to Long-Lived Token (60 days)
        ll_resp = await client.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "fb_exchange_token": short_token
            }
        )
        ll_token = ll_resp.json().get("access_token", short_token)

        # 3. Fetch User Info
        # With Business Login, we can query /me directly for the IG account
        user_info_resp = await client.get(
            "https://graph.facebook.com/v19.0/me",
            params={"fields": "id,username", "access_token": ll_token}
        )
        user_info = user_info_resp.json()
        ig_username = user_info.get("username")
        ig_user_id = user_info.get("id")

        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/dashboard?connected=true&ig_username={ig_username}&ig_id={ig_user_id}"
        )