from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, UniqueConstraint, Date
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    total_xp = Column(Integer, default=0, nullable=False)
    display_name = Column(String(80), nullable=True)
    bio = Column(String(500), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    email = Column(String(254), unique=True, nullable=True)
    phone = Column(String(20), unique=True, nullable=True)
    player_birth_date = Column(Date, nullable=True)
    account_status = Column(String(30), default="active", nullable=False)
    guardian_managed = Column(Integer, default=0, nullable=False)
    role = Column(String(20), default="user", nullable=False)
    suspended = Column(Integer, default=0, nullable=False)
    staff_totp_secret = Column(Text, nullable=True)
    staff_totp_counter = Column(Integer, default=-1, nullable=False)

class LegalConsent(Base):
    __tablename__ = "legal_consents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    notice_snapshot = Column(Text, nullable=False)
    actor_type = Column(String(20), nullable=False)
    guardian_name = Column(String(150), nullable=True)
    guardian_birth_date = Column(Date, nullable=True)
    relationship = Column(String(50), nullable=True)
    child_assent = Column(Integer, default=0, nullable=False)
    accepted_at = Column(Float, nullable=False)
    withdrawn_at = Column(Float, nullable=True)

class GuardianInvite(Base):
    __tablename__ = "guardian_invites"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    guardian_email = Column(String(254), nullable=False)
    expires_at = Column(Float, nullable=False)
    created_at = Column(Float, nullable=False)
    used_at = Column(Float, nullable=True)

class LegalRequest(Base):
    __tablename__ = "legal_requests"
    reference = Column(String(24), primary_key=True)
    kind = Column(String(30), nullable=False)
    email = Column(String(254), nullable=False)
    name = Column(String(150), nullable=False)
    details = Column(Text, nullable=False)
    content_url = Column(String(500), nullable=True)
    created_at = Column(Float, nullable=False)
    status = Column(String(30), default="received", nullable=False)
    legal_version = Column(String(50), nullable=True)

class ContentAttestation(Base):
    __tablename__ = "content_attestations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    resource = Column(String(255), nullable=False)
    legal_version = Column(String(50), nullable=False)
    accepted_at = Column(Float, nullable=False)

class ExternalIdentity(Base):
    """Reserved for verified provider subject IDs; never link by email alone."""
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"), UniqueConstraint("user_id", "provider"))
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String(30), nullable=False)
    subject = Column(String(255), nullable=False)

class Token(Base):
    __tablename__ = "tokens"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(Float, nullable=False)
    staff_verified = Column(Integer, default=0, nullable=False)

class LoginBucket(Base):
    __tablename__ = "login_buckets"
    key = Column(String(64), primary_key=True)
    attempts = Column(Integer, nullable=False)
    expires_at = Column(Float, nullable=False, index=True)

class ImageReview(Base):
    __tablename__ = "image_reviews"
    image_url = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    scan = Column(Text, nullable=False)
    created_at = Column(Float, nullable=False)

class ContentReport(Base):
    __tablename__ = "content_reports"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String(40), nullable=False)
    details = Column(String(1000), nullable=False, default="")
    status = Column(String(20), default="open", nullable=False)
    created_at = Column(Float, nullable=False)

class ModerationAudit(Base):
    __tablename__ = "moderation_audits"
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(30), nullable=False)
    target = Column(String(255), nullable=False)
    reason = Column(String(1000), nullable=False)
    created_at = Column(Float, nullable=False)

class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False, default="")
    image_url = Column(String(255), nullable=False)
    answer = Column(String(200), nullable=False)
    moderation_status = Column(String(20), default="published", nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    radius_meters = Column(Integer, default=150, nullable=False)
    reward_xp = Column(Integer, default=50, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class Solve(Base):
    __tablename__ = "solves"
    __table_args__ = (UniqueConstraint("user_id", "case_id"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_hidden = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class Attempt(Base):
    __tablename__ = "attempts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    created_at = Column(Float, nullable=False)

class AnswerAlias(Base):
    __tablename__ = "answer_aliases"
    __table_args__ = (UniqueConstraint("case_id", "answer"),)
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    answer = Column(String(200), nullable=False)

class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "case_id"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)

class Notification(Base):
    __tablename__ = "notifications"
    event_key = Column(String(100), unique=True, nullable=False)
    id = Column(Integer, primary_key=True)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    kind = Column(String(20), nullable=False)
    is_read = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
