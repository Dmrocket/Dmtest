"""
Affiliate/Referral system routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List
from datetime import datetime

from app.database import get_db
from app.models import User, Referral, SubscriptionStatus
from app.auth.routes import get_current_active_user
from app.config import settings

router = APIRouter()

class ReferralStats(BaseModel):
    total_referrals: int
    paid_conversions: int
    total_commission: float
    pending_commission: float
    paid_commission: float

class ReferralDetail(BaseModel):
    id: int
    referred_user_email: str
    referred_user_name: str
    is_paid_conversion: bool
    commission_amount: float
    commission_paid: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.get("/referral-link")
async def get_referral_link(
    current_user: User = Depends(get_current_active_user)
):
    """Get user's unique referral link"""
    
    referral_link = f"{settings.FRONTEND_URL}/register?ref={current_user.referral_code}"
    
    return {
        "referral_code": current_user.referral_code,
        "referral_link": referral_link
    }

@router.get("/stats", response_model=ReferralStats)
async def get_referral_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get referral statistics and earnings"""
    
    # Get all referrals
    referrals = db.query(Referral).filter(
        Referral.referrer_id == current_user.id
    ).all()
    
    total_referrals = len(referrals)
    paid_conversions = sum(1 for r in referrals if r.is_paid_conversion)
    total_commission = sum(r.commission_amount for r in referrals)
    paid_commission = sum(r.commission_amount for r in referrals if r.commission_paid)
    pending_commission = total_commission - paid_commission
    
    return ReferralStats(
        total_referrals=total_referrals,
        paid_conversions=paid_conversions,
        total_commission=total_commission,
        pending_commission=pending_commission,
        paid_commission=paid_commission
    )

@router.get("/referrals", response_model=List[ReferralDetail])
async def get_referrals(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of all referrals"""
    
    referrals = db.query(Referral).filter(
        Referral.referrer_id == current_user.id
    ).order_by(Referral.created_at.desc()).all()
    
    result = []
    for referral in referrals:
        referred_user = referral.referred_user
        result.append(ReferralDetail(
            id=referral.id,
            referred_user_email=referred_user.email,
            referred_user_name=referred_user.full_name,
            is_paid_conversion=referral.is_paid_conversion,
            commission_amount=referral.commission_amount,
            commission_paid=referral.commission_paid,
            created_at=referral.created_at
        ))
    
    return result

@router.get("/commission-rate")
async def get_commission_rate():
    """Get affiliate commission rate"""
    
    return {
        "commission_rate": settings.AFFILIATE_COMMISSION_RATE,
        "commission_percentage": f"{settings.AFFILIATE_COMMISSION_RATE * 100}%",
        "plan_price": settings.PRO_PLAN_PRICE,
        "commission_per_sale": settings.PRO_PLAN_PRICE * settings.AFFILIATE_COMMISSION_RATE
    }

@router.get("/leaderboard")
async def get_affiliate_leaderboard(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get top affiliates leaderboard"""
    
    # Get top referrers by commission
    top_affiliates = db.query(
        User.id,
        User.full_name,
        func.count(Referral.id).label('total_referrals'),
        func.sum(Referral.commission_amount).label('total_commission')
    ).join(
        Referral, Referral.referrer_id == User.id
    ).group_by(
        User.id, User.full_name
    ).order_by(
        func.sum(Referral.commission_amount).desc()
    ).limit(limit).all()
    
    return [
        {
            "rank": idx + 1,
            "name": affiliate.full_name,
            "total_referrals": affiliate.total_referrals,
            "total_commission": float(affiliate.total_commission or 0)
        }
        for idx, affiliate in enumerate(top_affiliates)
    ]
