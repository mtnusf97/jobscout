"""Onboarding orchestration: runs as FastAPI background tasks with their own DB sessions.

Status for long-running steps lives in profiles.settings_json["onboarding"]:
  {"status": "idle" | "building" | "refining" | "built" | "failed", "error": str | None}
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from .. import llm, models
from ..db import SessionLocal
from . import extract, merge


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_status(profile: models.Profile) -> dict[str, Any]:
    onboarding = (profile.settings_json or {}).get("onboarding") or {}
    return {"status": onboarding.get("status", "idle"), "error": onboarding.get("error")}


def _set_status(db: Session, profile_id: str, status: str, error: Optional[str] = None) -> None:
    profile = db.get(models.Profile, profile_id)
    if profile is None:
        return
    profile.settings_json = {
        **(profile.settings_json or {}),
        "onboarding": {"status": status, "error": error},
    }
    db.commit()


# --- extraction ------------------------------------------------------------------


def process_documents(doc_ids: list[str]) -> None:
    """Background task: extract facts from each uploaded document, sequentially."""
    db = SessionLocal()
    try:
        try:
            client = llm.get_client(db)
        except Exception as exc:
            for doc_id in doc_ids:
                doc = db.get(models.Document, doc_id)
                if doc is not None and doc.status in ("uploaded", "processing"):
                    doc.status = "failed"
                    doc.error = llm.short_error(exc)
            db.commit()
            return

        for doc_id in doc_ids:
            doc = db.get(models.Document, doc_id)
            if doc is None or doc.status not in ("uploaded", "processing"):
                continue
            doc.status = "processing"
            db.commit()
            try:
                facts = extract.extract_document(client, Path(doc.path), doc.mime, doc.filename)
                doc.extracted_json = facts.model_dump()
                doc.status = "extracted"
                doc.error = None
            except Exception as exc:  # noqa: BLE001 - surface every failure per-doc
                doc.status = "failed"
                doc.error = llm.short_error(exc)
            doc.processed_at = _utcnow()
            db.commit()
    finally:
        db.close()


# --- merge (build) ----------------------------------------------------------------


def latest_profile_row(db: Session, profile_id: str) -> Optional[models.MasterProfileRow]:
    return (
        db.query(models.MasterProfileRow)
        .filter(models.MasterProfileRow.profile_id == profile_id)
        .order_by(models.MasterProfileRow.version.desc())
        .first()
    )


def _next_version(db: Session, profile_id: str) -> int:
    row = latest_profile_row(db, profile_id)
    return (row.version + 1) if row is not None else 1


def build_profile(profile_id: str) -> None:
    """Background task: merge all extracted documents into a new master-profile version."""
    db = SessionLocal()
    try:
        try:
            client = llm.get_client(db)
            docs = (
                db.query(models.Document)
                .filter(
                    models.Document.profile_id == profile_id,
                    models.Document.status == "extracted",
                )
                .order_by(models.Document.uploaded_at)
                .all()
            )
            if not docs:
                raise RuntimeError("No extracted documents to merge.")

            alias_map: dict[str, str] = {}
            payloads: list[dict[str, Any]] = []
            for index, doc in enumerate(docs, start=1):
                alias = f"D{index}"
                alias_map[alias] = doc.id
                facts = doc.extracted_json or {}
                payloads.append(
                    {
                        "id": alias,
                        "filename": doc.filename,
                        "doc_type": facts.get("doc_type", "other"),
                        "facts": facts,
                    }
                )

            result = merge.merge_documents(client, payloads)

            row = models.MasterProfileRow(
                profile_id=profile_id,
                version=_next_version(db, profile_id),
                origin="build",
                body_json=result.profile.model_dump(),
                built_from=alias_map,
            )
            db.add(row)

            # Rebuild replaces the open question set; answered history is kept.
            db.query(models.InterviewQuestion).filter(
                models.InterviewQuestion.profile_id == profile_id,
                models.InterviewQuestion.status == "open",
            ).update({"status": "superseded"})
            for question in result.open_questions:
                db.add(
                    models.InterviewQuestion(
                        profile_id=profile_id,
                        question=question.question,
                        reason=question.reason,
                    )
                )
            db.commit()
            _set_status(db, profile_id, "built")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            _set_status(db, profile_id, "failed", llm.short_error(exc))
    finally:
        db.close()


# --- refine (interview answers) ----------------------------------------------------


def refine_with_answers(profile_id: str) -> None:
    """Background task: fold answered interview questions into a new profile version."""
    db = SessionLocal()
    try:
        try:
            client = llm.get_client(db)
            current = latest_profile_row(db, profile_id)
            if current is None:
                raise RuntimeError("No master profile yet — build it first.")
            questions = (
                db.query(models.InterviewQuestion)
                .filter(
                    models.InterviewQuestion.profile_id == profile_id,
                    models.InterviewQuestion.status == "answered",
                )
                .order_by(models.InterviewQuestion.created_at)
                .all()
            )
            if not questions:
                raise RuntimeError("No answered questions to apply.")

            answers = [{"question": q.question, "answer": q.answer or ""} for q in questions]
            result = merge.refine_profile(client, current.body_json, answers)

            row = models.MasterProfileRow(
                profile_id=profile_id,
                version=_next_version(db, profile_id),
                origin="interview",
                body_json=result.profile.model_dump(),
                built_from=current.built_from,
            )
            db.add(row)
            for question in questions:
                question.status = "applied"
            db.commit()
            _set_status(db, profile_id, "built")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            _set_status(db, profile_id, "failed", llm.short_error(exc))
    finally:
        db.close()


def mark_building(db: Session, profile_id: str) -> None:
    _set_status(db, profile_id, "building")


def mark_refining(db: Session, profile_id: str) -> None:
    _set_status(db, profile_id, "refining")


def recover_interrupted() -> None:
    """On startup: anything left mid-flight by a crash/restart becomes retryable.

    Background tasks die with the server (incl. uvicorn --reload restarts in dev);
    without this, documents sit in 'processing' forever and the UI polls endlessly.
    """
    db = SessionLocal()
    try:
        stuck_docs = (
            db.query(models.Document)
            .filter(models.Document.status.in_(["uploaded", "processing"]))
            .all()
        )
        for doc in stuck_docs:
            doc.status = "failed"
            doc.error = "Interrupted by a server restart — hit Retry."
        for profile in db.query(models.Profile).all():
            onboarding = (profile.settings_json or {}).get("onboarding") or {}
            if onboarding.get("status") in ("building", "refining"):
                profile.settings_json = {
                    **(profile.settings_json or {}),
                    "onboarding": {
                        "status": "failed",
                        "error": "Interrupted by a server restart — run it again.",
                    },
                }
        db.commit()
    finally:
        db.close()
