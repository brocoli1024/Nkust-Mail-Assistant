"""Analysis audit records; original announcement fields remain untouched."""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Text

from app.models import Base


class Analysis(Base):
    __tablename__ = 'announcement_analyses'
    id = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey('announcements.id', ondelete='CASCADE'), nullable=False, index=True)
    input_hash = Column(String(64), nullable=False)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    version = Column(String, nullable=False)
    status = Column(String, nullable=False)
    result = Column(JSON)
    warnings = Column(JSON, nullable=False, default=list)
    error = Column(Text)
    created_at = Column(String, nullable=False)
