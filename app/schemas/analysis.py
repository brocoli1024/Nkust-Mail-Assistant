"""Strict output contract, shared by all providers."""
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal['課程', '選課', '獎學金', '競賽', '講座', '活動', '證照', 'TOEIC',
                   '實習', '徵才', '交換學生', '行政通知', '其他']


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    summary: str = Field(min_length=1, max_length=160)
    category: Category
    requires_action: bool | None
    action_evidence: str | None = Field(max_length=400)
    keywords: list[str] = Field(max_length=8)
    event_date: str | None
    deadline: str | None
    event_evidence: str | None = Field(max_length=400)
    deadline_evidence: str | None = Field(max_length=400)

    @field_validator('event_date', 'deadline')
    @classmethod
    def iso_date(cls, value):
        if value is not None:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError('Expected ISO calendar date')
            date.fromisoformat(value)
        return value

    @field_validator('keywords')
    @classmethod
    def short_keywords(cls, values):
        if any(not value.strip() or len(value) > 40 for value in values):
            raise ValueError('Invalid keyword')
        return list(dict.fromkeys(values))

    @field_validator('summary')
    @classmethod
    def nonblank_summary(cls, value):
        if not value.strip():
            raise ValueError('Empty summary')
        return value.strip()
