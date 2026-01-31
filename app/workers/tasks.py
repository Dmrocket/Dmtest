import os
from celery import Celery
from celery.schedules import crontab
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import httpx
import logging

from app.config import settings
from app.database import SessionLocal
from app.models import (
    DMLog, DMStatus, User, Automation, AutomationStatus,
    SubscriptionStatus, RateLimitTracker, Referral
)
from app.auth.utils import decrypt_token
from app.instagram.service import InstagramAPIClient

logger = logging.getLogger(__name__)

# --- FIX: Use settings directly to ensure we get the Railway variable ---
redis_url = settings.REDIS_URL

# Initialize Celery
celery_app = Celery(
    "instagram_automation",
    broker=redis_url,
    backend=redis_url
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # Add connection retry to prevent startup crashes
    broker_connection_retry_on_startup=True
)

print(f"DEBUG: Celery Broker URL: {redis_url}")

def get_db_session():
    """Get database session for tasks"""
    return SessionLocal()

@celery_app.task(bind=True, max_retries=3)
def process_comment_and_send_dm(self, dm_log_id: int):
    """
    Process a comment and send DM to the commenter
    This is the core automation task
    """
    db = get_db_session()
    
    try:
        dm_log = db.query(DMLog).filter(DMLog.id == dm_log_id).first()
        if not dm_log:
            logger.error(f"DMLog {dm_log_id} not found")
            return
        
        user = dm_log.user
        automation = dm_log.automation
        
        # Check subscription status
        if not user.can_use_automation():
            dm_log.dm_status = DMStatus.FAILED
            dm_log.error_message = "Subscription expired"
            dm_log.failed_at = datetime.utcnow()
            automation.total_dms_failed += 1
            automation.total_dms_pending -= 1
            db.commit()
            return
        
        # Check rate limits
        if not check_rate_limit(user.id, "dm_send", db):
            # Retry later (in 1 hour)
            raise self.retry(countdown=3600)
        
        # Get access token
        if not user.encrypted_access_token:
            dm_log.dm_status = DMStatus.FAILED
            dm_log.error_message = "Instagram not connected"
            dm_log.failed_at = datetime.utcnow()
            automation.total_dms_failed += 1
            automation.total_dms_pending -= 1
            db.commit()
            return
        
        access_token = decrypt_token(user.encrypted_access_token)
        client = InstagramAPIClient(access_token)
        
        # Send DM
        try:
            # --- UPDATED CALL: Passing comment_id for Private Reply ---
            result = client.send_message(
                recipient_id=dm_log.instagram_commenter_id,
                message_text=dm_log.message_sent,
                media_url=automation.message_media_url,
                comment_id=dm_log.comment_id  # <--- CRITICAL FIX
            )
            
            # Update DM log
            dm_log.dm_status = DMStatus.SENT
            # Store the message ID from the response (can vary slightly in key name)
            dm_log.instagram_message_id = result.get("id") or result.get("message_id")
            dm_log.sent_at = datetime.utcnow()
            
            # Update automation stats
            automation.total_dms_sent += 1
            automation.total_dms_pending -= 1
            
            # Track rate limit
            track_rate_limit(user.id, "dm_send", db)
            
            logger.info(f"DM sent successfully: {dm_log_id}")
            
        except Exception as e:
            logger.error(f"Failed to send DM {dm_log_id}: {str(e)}")
            
            dm_log.dm_status = DMStatus.FAILED
            dm_log.error_message = str(e)
            dm_log.failed_at = datetime.utcnow()
            dm_log.retry_count += 1
            
            automation.total_dms_failed += 1
            automation.total_dms_pending -= 1
            
            # Retry if not max retries
            if dm_log.retry_count < 3:
                # Exponential backoff: 300s, 600s, etc.
                raise self.retry(countdown=300 * dm_log.retry_count, exc=e)
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Error processing DM log {dm_log_id}: {str(e)}")
        db.rollback()
        raise
    
    finally:
        db.close()

@celery_app.task
def subscribe_to_instagram_webhooks(user_id: int, automation_id: int):
    """Subscribe to Instagram webhooks for comment notifications"""
    db = get_db_session()
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.encrypted_access_token:
            return
        
        access_token = decrypt_token(user.encrypted_access_token)
        client = InstagramAPIClient(access_token)
        
        # Subscribe to webhooks
        success = client.subscribe_to_webhooks()
        
        if success:
            logger.info(f"Subscribed to webhooks for user {user_id}")
        else:
            logger.error(f"Failed to subscribe to webhooks for user {user_id}")
    
    except Exception as e:
        logger.error(f"Error subscribing to webhooks: {str(e)}")
    
    finally:
        db.close()

@celery_app.task
def check_expired_trials():
    """
    Cron job: Check for expired trials and disable automations
    Runs every hour
    """
    db = get_db_session()
    
    try:
        # Find users with expired trials
        expired_users = db.query(User).filter(
            User.subscription_status == SubscriptionStatus.TRIAL,
            User.trial_end_date <= datetime.utcnow(),
            User.is_active == True
        ).all()
        
        for user in expired_users:
            user.subscription_status = SubscriptionStatus.EXPIRED
            
            # Disable all automations
            automations = db.query(Automation).filter(
                Automation.user_id == user.id,
                Automation.status == AutomationStatus.ACTIVE
            ).all()
            
            for automation in automations:
                automation.status = AutomationStatus.DISABLED
            
            logger.info(f"Disabled automations for expired trial user {user.id}")
        
        db.commit()
        logger.info(f"Processed {len(expired_users)} expired trial users")
        
    except Exception as e:
        logger.error(f"Error checking expired trials: {str(e)}")
        db.rollback()
    
    finally:
        db.close()

@celery_app.task
def check_failed_payments():
    """
    Cron job: Check for failed payments and disable services
    Runs every 6 hours
    """
    db = get_db_session()
    
    try:
        # This would integrate with Stripe webhooks
        # For now, we check subscription_status
        
        failed_payment_users = db.query(User).filter(
            User.subscription_status == SubscriptionStatus.PAYMENT_FAILED,
            User.is_active == True
        ).all()
        
        for user in failed_payment_users:
            # Disable automations
            automations = db.query(Automation).filter(
                Automation.user_id == user.id,
                Automation.status == AutomationStatus.ACTIVE
            ).all()
            
            for automation in automations:
                automation.status = AutomationStatus.DISABLED
            
            logger.info(f"Disabled automations for failed payment user {user.id}")
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Error checking failed payments: {str(e)}")
        db.rollback()
    
    finally:
        db.close()

@celery_app.task
def process_affiliate_commissions():
    """
    Cron job: Process affiliate commissions for paid conversions
    Runs daily
    """
    db = get_db_session()
    
    try:
        # Find referrals where referred user has paid subscription
        referrals = db.query(Referral).filter(
            Referral.is_paid_conversion == False
        ).all()
        
        for referral in referrals:
            referred_user = referral.referred_user
            
            # Check if referred user has active paid subscription
            if referred_user.subscription_status == SubscriptionStatus.ACTIVE:
                # Calculate commission
                commission = settings.PRO_PLAN_PRICE * settings.AFFILIATE_COMMISSION_RATE
                
                referral.is_paid_conversion = True
                referral.commission_amount = commission
                
                logger.info(f"Processed commission for referral {referral.id}: ${commission}")
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Error processing affiliate commissions: {str(e)}")
        db.rollback()
    
    finally:
        db.close()

def check_rate_limit(user_id: int, action_type: str, db: Session) -> bool:
    """Check if user has exceeded rate limit"""
    now = datetime.utcnow()
    
    # Check daily DM limit
    if action_type == "dm_send":
        tracker = db.query(RateLimitTracker).filter(
            RateLimitTracker.user_id == user_id,
            RateLimitTracker.action_type == action_type,
            RateLimitTracker.window_end > now
        ).first()
        
        if tracker and tracker.count >= settings.DM_RATE_LIMIT_PER_DAY:
            return False
    
    return True

def track_rate_limit(user_id: int, action_type: str, db: Session):
    """Track rate limit usage"""
    now = datetime.utcnow()
    window_end = now + timedelta(days=1)
    
    tracker = db.query(RateLimitTracker).filter(
        RateLimitTracker.user_id == user_id,
        RateLimitTracker.action_type == action_type,
        RateLimitTracker.window_end > now
    ).first()
    
    if tracker:
        tracker.count += 1
    else:
        tracker = RateLimitTracker(
            user_id=user_id,
            action_type=action_type,
            count=1,
            window_start=now,
            window_end=window_end
        )
        db.add(tracker)
    
    db.commit()

# Configure periodic tasks
celery_app.conf.beat_schedule = {
    'check-expired-trials': {
        'task': 'app.workers.tasks.check_expired_trials',
        'schedule': crontab(minute=0),  # Every hour
    },
    'check-failed-payments': {
        'task': 'app.workers.tasks.check_failed_payments',
        'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
    },
    'process-affiliate-commissions': {
        'task': 'app.workers.tasks.process_affiliate_commissions',
        'schedule': crontab(minute=0, hour=2),  # Daily at 2 AM
    },
}

def start_background_workers():
    """Start background workers (called from main.py)"""
    logger.info("Background workers configured and ready")