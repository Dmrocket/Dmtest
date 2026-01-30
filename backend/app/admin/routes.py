"""
Admin panel routes for system management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List

from app.database import get_db
from app.models import (
    User, UserRole, SubscriptionStatus, Automation, 
    DMLog, DMStatus, Referral, WebhookLog
)
from app.auth.routes import get_current_admin_user

router = APIRouter()

class AdminDashboard(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    trial_users: int
    paid_users: int
    failed_payment_users: int
    total_automations: int
    active_automations: int
    total_dms_sent: int
    total_dms_failed: int
    total_affiliate_revenue: float
    total_revenue: float

class UserDetail(BaseModel):
    id: int
    email: str
    full_name: str
    instagram_username: str | None
    subscription_status: str
    trial_end_date: datetime | None
    subscription_end_date: datetime | None
    is_active: bool
    created_at: datetime
    last_login: datetime | None
    total_automations: int
    
    class Config:
        from_attributes = True

class SystemHealth(BaseModel):
    database_status: str
    redis_status: str
    celery_status: str
    webhook_processing_rate: float
    last_webhook_processed: datetime | None

@router.get("/dashboard", response_model=AdminDashboard)
async def get_admin_dashboard(
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get admin dashboard metrics"""
    
    # User metrics
    total_users = db.query(func.count(User.id)).scalar()
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    inactive_users = total_users - active_users
    
    trial_users = db.query(func.count(User.id)).filter(
        User.subscription_status == SubscriptionStatus.TRIAL
    ).scalar()
    
    paid_users = db.query(func.count(User.id)).filter(
        User.subscription_status == SubscriptionStatus.ACTIVE
    ).scalar()
    
    failed_payment_users = db.query(func.count(User.id)).filter(
        User.subscription_status == SubscriptionStatus.PAYMENT_FAILED
    ).scalar()
    
    # Automation metrics
    total_automations = db.query(func.count(Automation.id)).scalar()
    active_automations = db.query(func.count(Automation.id)).filter(
        Automation.status == "active"
    ).scalar()
    
    # DM metrics
    total_dms_sent = db.query(func.count(DMLog.id)).filter(
        DMLog.dm_status == DMStatus.SENT
    ).scalar()
    
    total_dms_failed = db.query(func.count(DMLog.id)).filter(
        DMLog.dm_status == DMStatus.FAILED
    ).scalar()
    
    # Revenue metrics
    from app.config import settings
    total_affiliate_revenue = db.query(
        func.sum(Referral.commission_amount)
    ).scalar() or 0
    
    total_revenue = paid_users * settings.PRO_PLAN_PRICE
    
    return AdminDashboard(
        total_users=total_users,
        active_users=active_users,
        inactive_users=inactive_users,
        trial_users=trial_users,
        paid_users=paid_users,
        failed_payment_users=failed_payment_users,
        total_automations=total_automations,
        active_automations=active_automations,
        total_dms_sent=total_dms_sent or 0,
        total_dms_failed=total_dms_failed or 0,
        total_affiliate_revenue=float(total_affiliate_revenue),
        total_revenue=float(total_revenue)
    )

@router.get("/users", response_model=List[UserDetail])
async def get_all_users(
    skip: int = 0,
    limit: int = 50,
    subscription_status: str | None = None,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get all users with filtering"""
    
    query = db.query(User).filter(User.role != UserRole.ADMIN)
    
    if subscription_status:
        query = query.filter(User.subscription_status == subscription_status)
    
    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for user in users:
        automation_count = db.query(func.count(Automation.id)).filter(
            Automation.user_id == user.id
        ).scalar()
        
        result.append(UserDetail(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            instagram_username=user.instagram_username,
            subscription_status=user.subscription_status.value,
            trial_end_date=user.trial_end_date,
            subscription_end_date=user.subscription_end_date,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login,
            total_automations=automation_count
        ))
    
    return result

@router.get("/users/{user_id}")
async def get_user_details(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get detailed user information"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    automations = db.query(Automation).filter(Automation.user_id == user_id).all()
    
    dm_stats = {
        "sent": db.query(func.count(DMLog.id)).filter(
            DMLog.user_id == user_id,
            DMLog.dm_status == DMStatus.SENT
        ).scalar(),
        "failed": db.query(func.count(DMLog.id)).filter(
            DMLog.user_id == user_id,
            DMLog.dm_status == DMStatus.FAILED
        ).scalar(),
        "pending": db.query(func.count(DMLog.id)).filter(
            DMLog.user_id == user_id,
            DMLog.dm_status == DMStatus.PENDING
        ).scalar()
    }
    
    referral_stats = {
        "total_referrals": db.query(func.count(Referral.id)).filter(
            Referral.referrer_id == user_id
        ).scalar(),
        "paid_conversions": db.query(func.count(Referral.id)).filter(
            Referral.referrer_id == user_id,
            Referral.is_paid_conversion == True
        ).scalar()
    }
    
    return {
        "user": UserDetail(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            instagram_username=user.instagram_username,
            subscription_status=user.subscription_status.value,
            trial_end_date=user.trial_end_date,
            subscription_end_date=user.subscription_end_date,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login,
            total_automations=len(automations)
        ),
        "automations": [
            {
                "id": auto.id,
                "name": auto.name,
                "media_type": auto.media_type,
                "status": auto.status,
                "total_dms_sent": auto.total_dms_sent
            }
            for auto in automations
        ],
        "dm_stats": dm_stats,
        "referral_stats": referral_stats
    }

@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Suspend a user account"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Cannot suspend admin users")
    
    user.is_active = False
    
    # Disable automations
    db.query(Automation).filter(Automation.user_id == user_id).update(
        {"status": "disabled"}
    )
    
    db.commit()
    
    return {"message": "User suspended successfully"}

@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Activate a suspended user"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = True
    db.commit()
    
    return {"message": "User activated successfully"}

@router.post("/users/{user_id}/extend-trial")
async def extend_trial(
    user_id: int,
    days: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Extend user's trial period"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.subscription_status != SubscriptionStatus.TRIAL:
        raise HTTPException(status_code=400, detail="User is not on trial")
    
    user.trial_end_date = user.trial_end_date + timedelta(days=days)
    db.commit()
    
    return {
        "message": f"Trial extended by {days} days",
        "new_trial_end_date": user.trial_end_date
    }

@router.get("/system-health", response_model=SystemHealth)
async def get_system_health(
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get system health status"""
    
    # Check database
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except:
        db_status = "unhealthy"
    
    # Check webhook processing
    recent_webhooks = db.query(WebhookLog).filter(
        WebhookLog.created_at >= datetime.utcnow() - timedelta(hours=1)
    ).all()
    
    processed_webhooks = sum(1 for w in recent_webhooks if w.processed)
    processing_rate = (processed_webhooks / len(recent_webhooks) * 100) if recent_webhooks else 0
    
    last_webhook = db.query(WebhookLog).order_by(
        WebhookLog.created_at.desc()
    ).first()
    
    return SystemHealth(
        database_status=db_status,
        redis_status="healthy",  # Would check Redis connection
        celery_status="healthy",  # Would check Celery workers
        webhook_processing_rate=processing_rate,
        last_webhook_processed=last_webhook.created_at if last_webhook else None
    )

@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = 20,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get recent system activity"""
    
    recent_dms = db.query(DMLog).order_by(
        DMLog.created_at.desc()
    ).limit(limit).all()
    
    recent_users = db.query(User).order_by(
        User.created_at.desc()
    ).limit(10).all()
    
    return {
        "recent_dms": [
            {
                "id": dm.id,
                "user_email": dm.user.email,
                "status": dm.dm_status,
                "created_at": dm.created_at
            }
            for dm in recent_dms
        ],
        "recent_signups": [
            {
                "id": user.id,
                "email": user.email,
                "created_at": user.created_at
            }
            for user in recent_users
        ]
    }
