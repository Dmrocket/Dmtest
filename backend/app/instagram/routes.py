"""
Instagram API integration routes (Standard API)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx
from typing import List

from app.database import get_db
from app.models import User
from app.auth.routes import get_current_active_user
from app.auth.utils import decrypt_token
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
                    "callback_url": f"{settings.FRONTEND_URL}/api/webhooks/instagram",
                    "fields": "comments",
                    "verify_token": settings.META_VERIFY_TOKEN,
                    "access_token": self.access_token
                }
            )
            
            return response.status_code in [200, 201]

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