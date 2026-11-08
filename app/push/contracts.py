from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool

class PushModel(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)

class Deadline(PushModel):
    kind: Literal['date','datetime']
    value: str = Field(max_length=64)
    confirmed: StrictBool
    basis: Literal['official','user']

class ReminderIntent(PushModel):
    todo_id: UUID
    source_ref: str = Field(max_length=8192)
    source_version: str = Field(max_length=64,pattern=r'^(?:[a-f0-9]{64})?$')
    client_revision: int = Field(strict=True,ge=1,le=2147483647)
    operation_id: UUID
    enabled: StrictBool
    deadline: Deadline|None=None
    remind_at: datetime|None=None

@dataclass(frozen=True)
class DeviceState:
    id: UUID
    epoch: UUID
    subscription_version: int
    expires_at: datetime

@dataclass(frozen=True)
class PublicRef:
    id: int
    source_ref: str
    title: str
    detail_path: str
    version: str

@dataclass(frozen=True)
class ReminderWindow:
    remind_at: datetime
    expires_at: datetime

@dataclass(frozen=True)
class MutationResult:
    server_revision: int
    client_revision: int
    status: str
