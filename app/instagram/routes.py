"""
Instagram API integration routes (Standard API) & Business Login
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import httpx
from typing import List
from datetime import datetime, timedelta
import secrets
from urllib.parse import quote

from app.database import get_db
from app.models import User
from app.auth.routes import get_current_active_user, get_current_user
from app.auth.utils import decrypt_token, encrypt_token
from app.config import settings

router = APIRouter()

class InstagramAPIClient:
    """Instagram Graph API client"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = f"https://graph.instagram.com/{settings.INSTAGRAM_GRAPH_API_VERSION}"
    
    async def get_user_media(self, limit: int = 25):
        """Get user's media (posts, reels)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/me/media",
                params={
                    "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp",
                    "limit": limit,
                    "access_token": self.access_token
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch media")
            
            return response.json()
    
    async def send_message(self, recipient_id: str, message: str, media_url: str = None):
        """Send a direct message to a user"""
        async with httpx.AsyncClient() as client:
            # First, get the conversation or create one
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": message}
            }
            
            if media_url:
                # For media messages
                payload["message"] = {
                    "attachment": {
                        "type": "image",  # or video, file
                        "payload": {"url": media_url}
                    }
                }
            
            response = await client.post(
                f"{self.base_url}/me/messages",
                json=payload,
                params={"access_token": self.access_token}
            )
            
            if response.status_code not in [200, 201]:
                error_data = response.json()
                raise Exception(f"Failed to send message: {error_data}")
            
            return response.json()
    
    async def get_media_comments(self, media_id: str):
        """Get comments on a media"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/{media_id}/comments",
                params={
                    "fields": "id,text,username,timestamp",
                    "access_token": self.access_token
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch comments")
            
            return response.json()
    
    async def subscribe_to_webhooks(self, object_type: str = "instagram"):
        """Subscribe to Instagram webhooks"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_API_VERSION}/{settings.META_APP_ID}/subscriptions",
                data={
                    "object": object_type,
                    "callback_url": f"{settings.API_URL}/api/webhooks/instagram",
                    "fields": "comments",
                    "verify_token": settings.META_VERIFY_TOKEN,
                    "access_token": self.access_token
                }
            )
            
            return response.status_code in [200, 201]

# ============================================================================
# INSTAGRAM BUSINESS LOGIN FLOW (OAUTH)
# ============================================================================

@router.get("/auth-url")
async def get_instagram_auth_url(current_user: User = Depends(get_current_active_user)):
    """
    Step 1: Generate the Instagram Authorization URL.
    Called by Frontend to get the link the user should click.
    """
    # Create a state containing the user ID to identify them in the callback
    # In production, sign this state to prevent tampering
    state = f"{current_user.id}_{secrets.token_urlsafe(10)}"
    
    scope = (
        "instagram_business_basic,"
        "instagram_business_manage_messages,"
        "instagram_business_manage_comments,"
        "instagram_business_content_publish"
    )
    
    encoded_redirect_uri = quote(settings.INSTAGRAM_REDIRECT_URI, safe="")
    
    auth_url = (
        "https://www.instagram.com/oauth/authorize"
        "?response_type=code"
        f"&client_id={settings.META_APP_ID}"
        f"&redirect_uri={encoded_redirect_uri}"
        f"&scope={scope}"
        f"&state={state}"
        "&force_reauth=true"
    )
    
    return {"url": auth_url}

@router.get("/callback")
async def instagram_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """
    Step 2: Handle the redirect from Instagram.
    Exchange code for Short Token -> Long Token -> Update DB.
    """
    # 1. Validate State and User
    try:
        user_id_str = state.split("_")[0]
        user_id = int(user_id_str)
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard?error=user_not_found")
    except Exception:
        return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard?error=invalid_state")

    # Clean code parameter (Instagram appends #_)
    if code and code.endswith("#_"):
        code = code[:-2]

    async with httpx.AsyncClient() as client:
        # 2. Exchange Code for Short-Lived Token
        # Endpoint: https://api.instagram.com/oauth/access_token
        try:
            token_resp = await client.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": settings.META_APP_ID,
                    "client_secret": settings.META_APP_SECRET,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
                    "code": code,
                }
            )
            
            if token_resp.status_code != 200:
                print(f"Short Token Error: {token_resp.text}")
                return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard?error=auth_failed_short")

            data = token_resp.json()
            short_lived_token = data.get("access_token")
            # Note: user_id here is Instagram Scoped User ID
            ig_user_id = str(data.get("user_id")) 

        except Exception as e:
            print(f"Exception during token exchange: {str(e)}")
            return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard?error=server_error")

        # 3. Exchange Short-Lived Token for Long-Lived Token (60 Days)
        # Endpoint: https://graph.instagram.com/access_token
        try:
            long_lived_resp = await client.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": settings.META_APP_SECRET,
                    "access_token": short_lived_token
                }
            )
            
            if long_lived_resp.status_code != 200:
                 print(f"Long Token Error: {long_lived_resp.text}")
                 # Fallback to short lived if long fail (rare)
                 final_token = short_lived_token
                 expires_in = 3600 # 1 hour
            else:
                long_data = long_lived_resp.json()
                final_token = long_data.get("access_token")
                expires_in = long_data.get("expires_in") # seconds

        except Exception as e:
            print(f"Exception during long token exchange: {str(e)}")
            return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard?error=long_token_failed")

        # 4. Get User Profile (Username)
        # Endpoint: https://graph.instagram.com/me
        try:
            profile_resp = await client.get(
                f"https://graph.instagram.com/{settings.INSTAGRAM_GRAPH_API_VERSION}/me",
                params={
                    "fields": "id,username",
                    "access_token": final_token
                }
            )
            profile_data = profile_resp.json()
            username = profile_data.get("username")
        except Exception:
            username = "Unknown"

        # 5. Update Database
        user.instagram_user_id = ig_user_id
        user.instagram_username = username
        user.encrypted_access_token = encrypt_token(final_token)
        user.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        db.commit()

        # 6. Redirect to Frontend
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/dashboard?connected=true&username={username}"
        )

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/media")
async def get_instagram_media(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user's Instagram media"""
    
    if not current_user.instagram_user_id or not current_user.encrypted_access_token:
        raise HTTPException(status_code=400, detail="Instagram account not connected")
    
    access_token = decrypt_token(current_user.encrypted_access_token)
    client = InstagramAPIClient(access_token)
    
    try:
        media = await client.get_user_media()
        return media
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/media/{media_id}/comments")
async def get_media_comments(
    media_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get comments on specific media"""
    
    if not current_user.encrypted_access_token:
        raise HTTPException(status_code=400, detail="Instagram account not connected")
    
    access_token = decrypt_token(current_user.encrypted_access_token)
    client = InstagramAPIClient(access_token)
    
    try:
        comments = await client.get_media_comments(media_id)
        return comments
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/test-message")
async def send_test_message(
    recipient_id: str,
    message: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Send a test message (for testing purposes)"""
    
    if not current_user.encrypted_access_token:
        raise HTTPException(status_code=400, detail="Instagram account not connected")
    
    access_token = decrypt_token(current_user.encrypted_access_token)
    client = InstagramAPIClient(access_token)
    
    try:
        result = await client.send_message(recipient_id, message)
        return {"status": "sent", "result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/connection-status")
async def get_connection_status(
    current_user: User = Depends(get_current_active_user)
):
    """Check Instagram connection status"""
    
    return {
        "connected": bool(current_user.instagram_user_id),
        "username": current_user.instagram_username,
        "token_expires_at": current_user.token_expires_at
    }