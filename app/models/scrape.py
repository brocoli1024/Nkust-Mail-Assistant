from sqlalchemy import Column, ForeignKey, Integer, String, Text
from app.models import Base


class Scrape(Base):
    __tablename__ = 'announcement_scrapes'
    announcement_id = Column(Integer, ForeignKey('announcements.id', ondelete='CASCADE'), primary_key=True)
    status = Column(String, nullable=False)
    source_url = Column(Text)
    final_url = Column(Text)
    content_hash = Column(String)
    fetched_at = Column(String)
    attempted_at = Column(String, nullable=False)
    error = Column(String)
