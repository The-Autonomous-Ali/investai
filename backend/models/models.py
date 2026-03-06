"""
SQLAlchemy database models for InvestAI
"""
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, 
    Text, JSON, ForeignKey, Enum as SAEnum, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import enum
import uuid

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────────────────────

class RiskTolerance(str, enum.Enum):
    CONSERVATIVE = "conservative"
    MODERATE     = "moderate"
    AGGRESSIVE   = "aggressive"

class SubscriptionTier(str, enum.Enum):
    FREE    = "free"
    STARTER = "starter"
    PRO     = "pro"
    ELITE   = "elite"

class SignalType(str, enum.Enum):
    GEOPOLITICAL = "geopolitical"
    MONETARY     = "monetary"
    FISCAL       = "fiscal"
    COMMODITY    = "commodity"
    CURRENCY     = "currency"
    CORPORATE    = "corporate"
    NATURAL      = "natural_disaster"

class SignalUrgency(str, enum.Enum):
    BREAKING    = "breaking"
    DEVELOPING  = "developing"
    LONG_TERM   = "long_term"

class EventStage(str, enum.Enum):
    WATCH         = "watch"
    ALERT         = "alert"
    ACTIVE        = "active"
    ESCALATING    = "escalating"
    DE_ESCALATING = "de_escalating"
    FADING        = "fading"
    RESOLVED      = "resolved"

class AdviceRating(str, enum.Enum):
    EXCELLENT = "excellent"
    GOOD      = "good"
    NEUTRAL   = "neutral"
    POOR      = "poor"
    BAD       = "bad"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id                  = Column(String, primary_key=True, default=gen_uuid)
    email               = Column(String, unique=True, nullable=False, index=True)
    name                = Column(String)
    avatar_url          = Column(String)
    google_id           = Column(String, unique=True, index=True)

    # Profile
    risk_tolerance      = Column(SAEnum(RiskTolerance), default=RiskTolerance.MODERATE)
    investment_horizon  = Column(String, default="1 year")
    monthly_income_bracket = Column(String)          # "5-10L", "10-25L", "25L+"
    tax_bracket         = Column(Integer, default=30) # percentage
    country             = Column(String, default="IN")
    state               = Column(String)              # for state-specific tax rules
    experience_level    = Column(String, default="intermediate")  # beginner/intermediate/expert

    # Preferences
    avoid_sectors       = Column(JSON, default=list)
    preferred_instruments = Column(JSON, default=list)  # ["mutual_funds", "etfs", "stocks"]
    notification_prefs  = Column(JSON, default=dict)

    # Connected sources
    linkedin_connected  = Column(Boolean, default=False)
    linkedin_token      = Column(Text)
    twitter_connected   = Column(Boolean, default=False)
    twitter_token       = Column(Text)

    # Subscription
    subscription_tier   = Column(SAEnum(SubscriptionTier), default=SubscriptionTier.FREE)
    subscription_expires = Column(DateTime)
    queries_used_this_month = Column(Integer, default=0)
    queries_reset_date  = Column(DateTime)

    # Timestamps
    created_at          = Column(DateTime, server_default=func.now())
    updated_at          = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_login          = Column(DateTime)

    # Relationships
    portfolio_items     = relationship("PortfolioItem", back_populates="user", cascade="all, delete-orphan")
    advice_history      = relationship("AdviceRecord", back_populates="user", cascade="all, delete-orphan")
    alerts              = relationship("UserAlert", back_populates="user", cascade="all, delete-orphan")


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"

    id           = Column(String, primary_key=True, default=gen_uuid)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    symbol       = Column(String, nullable=False)   # "ONGC", "NIFTYBEES"
    name         = Column(String, nullable=False)
    instrument_type = Column(String)                # "stock", "etf", "mutual_fund", "gold", "bond"
    quantity     = Column(Float)
    avg_buy_price = Column(Float)
    buy_date     = Column(DateTime)
    current_price = Column(Float)
    sector       = Column(String)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, server_default=func.now())
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user         = relationship("User", back_populates="portfolio_items")

    __table_args__ = (
        Index("ix_portfolio_user_symbol", "user_id", "symbol"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id                  = Column(String, primary_key=True, default=gen_uuid)
    title               = Column(String, nullable=False)
    content             = Column(Text)
    source              = Column(String)              # "rbi.org.in", "economictimes.com"
    source_agent        = Column(String)              # which agent found this
    source_tier         = Column(Integer)             # 1-4
    signal_type         = Column(SAEnum(SignalType))
    urgency             = Column(SAEnum(SignalUrgency))
    importance_score    = Column(Float)               # 0.0-10.0
    confidence          = Column(Float)               # 0.0-1.0
    geography           = Column(String)              # "global", "india", "regional"
    sentiment           = Column(String)              # "positive", "negative", "neutral"

    # Entities extracted
    entities_mentioned  = Column(JSON, default=list)  # ["Iran", "Oil", "Aviation"]
    sectors_affected    = Column(JSON, default=dict)  # {"aviation": "negative", "ongc": "positive"}

    # Second order effects
    india_impact_analysis = Column(Text)
    chain_effects       = Column(JSON, default=list)

    # Event lifecycle
    stage               = Column(SAEnum(EventStage), default=EventStage.WATCH)
    lifecycle_data      = Column(JSON, default=dict)
    resolution_conditions = Column(JSON, default=list)
    probability_scenarios = Column(JSON, default=dict)
    early_warning_signals = Column(JSON, default=dict)

    # Corroboration
    corroborated_by     = Column(JSON, default=list)
    corroboration_boost = Column(Float, default=0.0)
    final_weight        = Column(Float)

    # Deduplication
    content_hash        = Column(String, index=True)

    detected_at         = Column(DateTime, server_default=func.now())
    updated_at          = Column(DateTime, server_default=func.now(), onupdate=func.now())
    expires_at          = Column(DateTime)


class AdviceRecord(Base):
    __tablename__ = "advice_records"

    id                    = Column(String, primary_key=True, default=gen_uuid)
    user_id               = Column(String, ForeignKey("users.id"), nullable=False)

    # What triggered this advice
    triggering_signals    = Column(JSON, default=list)
    user_query            = Column(Text)

    # The advice itself
    allocation_plan       = Column(JSON)        # {"ONGC": {"pct": 15, "amount": 15000}, ...}
    sectors_to_buy        = Column(JSON, default=list)
    sectors_to_avoid      = Column(JSON, default=list)
    rebalancing_triggers  = Column(JSON, default=list)
    tax_optimizations     = Column(JSON, default=list)
    narrative             = Column(Text)         # human-readable explanation
    reasoning_chain       = Column(JSON)         # step by step reasoning
    confidence_score      = Column(Float)
    review_date           = Column(DateTime)     # when to reassess

    # Market conditions at time of advice
    market_snapshot       = Column(JSON)

    # Performance tracking
    performance_30d       = Column(JSON)
    performance_90d       = Column(JSON)
    performance_180d      = Column(JSON)
    advice_rating         = Column(SAEnum(AdviceRating))
    performance_notes     = Column(Text)

    # Critic agent output
    critic_verdict        = Column(String)       # "pass", "revise", "reject"
    critic_notes          = Column(Text)
    revision_count        = Column(Integer, default=0)

    created_at            = Column(DateTime, server_default=func.now())
    updated_at            = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user                  = relationship("User", back_populates="advice_history")

    __table_args__ = (
        Index("ix_advice_user_created", "user_id", "created_at"),
    )


class AgentPerformance(Base):
    __tablename__ = "agent_performance"

    id              = Column(String, primary_key=True, default=gen_uuid)
    agent_name      = Column(String, nullable=False, index=True)
    total_runs      = Column(Integer, default=0)
    successful_runs = Column(Integer, default=0)
    accuracy_rate   = Column(Float)
    avg_latency_ms  = Column(Float)
    signal_type_accuracy = Column(JSON, default=dict)  # {"monetary": 0.81, "geopolitical": 0.54}
    known_biases    = Column(JSON, default=dict)        # {"tends_to_be": "slightly_bearish"}
    last_calibration = Column(DateTime)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserAlert(Base):
    __tablename__ = "user_alerts"

    id          = Column(String, primary_key=True, default=gen_uuid)
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    signal_id   = Column(String, ForeignKey("signals.id"))
    alert_type  = Column(String)      # "new_signal", "stage_change", "portfolio_action"
    title       = Column(String)
    message     = Column(Text)
    severity    = Column(String)      # "info", "warning", "urgent"
    is_read     = Column(Boolean, default=False)
    action_required = Column(Boolean, default=False)
    created_at  = Column(DateTime, server_default=func.now())

    user        = relationship("User", back_populates="alerts")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id              = Column(String, primary_key=True, default=gen_uuid)
    user_id         = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    tier            = Column(SAEnum(SubscriptionTier), nullable=False)
    razorpay_sub_id = Column(String, unique=True)
    status          = Column(String)   # "active", "cancelled", "past_due"
    current_period_start = Column(DateTime)
    current_period_end   = Column(DateTime)
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())
