from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str
    app: str
    version: str


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    settings: Optional[dict[str, Any]] = None


class ProfileOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    settings: dict[str, Any]


class CredentialStateOut(BaseModel):
    name: str
    label: str
    description: str
    help_url: str
    phase: int
    validation: Literal["live", "format"]
    is_set: bool
    masked_value: Optional[str]
    last_validated_at: Optional[datetime]


class CredentialSetIn(BaseModel):
    value: str = Field(min_length=1)


class CredentialResultOut(BaseModel):
    state: CredentialStateOut
    valid: bool
    message: str


class DocumentOut(BaseModel):
    id: str
    filename: str
    mime: str
    size_bytes: int
    status: str
    error: Optional[str]
    doc_type: Optional[str]
    uploaded_at: datetime
    processed_at: Optional[datetime]


class OnboardingOut(BaseModel):
    status: str
    error: Optional[str] = None


class BuiltFromEntry(BaseModel):
    doc_id: str
    filename: str


class MasterProfileOut(BaseModel):
    version: int
    origin: str
    created_at: datetime
    built_from: dict[str, BuiltFromEntry]
    body: dict[str, Any]


class ProfileBodyIn(BaseModel):
    body: dict[str, Any]


class QuestionOut(BaseModel):
    id: str
    question: str
    reason: Optional[str]
    status: str
    answer: Optional[str]
    created_at: datetime


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1)


class NoteIn(BaseModel):
    text: str = Field(min_length=1)
