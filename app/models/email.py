from sqlalchemy import CheckConstraint, Column, Integer, JSON, String, Text

from app.models import Base


class Email(Base):
    __tablename__ = 'emails'
    __table_args__ = (CheckConstraint("status IN ('failed', 'processed')"),)

    id = Column(Integer, primary_key=True)
    gmail_message_id = Column(String, nullable=False, unique=True)
    subject = Column(Text)
    sender = Column(Text)
    received_at = Column(String, index=True)
    html_body = Column(Text)
    text_body = Column(Text)
    status = Column(String, nullable=False)
    processed_at = Column(String)
    parser_version = Column(String)
    last_error = Column(Text)
    warnings = Column(JSON, nullable=False, default=list)
