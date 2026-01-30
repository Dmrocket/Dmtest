"""
Automation management routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, case, cast, Date, desc
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime, timedelta

from app.database import get_db
from app.models import User, Automation, AutomationStatus, MediaType, MessageContentType, DMLog
from app.auth.routes import get_current_active_user

router = APIRouter()

# --- Pydantic Schemas ---

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

class DashboardStatsResponse(BaseModel):
    totalDMs: int
    totalComments: int
    activeAutomations: int
    totalAutomations: int
    replies: int
    conversionRate: float
    leadsCapture: int

# Schema for the new Leads endpoint
class LeadResponse(BaseModel):
    id: str
    name: str
    email: str
    source: str
    date: str
    status: str
    interactionCount: int

# --- Routes ---

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

@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get aggregated statistics for the user dashboard.
    """
    stats = db.query(
        func.sum(Automation.total_dms_sent),
        func.sum(Automation.total_comments_processed),
        func.count(Automation.id),
        func.sum(case((Automation.status == AutomationStatus.ACTIVE, 1), else_=0))
    ).filter(
        Automation.user_id == current_user.id
    ).first()
    
    total_dms = stats[0] or 0
    total_comments = stats[1] or 0
    total_automations = stats[2] or 0
    active_automations = stats[3] or 0
    
    # Calculate conversion rate (DMs / Comments)
    conversion_rate = 0.0
    if total_comments > 0:
        conversion_rate = round((total_dms / total_comments) * 100, 1)

    return {
        "totalDMs": total_dms,
        "totalComments": total_comments,
        "totalAutomations": total_automations,
        "activeAutomations": active_automations,
        "replies": int(total_dms * 0.15), # Estimated 15% reply rate
        "conversionRate": conversion_rate,
        "leadsCapture": total_comments # Treating unique commenters as leads
    }

# --- NEW LEADS ENDPOINT ---
@router.get("/leads", response_model=List[LeadResponse])
async def get_leads(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get list of unique leads captured from automation logs.
    Groups by username and calculates engagement status.
    """
    # 1. Query logs joined with user's automations
    # Group by username to get unique people
    results = db.query(
        DMLog.instagram_commenter_username,
        func.count(DMLog.id).label("interaction_count"),
        func.max(DMLog.created_at).label("last_active")
    ).join(Automation).filter(
        Automation.user_id == current_user.id
    ).group_by(
        DMLog.instagram_commenter_username
    ).order_by(
        # Fixed: Use SQL expression for descending sort instead of string label
        func.max(DMLog.created_at).desc()
    ).limit(100).all()

    leads = []
    for r in results:
        # Determine status based on interaction count
        count = r.interaction_count
        status_val = "hot" if count > 2 else "warm"
        
        # Safety check for username
        username = r.instagram_commenter_username or "Unknown User"
        
        # Safety check for date
        date_str = r.last_active.strftime("%Y-%m-%d") if r.last_active else datetime.utcnow().strftime("%Y-%m-%d")
        
        leads.append({
            "id": username,
            "name": username,
            "email": "Not captured", # Placeholder until email capture feature is live
            "source": "Instagram",
            "date": date_str,
            "status": status_val,
            "interactionCount": count
        })
        
    return leads

@router.get("/analytics/chart")
async def get_analytics_chart(
    days: int = 7,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get daily message volume for charts.
    """
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Query DMLogs joined with Automations to ensure we only get current user's data
    daily_stats = db.query(
        func.date(DMLog.created_at).label('day'),
        func.count(DMLog.id).label('dms')
    ).join(Automation).filter(
        Automation.user_id == current_user.id,
        DMLog.created_at >= start_date
    ).group_by(
        func.date(DMLog.created_at)
    ).all()
    
    result = []
    stats_map = {str(stat.day): stat.dms for stat in daily_stats}
    
    for i in range(days):
        date = (start_date + timedelta(days=i)).date()
        date_str = str(date)
        day_label = date.strftime("%a") 
        
        count = stats_map.get(date_str, 0)
        
        result.append({
            "day": day_label,
            "fullDate": date_str,
            "dms": count,
            "replies": int(count * 0.2), 
            "leads": count
        })
        
    return {
        "weekly": result,
        "monthly": result
    }

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
async def get_single_automation_stats(
    automation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get stats for a SINGLE automation"""
    
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