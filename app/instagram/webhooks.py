"""
Instagram webhook handlers for comment notifications, DMs, Story Replies, and Reactions
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

router = APIRouter()

# --- VERIFICATION ROUTE ---
@router.get("/instagram")
@router.get("/instagram/")
async def verify_webhook(request: Request):
    """
    Verify Instagram webhook subscription.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    # Secure check against settings
    AUTHORIZED = (token == settings.META_VERIFY_TOKEN)
    
    if mode == "subscribe" and AUTHORIZED:
        return PlainTextResponse(content=challenge, status_code=200)
    
    raise HTTPException(status_code=403, detail="Verification failed")

# --- NOTIFICATION ROUTE ---
@router.post("/instagram")
@router.post("/instagram/")
async def handle_instagram_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle incoming Instagram webhook notifications.
    Supports: Comments, DMs, Story Replies, Story Reactions.
    """
    # 1. Verify Request Signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()
    
    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # 2. Parse JSON
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # 3. Log webhook
    webhook_log = WebhookLog(
        webhook_type="instagram_event",
        payload=payload,
        processed=False
    )
    db.add(webhook_log)
    db.commit()
    
    # 4. Process Data
    try:
        for entry in payload.get("entry", []):
            
            # Case A: Messaging Events (DMs, Story Replies, Reactions)
            # These are typically found under 'messaging' list
            if "messaging" in entry:
                for event in entry["messaging"]:
                    await process_dm_event(event, db)

            # Case B: Change Events (Comments)
            # These are typically found under 'changes' list
            if "changes" in entry:
                for change in entry["changes"]:
                    if change.get("field") == "comments":
                        await process_comment_webhook(change["value"], db)
        
        webhook_log.processed = True
        db.commit()
        
    except Exception as e:
        webhook_log.error_message = str(e)
        db.commit()
        print(f"Error processing webhook: {str(e)}")
    
    return {"status": "received"}

# --- HELPER FUNCTIONS ---

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify that the request actually came from Facebook/Meta"""
    if not signature.startswith("sha256="):
        return False
    
    expected_signature = hmac.new(
        settings.META_APP_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    received_signature = signature.split("sha256=")[1]
    
    return hmac.compare_digest(expected_signature, received_signature)

async def process_dm_event(event: dict, db: Session):
    """
    Process Direct Messages, including Story Replies and Reactions
    """
    sender_id = event.get("sender", {}).get("id")
    recipient_id = event.get("recipient", {}).get("id")
    timestamp = event.get("timestamp")
    
    if not sender_id:
        return

    # 1. Handle "message" object (Standard DM or Story Reply)
    if "message" in event:
        message = event["message"]
        mid = message.get("mid")
        text = message.get("text", "")
        
        # Check for Story Reply
        if "reply_to" in message and "story" in message["reply_to"]:
            story_id = message["reply_to"]["story"]["id"]
            # Logic: Treat as a keyword match event or specific story trigger
            # await trigger_story_automation(sender_id, story_id, text, db)
            return

        # Check for normal Text DM
        if text:
            # Logic: Keyword matching for DM automation
            pass

    # 2. Handle "reaction"
    if "reaction" in event:
        reaction = event["reaction"]
        emoji = reaction.get("emoji")
        action = reaction.get("action") 
        pass

async def process_comment_webhook(value: dict, db: Session):
    """
    Process a comment webhook event
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
        if not automation.user.can_use_automation():
            automation.status = AutomationStatus.DISABLED
            db.commit()
            continue
        
        matched_keyword = check_keyword_match(
            comment_text,
            automation.keywords,
            automation.case_sensitive
        )
        
        if matched_keyword:
            existing_dm = db.query(DMLog).filter(
                DMLog.automation_id == automation.id,
                DMLog.instagram_commenter_id == commenter_id,
                DMLog.dm_status.in_([DMStatus.SENT, DMStatus.PENDING])
            ).first()
            
            if existing_dm:
                continue
            
            dm_log = DMLog(
                user_id=automation.user_id,
                automation_id=automation.id,
                instagram_commenter_id=commenter_id,
                instagram_commenter_username=commenter_username,
                # THIS IS THE CRITICAL FIELD NEEDED FOR PRIVATE REPLIES
                comment_id=comment_id, 
                comment_text=comment_text,
                matched_keyword=matched_keyword,
                message_sent=automation.message_text,
                dm_status=DMStatus.PENDING
            )
            
            db.add(dm_log)
            automation.total_comments_processed += 1
            automation.total_dms_pending += 1
            db.commit()
            db.refresh(dm_log)
            
            # Use delay() to send to Celery
            from app.workers.tasks import process_comment_and_send_dm
            process_comment_and_send_dm.delay(dm_log.id)

def check_keyword_match(text: str, keywords: list, case_sensitive: bool) -> str | None:
    search_text = text if case_sensitive else text.lower()
    for keyword in keywords:
        search_keyword = keyword if case_sensitive else keyword.lower()
        if search_keyword in search_text:
            return keyword
    return None