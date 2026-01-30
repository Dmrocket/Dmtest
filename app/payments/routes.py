"""
Payment and subscription management with Stripe
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
import stripe
import hmac
import hashlib

from app.database import get_db
from app.models import User, SubscriptionStatus, Automation, AutomationStatus
from app.auth.routes import get_current_active_user
from app.config import settings

router = APIRouter()
stripe.api_key = settings.STRIPE_SECRET_KEY

class CheckoutSession(BaseModel):
    success_url: str
    cancel_url: str

class SubscriptionResponse(BaseModel):
    status: str
    current_period_end: datetime | None
    trial_end: datetime | None
    is_active: bool

@router.get("/subscription-status", response_model=SubscriptionResponse)
async def get_subscription_status(
    current_user: User = Depends(get_current_active_user)
):
    """Get current subscription status"""
    
    is_active = current_user.can_use_automation()
    
    return SubscriptionResponse(
        status=current_user.subscription_status.value,
        current_period_end=current_user.subscription_end_date,
        trial_end=current_user.trial_end_date,
        is_active=is_active
    )

@router.post("/create-checkout-session")
async def create_checkout_session(
    checkout_data: CheckoutSession,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create Stripe checkout session for subscription"""
    
    try:
        # Create or retrieve Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={
                    "user_id": current_user.id,
                    "full_name": current_user.full_name
                }
            )
            current_user.stripe_customer_id = customer.id
            db.commit()
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Instagram Automation Pro Plan',
                        'description': 'Monthly subscription for unlimited automations'
                    },
                    'unit_amount': int(settings.PRO_PLAN_PRICE * 100),  # Convert to cents
                    'recurring': {
                        'interval': 'month'
                    }
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url=checkout_data.success_url,
            cancel_url=checkout_data.cancel_url,
            metadata={
                'user_id': current_user.id
            }
        )
        
        return {
            "checkout_url": session.url,
            "session_id": session.id
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhook events"""
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session, db)
    
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        handle_successful_payment_renewal(invoice, db)
    
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        handle_failed_payment(invoice, db)
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        handle_subscription_cancelled(subscription, db)
    
    return {"status": "success"}

def handle_successful_payment(session: dict, db: Session):
    """Handle successful subscription payment"""
    user_id = int(session['metadata']['user_id'])
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        return
    
    # Update subscription
    user.subscription_status = SubscriptionStatus.ACTIVE
    user.subscription_start_date = datetime.utcnow()
    user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
    user.stripe_subscription_id = session.get('subscription')
    
    # Re-enable automations
    automations = db.query(Automation).filter(
        Automation.user_id == user.id,
        Automation.status == AutomationStatus.DISABLED
    ).all()
    
    for automation in automations:
        automation.status = AutomationStatus.ACTIVE
    
    # Update referral if exists
    from app.models import Referral
    referral = db.query(Referral).filter(
        Referral.referred_user_id == user.id,
        Referral.is_paid_conversion == False
    ).first()
    
    if referral:
        referral.is_paid_conversion = True
        referral.commission_amount = settings.PRO_PLAN_PRICE * settings.AFFILIATE_COMMISSION_RATE
    
    db.commit()

def handle_successful_payment_renewal(invoice: dict, db: Session):
    """Handle successful subscription renewal"""
    customer_id = invoice['customer']
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    
    if not user:
        return
    
    # Extend subscription
    user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
    user.subscription_status = SubscriptionStatus.ACTIVE
    
    db.commit()

def handle_failed_payment(invoice: dict, db: Session):
    """Handle failed payment"""
    customer_id = invoice['customer']
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    
    if not user:
        return
    
    user.subscription_status = SubscriptionStatus.PAYMENT_FAILED
    
    # Disable automations after grace period (3 days)
    if user.subscription_end_date and datetime.utcnow() > user.subscription_end_date + timedelta(days=3):
        automations = db.query(Automation).filter(
            Automation.user_id == user.id,
            Automation.status == AutomationStatus.ACTIVE
        ).all()
        
        for automation in automations:
            automation.status = AutomationStatus.DISABLED
    
    db.commit()

def handle_subscription_cancelled(subscription: dict, db: Session):
    """Handle subscription cancellation"""
    customer_id = subscription['customer']
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    
    if not user:
        return
    
    user.subscription_status = SubscriptionStatus.CANCELLED
    
    # Disable automations
    automations = db.query(Automation).filter(
        Automation.user_id == user.id,
        Automation.status == AutomationStatus.ACTIVE
    ).all()
    
    for automation in automations:
        automation.status = AutomationStatus.DISABLED
    
    db.commit()

@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cancel user's subscription"""
    
    if not current_user.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    
    try:
        stripe.Subscription.delete(current_user.stripe_subscription_id)
        
        current_user.subscription_status = SubscriptionStatus.CANCELLED
        db.commit()
        
        return {"message": "Subscription cancelled successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pricing")
async def get_pricing():
    """Get pricing information"""
    return {
        "trial_days": settings.FREE_TRIAL_DAYS,
        "pro_plan": {
            "price": settings.PRO_PLAN_PRICE,
            "currency": "USD",
            "interval": "month",
            "features": [
                "Unlimited automations",
                "All media types (Posts, Reels, Stories, Live)",
                "Custom messages with media",
                "Real-time analytics",
                "Priority support"
            ]
        }
    }
