"""
Automation management routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime

from app.database import get_db
from app.models import User, Automation, AutomationStatus, MediaType, MessageContentType, DMLog, DMStatus
from app.auth.routes import get_current_active_user

router = APIRouter()

# Pydantic schemas
class AutomationCreate(BaseModel):
    name: str
    media_type: MediaType
    instagram_media_id: str
    keywords: List[str]
    case_sensitive: bool = False
    message_type: MessageContentType
    message_text: str
    message_media_url: str | None = None

class AutomationUpdate(BaseModel):
    name: str | None = None
    keywords: List[str] | None = None
    case_sensitive: bool | None = None
    message_text: str | None = None
    message_media_url: str | None = None
    status: AutomationStatus | None = None

class AutomationResponse(BaseModel):
    id: int
    name: str
    media_type: MediaType
    instagram_media_id: str
    keywords: List[str]
    case_sensitive: bool
    message_type: MessageContentType
    message_text: str
    message_media_url: str | None
    status: AutomationStatus
    total_comments_processed: int
    total_dms_sent: int
    total_dms_failed: int
    total_dms_pending: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class AutomationStats(BaseModel):
    successful_dms: int
    failed_dms: int
    pending_dms: int
    total_comments: int

@router.post("/", response_model=AutomationResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    automation_data: AutomationCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new automation"""
    
    # Check if user can use automation
    if not current_user.can_use_automation():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription required. Your trial has expired or payment is overdue."
        )
    
    # Check if user has connected Instagram
    if not current_user.instagram_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please connect your Instagram account first"
        )
    
    # Create automation
    automation = Automation(
        user_id=current_user.id,
        name=automation_data.name,
        media_type=automation_data.media_type,
        instagram_media_id=automation_data.instagram_media_id,
        keywords=automation_data.keywords,
        case_sensitive=automation_data.case_sensitive,
        message_type=automation_data.message_type,
        message_text=automation_data.message_text,
        message_media_url=automation_data.message_media_url,
        status=AutomationStatus.ACTIVE
    )
    
    db.add(automation)
    db.commit()
    db.refresh(automation)
    
    # Subscribe to webhooks for this media (handled by background worker)
    from app.workers.tasks import subscribe_to_instagram_webhooks
    subscribe_to_instagram_webhooks.delay(current_user.id, automation.id)
    
    return automation

@router.get("/", response_model=List[AutomationResponse])
async def get_automations(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all automations for current user"""
    
    automations = db.query(Automation).filter(
        Automation.user_id == current_user.id
    ).order_by(Automation.created_at.desc()).all()
    
    return automations

@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    automation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get specific automation"""
    
    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.user_id == current_user.id
    ).first()
    
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    return automation

@router.put("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    automation_id: int,
    update_data: AutomationUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update automation"""
    
    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.user_id == current_user.id
    ).first()
    
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(automation, field, value)
    
    automation.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(automation)
    
    return automation

@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete automation"""
    
    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.user_id == current_user.id
    ).first()
    
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    db.delete(automation)
    db.commit()
    
    return None

@router.post("/{automation_id}/pause")
async def pause_automation(
    automation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Pause automation"""
    
    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.user_id == current_user.id
    ).first()
    
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    automation.status = AutomationStatus.PAUSED
    automation.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "Automation paused"}

@router.post("/{automation_id}/resume")
async def resume_automation(
    automation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Resume automation"""
    
    # Check subscription
    if not current_user.can_use_automation():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription required to resume automation"
        )
    
    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.user_id == current_user.id
    ).first()
    
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    automation.status = AutomationStatus.ACTIVE
    automation.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "Automation resumed"}

@router.get("/{automation_id}/stats", response_model=AutomationStats)
async def get_automation_stats(
    automation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get automation statistics"""
    
    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.user_id == current_user.id
    ).first()
    
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    return AutomationStats(
        successful_dms=automation.total_dms_sent,
        failed_dms=automation.total_dms_failed,
        pending_dms=automation.total_dms_pending,
        total_comments=automation.total_comments_processed
    )

@router.get("/{automation_id}/logs")
async def get_automation_logs(
    automation_id: int,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get DM logs for automation"""
    
    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.user_id == current_user.id
    ).first()
    
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    logs = db.query(DMLog).filter(
        DMLog.automation_id == automation_id
    ).order_by(DMLog.created_at.desc()).limit(limit).offset(offset).all()
    
    return {
        "logs": [
            {
                "id": log.id,
                "commenter_username": log.instagram_commenter_username,
                "comment_text": log.comment_text,
                "matched_keyword": log.matched_keyword,
                "status": log.dm_status,
                "error_message": log.error_message,
                "created_at": log.created_at,
                "sent_at": log.sent_at
            }
            for log in logs
        ],
        "total": db.query(DMLog).filter(DMLog.automation_id == automation_id).count()
    }
