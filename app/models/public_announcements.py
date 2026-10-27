"""Public source records have no dependency on users, emails, or OAuth."""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, UniqueConstraint, CheckConstraint
from app.models.multi_user import MultiUserBase, utcnow


class PublicAnnouncement(MultiUserBase):
    __tablename__ = 'public_announcements'
    __table_args__ = (
        UniqueConstraint('source_key', 'canonical_url'),
        CheckConstraint("student_relevance IN ('relevant','not_student','unknown')", name='student_relevance'),
    )
    id = Column(Integer, primary_key=True)
    source_key = Column(String(64), nullable=False)
    canonical_url = Column(Text, nullable=False)
    external_id = Column(Text)
    title = Column(Text, nullable=False)
    published_at = Column(DateTime(timezone=True), index=True)
    excerpt = Column(Text, nullable=False, default='')
    category = Column(String(255), index=True)
    category_rule_version = Column(String(64))
    student_relevance = Column(String(32), nullable=False, default='unknown', index=True)
    student_reason = Column(JSON, nullable=False, default=list)
    student_rule_version = Column(String(64))
    content_hash = Column(String(64), nullable=False)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PublicSyncRun(MultiUserBase):
    __tablename__ = 'public_sync_runs'
    __table_args__ = (
        CheckConstraint("mode IN ('recent','history','reclassify')", name='mode'),
        CheckConstraint("status IN ('running','success','partial','failed')", name='status'),
    )
    id = Column(Integer, primary_key=True)
    source_key = Column(String(64), nullable=False)
    mode = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    added = Column(Integer, nullable=False, default=0)
    updated = Column(Integer, nullable=False, default=0)
    unchanged = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    error_code = Column(String(64))


class PublicSourceState(MultiUserBase):
    __tablename__ = 'public_source_states'
    __table_args__ = (
        CheckConstraint("history_status IN ('not_started','incomplete','complete')", name='history_status'),
        CheckConstraint('next_history_page >= 1', name='next_history_page'),
    )
    source_key = Column(String(64), primary_key=True)
    last_success_at = Column(DateTime(timezone=True))
    oldest_seen_at = Column(DateTime(timezone=True))
    next_history_page = Column(Integer, nullable=False, default=1)
    history_status = Column(String(32), nullable=False, default='not_started')
    history_completed_at = Column(DateTime(timezone=True))
    history_fingerprint = Column(String(64))
    lease_owner = Column(String(64))
    lease_expires_at = Column(DateTime(timezone=True))
