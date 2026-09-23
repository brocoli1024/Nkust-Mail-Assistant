from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from app.models import Base


class Announcement(Base):
    __tablename__ = 'announcements'
    __table_args__ = (
        UniqueConstraint('email_id', 'source_index'),
        CheckConstraint('source_index >= 0'),
    )

    id = Column(Integer, primary_key=True)
    email_id = Column(Integer, ForeignKey('emails.id', ondelete='CASCADE'), nullable=False, index=True)
    source_index = Column(Integer, nullable=False)
    source_fingerprint = Column(String(64), nullable=False, index=True)
    announcement_date = Column(String)
    department = Column(Text, nullable=False)
    source_category = Column(Text, nullable=False)
    category = Column(String, index=True)
    title = Column(Text, nullable=False)
    original_text = Column(Text, nullable=False)
    original_html = Column(Text)
    summary = Column(Text)
    keywords = Column(JSON, nullable=False, default=list)
    url = Column(Text)
    event_date = Column(String, index=True)
    deadline = Column(String, index=True)
    requires_action = Column(Boolean)
    date_evidence = Column(JSON, nullable=False, default=list)
    date_inferred = Column(Boolean, nullable=False)
    scraped_text = Column(Text)
    analysis_status = Column(String, nullable=False, default='pending')
    analysis_version = Column(String)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
