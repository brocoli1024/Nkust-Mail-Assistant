"""Action-card contracts; provenance and personal changes are distinct."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

class SourceSegment(Frozen):
    kind: Literal['title','excerpt','original','official_text']
    text: str

class SourceDocument(Frozen):
    kind: Literal['public','private','demo']
    source_ref: str
    title: str
    segments: tuple[SourceSegment,...]
    url: str | None = None
    anchor: datetime | None = None
    metadata: dict = Field(default_factory=dict)

class Evidence(Frozen):
    segment: int
    quote: str
    start: int
    end: int
    role: str | None = None
    year_inferred: bool = False

class CardField(Frozen):
    value: str | None = None
    state: Literal['supported','pending','user_confirmed','stale'] = 'pending'
    evidence: tuple[Evidence,...] = ()
    origin: str = 'rule'
    warnings: tuple[str,...] = ()

class ActionCard(Frozen):
    source: SourceDocument
    source_hash: str
    baseline_hash: str
    parser_version: str
    fields: dict[str,CardField]
    requires_action: bool | None = None
    deadline_kind: Literal['registration','application','submission','unknown'] = 'unknown'
    time_status: Literal['unparsed','not_provided','unknown'] = 'unknown'
    candidates: tuple[Evidence,...] = ()
    legacy: dict = Field(default_factory=dict)
    ai_references: tuple[dict,...] = ()
    warnings: tuple[str,...] = ()

class FieldPatch(Frozen):
    mode: Literal['inherit','value','pending']
    value: str | None = None
    quote: str | None = Field(default=None, max_length=2000)
    confirmed: StrictBool = False

class CorrectionPatch(Frozen):
    fields: dict[str,FieldPatch] = Field(default_factory=dict)
    action_decision: Literal['yes','no','unknown'] = 'unknown'
    deadline_kind: Literal['registration','application','submission','unknown'] = 'unknown'

    @model_validator(mode='after')
    def valid_fields(self):
        limits = {'summary':160,'action':1200,'audience':1200,'materials':1200,'deadline':10,'event_date':10}
        for name, change in self.fields.items():
            if name not in limits:
                raise ValueError('Unknown correction field')
            if change.mode != 'value':
                if change.value is not None or change.quote is not None or change.confirmed:
                    raise ValueError('Only value mode accepts content')
                continue
            if not change.value or not change.value.strip() or len(change.value) > limits[name]:
                raise ValueError('Invalid correction length')
            if name in ('deadline','event_date'):
                parsed = date.fromisoformat(change.value)
                if parsed.isoformat() != change.value or not change.confirmed:
                    raise ValueError('Confirm a complete ISO calendar date')
        return self
