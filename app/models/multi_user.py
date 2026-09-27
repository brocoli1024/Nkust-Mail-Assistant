"""Multi-user schema. Deliberately separate from the legacy Base metadata.

Do not import these tables into app.models.Base: the local app still owns its
original schema until the explicit, separately reviewed data import.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey,
    ForeignKeyConstraint, Index, Integer, JSON, MetaData, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class MultiUserBase(DeclarativeBase):
    metadata = MetaData(naming_convention={
        'ix': 'ix_%(table_name)s_%(column_0_name)s',
        'uq': 'uq_%(table_name)s_%(column_0_N_name)s',
        'ck': 'ck_%(table_name)s_%(constraint_name)s',
        'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
        'pk': 'pk_%(table_name)s',
    })


def utcnow():
    return datetime.now(timezone.utc)


class Timestamps:
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class User(Timestamps, MultiUserBase):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    google_user_id = Column(String(255), nullable=False, unique=True)
    email = Column(String(320), nullable=False)
    display_name = Column(Text)
    avatar_url = Column(Text)


class OAuthAttempt(MultiUserBase):
    """Short-lived authorization transaction, NOT an authenticated session."""
    __tablename__ = 'oauth_attempts'
    state_hash = Column(String(64), primary_key=True)
    browser_hash = Column(String(64), nullable=False)
    context_encrypted = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class WebSession(MultiUserBase):
    __tablename__ = 'web_sessions'
    id_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class SyncLease(MultiUserBase):
    __tablename__ = 'sync_leases'
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True, autoincrement=False)
    owner = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class OAuthAccount(Timestamps, MultiUserBase):
    __tablename__ = 'oauth_accounts'
    __table_args__ = (
        UniqueConstraint('provider', 'provider_user_id'),
        UniqueConstraint('user_id', 'provider'),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    provider_user_id = Column(String(255), nullable=False)
    access_token_encrypted = Column(Text)
    refresh_token_encrypted = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    scopes = Column(JSON, nullable=False, default=list)


class Email(MultiUserBase):
    __tablename__ = 'emails'
    __table_args__ = (
        UniqueConstraint('user_id', 'gmail_message_id'),
        UniqueConstraint('user_id', 'id'),
        CheckConstraint("status IN ('failed', 'processed')", name='status'),
        Index('ix_emails_user_received', 'user_id', 'received_at'),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    gmail_message_id = Column(String(255), nullable=False)
    subject = Column(Text)
    sender = Column(Text)
    received_at = Column(DateTime(timezone=True), index=True)
    html_body = Column(Text)
    text_body = Column(Text)
    status = Column(String(32), nullable=False)
    processed_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    parser_version = Column(String(255))
    warnings = Column(JSON, nullable=False, default=list)


class Announcement(Timestamps, MultiUserBase):
    __tablename__ = 'announcements'
    __table_args__ = (
        ForeignKeyConstraint(['user_id', 'email_id'], ['emails.user_id', 'emails.id'], ondelete='CASCADE'),
        UniqueConstraint('user_id', 'id'),
        UniqueConstraint('email_id', 'source_index'),
        CheckConstraint('source_index >= 0', name='source_index'),
        Index('ix_announcements_user_deadline', 'user_id', 'deadline'),
        Index('ix_announcements_user_category', 'user_id', 'category'),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    email_id = Column(Integer, nullable=False, index=True)
    source_index = Column(Integer, nullable=False)
    source_fingerprint = Column(String(64), nullable=False, index=True)
    announcement_date = Column(Date)
    department = Column(Text, nullable=False)
    source_category = Column(Text, nullable=False)
    category = Column(String(255), index=True)
    title = Column(Text, nullable=False)
    summary = Column(Text)
    original_text = Column(Text, nullable=False)
    original_html = Column(Text)
    url = Column(Text)
    event_date = Column(Date, index=True)
    deadline = Column(Date, index=True)
    requires_action = Column(Boolean)
    date_evidence = Column(JSON, nullable=False, default=list)
    date_inferred = Column(Boolean, nullable=False, default=False)
    # Preserve legacy data in the eventual import, without enabling AI/scrape.
    keywords = Column(JSON, nullable=False, default=list)
    scraped_text = Column(Text)
    analysis_status = Column(String(32), nullable=False, default='pending')
    analysis_version = Column(String(255))


class Analysis(MultiUserBase):
    __tablename__ = 'announcement_analyses'
    __table_args__ = (
        ForeignKeyConstraint(['user_id', 'announcement_id'],
                             ['announcements.user_id', 'announcements.id'], ondelete='CASCADE'),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    announcement_id = Column(Integer, nullable=False, index=True)
    input_hash = Column(String(64), nullable=False)
    provider = Column(String(255), nullable=False)
    model = Column(Text, nullable=False)
    version = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    result = Column(JSON)
    warnings = Column(JSON, nullable=False, default=list)
    error = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class Scrape(MultiUserBase):
    __tablename__ = 'announcement_scrapes'
    __table_args__ = (
        ForeignKeyConstraint(['user_id', 'announcement_id'],
                             ['announcements.user_id', 'announcements.id'], ondelete='CASCADE'),
    )
    announcement_id = Column(Integer, primary_key=True, autoincrement=False)
    user_id = Column(Integer, nullable=False, index=True)
    status = Column(String(32), nullable=False)
    source_url = Column(Text)
    final_url = Column(Text)
    content_hash = Column(String(64))
    fetched_at = Column(DateTime(timezone=True))
    attempted_at = Column(DateTime(timezone=True), nullable=False)
    error = Column(Text)
