"""
Instagram webhook handlers for comment notifications
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
import hmac
import hashlib
import json

from app.database import get_db
from app.models import WebhookLog, Automation, DMLog, DMStatus, AutomationStatus
from app.config import settings

# This router handles requests at /api/webhooks/instagram
router = APIRouter()

@router.get("/instagram")
async def verify_webhook(request: Request):
    """
    Verify Instagram webhook subscription
    The 'Secret Handshake' required by Meta
    """
    # 1. Get parameters from query string
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    # 2. Verify the token matches your settings
    if mode == "subscribe" and token == settings.META_VERIFY_TOKEN:
        # CRITICAL FIX: Return raw text, not JSON or Integer
        # Meta will fail if you return int(challenge) or a JSON object
        return PlainTextResponse(content=challenge, status_code=200)
    
    # 3. Fail if token is wrong
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/instagram")
async def handle_instagram_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle incoming Instagram webhook notifications
    """
    
    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()
    
    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Log webhook
    webhook_log = WebhookLog(
        webhook_type="instagram_comment",
        payload=payload,
        processed=False
    )
    db.add(webhook_log)
    db.commit()
    
    # Process webhook entries
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "comments":
                    await process_comment_webhook(change["value"], db)
        
        webhook_log.processed = True
        db.commit()
        
    except Exception as e:
        webhook_log.error_message = str(e)
        db.commit()
        # We don't raise here to ensure we return 200 to Meta so they don't retry endlessly
        print(f"Error processing webhook: {str(e)}")
    
    return {"status": "received"}

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Instagram webhook signature"""
    if not signature.startswith("sha256="):
        return False
    
    expected_signature = hmac.new(
        settings.META_APP_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    received_signature = signature.split("sha256=")[1]
    
    return hmac.compare_digest(expected_signature, received_signature)

async def process_comment_webhook(value: dict, db: Session):
    """
    Process a comment webhook event
    Match against automations and queue DM sending
    """
    comment_id = value.get("id")
    comment_text = value.get("text", "")
    media_id = value.get("media", {}).get("id")
    commenter_id = value.get("from", {}).get("id")
    commenter_username = value.get("from", {}).get("username")
    
    if not all([comment_id, media_id, commenter_id]):
        return
    
    # Find matching automations
    automations = db.query(Automation).filter(
        Automation.instagram_media_id == media_id,
        Automation.status == AutomationStatus.ACTIVE
    ).all()
    
    for automation in automations:
        # Check if user can still use automation
        if not automation.user.can_use_automation():
            automation.status = AutomationStatus.DISABLED
            db.commit()
            continue
        
        # Check if comment matches keywords
        matched_keyword = check_keyword_match(
            comment_text,
            automation.keywords,
            automation.case_sensitive
        )
        
        if matched_keyword:
            # Check for duplicate (don't spam same user)
            existing_dm = db.query(DMLog).filter(
                DMLog.automation_id == automation.id,
                DMLog.instagram_commenter_id == commenter_id,
                DMLog.dm_status.in_([DMStatus.SENT, DMStatus.PENDING])
            ).first()
            
            if existing_dm:
                continue  # Skip duplicate
            
            # Create DM log
            dm_log = DMLog(
                user_id=automation.user_id,
                automation_id=automation.id,
                instagram_commenter_id=commenter_id,
                instagram_commenter_username=commenter_username,
                comment_id=comment_id,
                comment_text=comment_text,
                matched_keyword=matched_keyword,
                message_sent=automation.message_text,
                dm_status=DMStatus.PENDING
            )
            
            db.add(dm_log)
            
            # Update automation stats
            automation.total_comments_processed += 1
            automation.total_dms_pending += 1
            
            db.commit()
            db.refresh(dm_log)
            
            # Queue DM sending task
            from app.workers.tasks import process_comment_and_send_dm
            process_comment_and_send_dm.delay(dm_log.id)

def check_keyword_match(text: str, keywords: list, case_sensitive: bool) -> str | None:
    """
    Check if text contains any of the keywords
    Returns matched keyword or None
    """
    search_text = text if case_sensitive else text.lower()
    
    for keyword in keywords:
        search_keyword = keyword if case_sensitive else keyword.lower()
        if search_keyword in search_text:
            return keyword
    
    return None