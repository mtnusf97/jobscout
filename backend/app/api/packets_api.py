from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import llm, models
from ..db import get_db
from ..engine import scoring, tailoring
from ..engine.util import canonical_url as canon_url
from ..engine.util import dedupe_key, jd_hash

router = APIRouter()


class TailorIn(BaseModel):
    notes: str = ""


class ActionIn(BaseModel):
    action: Literal["applied", "skip", "restore"]


class AdhocIn(BaseModel):
    text: str = Field(min_length=50)
    url: Optional[str] = None


class PacketOut(BaseModel):
    id: str
    version: int
    status: str
    created_at: datetime
    audit_passed: Optional[bool]
    audit_summary: Optional[str]
    audit_findings: list[dict[str, Any]]
    has_letter: bool
    cover_letter_hook: Optional[str]
    tailoring_notes: list[str]
    ats_missing: list[str]
    error: Optional[str]


def _job_or_404(db: Session, profile_id: str, job_id: str) -> models.Job:
    job = db.get(models.Job, job_id)
    if job is None or job.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _packet_out(packet: models.Packet) -> PacketOut:
    tailor = packet.tailor_json or {}
    audit = packet.audit_json or {}
    return PacketOut(
        id=packet.id,
        version=packet.version,
        status=packet.status,
        created_at=packet.created_at,
        audit_passed=audit.get("passed"),
        audit_summary=audit.get("summary"),
        audit_findings=audit.get("findings") or [],
        has_letter=bool(packet.letter_pdf),
        cover_letter_hook=(tailor.get("cover_letter") or {}).get("hook"),
        tailoring_notes=tailor.get("tailoring_notes") or [],
        ats_missing=(tailor.get("resume") or {}).get("ats_keywords_missing") or [],
        error=tailor.get("error"),
    )


@router.post("/jobs/{job_id}/tailor", response_model=dict, status_code=202)
def tailor(
    profile_id: str,
    job_id: str,
    background: BackgroundTasks,
    body: TailorIn = TailorIn(),
    db: Session = Depends(get_db),
):
    job = _job_or_404(db, profile_id, job_id)
    if job.status == "tailoring":
        raise HTTPException(status_code=409, detail="Already tailoring this job.")
    job.status = "tailoring"
    db.commit()
    background.add_task(tailoring.tailor_single, profile_id, job_id, body.notes.strip())
    return {"status": "tailoring"}


@router.get("/jobs/{job_id}/packet", response_model=PacketOut)
def get_packet(profile_id: str, job_id: str, db: Session = Depends(get_db)):
    _job_or_404(db, profile_id, job_id)
    packet = tailoring.latest_packet(db, job_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="No packet yet — tailor this job first.")
    return _packet_out(packet)


def _file_response(path: Optional[str]) -> FileResponse:
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="File not found — re-tailor to regenerate.")
    return FileResponse(path, media_type="application/pdf", filename=Path(path).name)


@router.get("/jobs/{job_id}/packet/resume.pdf")
def packet_resume(profile_id: str, job_id: str, db: Session = Depends(get_db)):
    _job_or_404(db, profile_id, job_id)
    packet = tailoring.latest_packet(db, job_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="No packet yet.")
    return _file_response(packet.resume_pdf)


@router.get("/jobs/{job_id}/packet/letter.pdf")
def packet_letter(profile_id: str, job_id: str, db: Session = Depends(get_db)):
    _job_or_404(db, profile_id, job_id)
    packet = tailoring.latest_packet(db, job_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="No packet yet.")
    return _file_response(packet.letter_pdf)


@router.post("/jobs/{job_id}/action", response_model=dict)
def job_action(profile_id: str, job_id: str, body: ActionIn, db: Session = Depends(get_db)):
    job = _job_or_404(db, profile_id, job_id)
    if body.action == "applied":
        job.status = "applied"
    elif body.action == "skip":
        job.status = "skipped"
    else:  # restore
        if tailoring.latest_packet(db, job_id) is not None:
            job.status = "tailored"
        elif (job.score_json or {}).get("recommend") == "apply":
            job.status = "shortlisted"
        else:
            job.status = "scored" if job.score is not None else "discovered"
    db.commit()
    return {"status": job.status}


# --- ad-hoc: paste a job, get a packet -----------------------------------------------


class AdhocMeta(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None


def _adhoc_chain(profile_id: str, job_id: str) -> None:
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        try:
            scoring.score_single(db, profile_id, job_id)
        except Exception:  # noqa: BLE001 - leave as discovered; user can score via pipeline
            db.rollback()
            return
    finally:
        db.close()
    tailoring.tailor_single(profile_id, job_id)


@router.post("/adhoc", response_model=dict, status_code=202)
def adhoc(
    profile_id: str,
    body: AdhocIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    profile = db.get(models.Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        client = llm.get_client(db)
        meta = llm.parse_call(
            client,
            model=llm.model_for(profile.settings_json, "scoring", scoring.MODEL_SCORE_DEFAULT),
            system=(
                "Extract the posting metadata from this pasted job description. "
                "Salary as annual integers only when explicitly stated."
            ),
            content=body.text[:14000],
            schema=AdhocMeta,
            max_tokens=1000,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=llm.friendly_llm_error(exc))

    url = body.url or f"manual:{jd_hash(body.text)[:16]}"
    job = models.Job(
        profile_id=profile_id,
        sources_json=["manual"],
        urls_json=[url],
        canonical_url=canon_url(url) if body.url else url,
        company=meta.company.strip()[:200],
        title=meta.title.strip()[:300],
        location=meta.location,
        salary_min=meta.salary_min,
        salary_max=meta.salary_max,
        salary_currency=meta.salary_currency,
        jd_text=body.text,
        jd_hash=jd_hash(body.text),
        dedupe_key=dedupe_key(meta.company, meta.title, meta.location),
    )
    db.add(job)
    db.commit()
    background.add_task(_adhoc_chain, profile_id, job.id)
    return {"job_id": job.id, "title": meta.title, "company": meta.company}
