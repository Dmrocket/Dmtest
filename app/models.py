"""
Database models for Instagram Automation SaaS
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import enum
from app.database import Base

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"

class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PAYMENT_FAILED = "payment_failed"

class MediaType(str, enum.Enum):
    POST = "post"
    REEL = "reel"
    STORY = "story"
    LIVE = "live"

class AutomationStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"

class DMStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"

class MessageContentType(str, enum.Enum):
    TEXT = "text"
    LINK = "link"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(Enum(UserRole), default=UserRole.USER)
    business_name = Column(String(255))
    country = Column(String(100))
    category = Column(String(100))

    # Instagram credentials (encrypted)
    instagram_user_id = Column(String(255), index=True)
    instagram_username = Column(String(255))
    encrypted_access_token = Column(Text)
    token_expires_at = Column(DateTime)
    
    # Subscription
    subscription_status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.TRIAL)
    trial_start_date = Column(DateTime, default=datetime.utcnow)
    trial_end_date = Column(DateTime)
    subscription_start_date = Column(DateTime)
    subscription_end_date = Column(DateTime)
    stripe_customer_id = Column(String(255), index=True)
    stripe_subscription_id = Column(String(255))
    
    # Referral
    referral_code = Column(String(50), unique=True, index=True)
    referred_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relationships
    automations = relationship("Automation", back_populates="user", cascade="all, delete-orphan")
    dm_logs = relationship("DMLog", back_populates="user", cascade="all, delete-orphan")
    
    # ✅ FIXED: Removed brackets inside the string for foreign_keys
    referrals = relationship("Referral", foreign_keys="Referral.referrer_id", back_populates="referrer")
    
    referred_by = relationship("User", remote_side=[id], foreign_keys=[referred_by_user_id])
    
    def is_subscription_active(self) -> bool:
        """Check if user has active subscription or trial"""
        if self.subscription_status == SubscriptionStatus.TRIAL:
            return datetime.utcnow() <= self.trial_end_date
        elif self.subscription_status == SubscriptionStatus.ACTIVE:
            return datetime.utcnow() <= self.subscription_end_date
        return False
    
    def can_use_automation(self) -> bool:
        """Check if user can use automation features"""
        return self.is_active and self.is_subscription_active()

class Automation(Base):
    __tablename__ = "automations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Target configuration
    name = Column(String(255), nullable=False)
    media_type = Column(Enum(MediaType), nullable=False)
    instagram_media_id = Column(String(255), index=True)  # Specific post/reel/story/live ID
    
    # Keyword configuration
    keywords = Column(JSON)  # List of keywords
    case_sensitive = Column(Boolean, default=False)
    
    # Message configuration
    message_type = Column(Enum(MessageContentType), default=MessageContentType.TEXT)
    message_text = Column(Text, nullable=False)
    message_media_url = Column(String(500))  # For images/videos/documents
    
    # Status
    status = Column(Enum(AutomationStatus), default=AutomationStatus.ACTIVE)
    
    # Statistics
    total_comments_processed = Column(Integer, default=0)
    total_dms_sent = Column(Integer, default=0)
    total_dms_failed = Column(Integer, default=0)
    total_dms_pending = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="automations")
    dm_logs = relationship("DMLog", back_populates="automation", cascade="all, delete-orphan")

class DMLog(Base):
    __tablename__ = "dm_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    automation_id = Column(Integer, ForeignKey("automations.id"), nullable=False, index=True)
    
    # Target user
    instagram_commenter_id = Column(String(255), nullable=False, index=True)
    instagram_commenter_username = Column(String(255))
    
    # Comment details
    comment_id = Column(String(255), index=True)
    comment_text = Column(Text)
    matched_keyword = Column(String(255))
    
    # DM details
    dm_status = Column(Enum(DMStatus), default=DMStatus.PENDING, index=True)
    message_sent = Column(Text)
    instagram_message_id = Column(String(255))
    
    # Error tracking
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    sent_at = Column(DateTime)
    failed_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="dm_logs")
    automation = relationship("Automation", back_populates="dm_logs")

class Referral(Base):
    __tablename__ = "referrals"
    
    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    referred_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Commission tracking
    is_paid_conversion = Column(Boolean, default=False)
    commission_amount = Column(Float, default=0.0)
    commission_paid = Column(Boolean, default=False)
    commission_paid_at = Column(DateTime)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals")
    referred_user = relationship("User", foreign_keys=[referred_user_id])

class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    webhook_type = Column(String(100), index=True)
    payload = Column(JSON)
    processed = Column(Boolean, default=False)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class RateLimitTracker(Base):
    __tablename__ = "rate_limit_trackers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)  # 'dm_send', 'api_call'
    count = Column(Integer, default=0)
    window_start = Column(DateTime, default=datetime.utcnow)
    window_end = Column(DateTime)