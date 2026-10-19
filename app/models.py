from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, UniqueConstraint
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

class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False, default="")
    image_url = Column(String(255), nullable=False)
    answer = Column(String(200), nullable=False)
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
