import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Credential(Base):
    """An encrypted secret: instance-scoped (API keys) or profile-scoped (Telegram bot, later)."""

    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("scope", "profile_id", "name", name="uq_credentials_scope_profile_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(16), default="instance")  # instance | profile
    profile_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(64))
    value_enc: Mapped[bytes] = mapped_column(LargeBinary)
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Document(Base):
    """An uploaded source document (resume PDF, cover letter, notes, screenshot...)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="uploaded")
    # uploaded | processing | extracted | failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MasterProfileRow(Base):
    """A version of the merged master career profile. Append-only; latest version wins."""

    __tablename__ = "master_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(16), default="build")  # build | edit | interview
    body_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    built_from: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # alias -> doc id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    """A discovered job posting, deduped across sources, per profile."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE")
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sources_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    urls_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    canonical_url: Mapped[str] = mapped_column(String(800))
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    remote_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    salary_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    salary_is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    jd_text: Mapped[str] = mapped_column(Text, default="")
    jd_hash: Mapped[str] = mapped_column(String(64), default="")
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="discovered")
    # discovered | filtered_out | scored | shortlisted | tailored | sent | applied | skipped | expired
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)


class Run(Base):
    """One pipeline run (discovery now; scoring/tailoring fold in later phases)."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16), default="discovery")
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | done | failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stats_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    errors_json: Mapped[list[Any]] = mapped_column(JSON, default=list)


class Packet(Base):
    """A tailored application packet (resume + optional cover letter) for one job."""

    __tablename__ = "packets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("jobs.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="ready")
    # ready | audit_flagged | failed
    tailor_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    audit_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    resume_pdf: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    letter_pdf: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    retailor_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_msg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


class TelegramBot(Base):
    """Per-profile Telegram bot binding — token pasted in the UI, chat linked via /start."""

    __tablename__ = "telegram_bots"
    __table_args__ = (UniqueConstraint("profile_id", name="uq_telegram_bots_profile"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE")
    )
    bot_token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    bot_username: Mapped[str] = mapped_column(String(64))
    link_code: Mapped[str] = mapped_column(String(16))
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | linked
    linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Preference(Base):
    """A version of the structured job-search preferences. Append-only; latest wins."""

    __tablename__ = "preferences"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InterviewQuestion(Base):
    """A gap-interview question generated during merge, answered by the candidate."""

    __tablename__ = "interview_questions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE")
    )
    question: Mapped[str] = mapped_column(Text)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    # open | answered | skipped | applied | superseded
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
