from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..engine.pipeline import run_pipeline

router = APIRouter()


class RunOut(BaseModel):
    id: str
    kind: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    stats: dict[str, Any]
    errors: list[Any]


class RunIn(BaseModel):
    kind: Literal["full", "discovery", "scoring", "tailoring"] = "full"


class PacketBrief(BaseModel):
    status: str
    version: int
    has_letter: bool
    audit_passed: Optional[bool]
    audit_flags: int


class JobItem(BaseModel):
    id: str
    company: str
    title: str
    location: Optional[str]
    remote_type: Optional[str]
    salary_min: Optional[int]
    salary_max: Optional[int]
    salary_currency: Optional[str]
    posted_at: Optional[datetime]
    first_seen_at: datetime
    sources: list[Any]
    url: str
    status: str
    score: Optional[int]
    recommend: Optional[str]
    rationale: Optional[str]
    salary_assessment: Optional[str]
    salary_estimate_min: Optional[int]
    salary_estimate_max: Optional[int]
    salary_estimate_currency: Optional[str]
    dealbreakers: list[str]
    matched: list[str]
    missing: list[str]
    packet: Optional[PacketBrief]


class JobDetail(JobItem):
    urls: list[Any]
    jd_text: str
    score_json: Optional[dict[str, Any]]


class JobsList(BaseModel):
    count: int
    items: list[JobItem]


def _profile_or_404(db: Session, profile_id: str) -> models.Profile:
    profile = db.get(models.Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _run_out(run: models.Run) -> RunOut:
    return RunOut(
        id=run.id,
        kind=run.kind,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stats=run.stats_json or {},
        errors=run.errors_json or [],
    )


def _packet_brief(packet: Optional[models.Packet]) -> Optional[PacketBrief]:
    if packet is None:
        return None
    audit = packet.audit_json or {}
    return PacketBrief(
        status=packet.status,
        version=packet.version,
        has_letter=bool(packet.letter_pdf),
        audit_passed=audit.get("passed"),
        audit_flags=len(audit.get("findings") or []),
    )


def _latest_packets(db: Session, job_ids: list[str]) -> dict[str, models.Packet]:
    if not job_ids:
        return {}
    rows = (
        db.query(models.Packet)
        .filter(models.Packet.job_id.in_(job_ids))
        .order_by(models.Packet.version)
        .all()
    )
    return {row.job_id: row for row in rows}  # ascending order → latest wins


def _job_item(job: models.Job, packet: Optional[models.Packet] = None) -> JobItem:
    verdict = job.score_json or {}
    return JobItem(
        id=job.id,
        company=job.company,
        title=job.title,
        location=job.location,
        remote_type=job.remote_type,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        sources=job.sources_json or [],
        url=job.canonical_url,
        status=job.status,
        score=job.score,
        recommend=verdict.get("recommend"),
        rationale=verdict.get("rationale"),
        salary_assessment=verdict.get("salary_assessment"),
        salary_estimate_min=verdict.get("salary_estimate_min"),
        salary_estimate_max=verdict.get("salary_estimate_max"),
        salary_estimate_currency=verdict.get("salary_estimate_currency"),
        dealbreakers=verdict.get("dealbreakers_triggered") or [],
        matched=verdict.get("matched_requirements") or [],
        missing=verdict.get("missing_requirements") or [],
        packet=_packet_brief(packet),
    )


@router.post("/runs", response_model=RunOut, status_code=202)
def start_run(
    profile_id: str,
    background: BackgroundTasks,
    body: RunIn = Body(default=RunIn()),
    db: Session = Depends(get_db),
):
    _profile_or_404(db, profile_id)
    active = (
        db.query(models.Run)
        .filter(models.Run.profile_id == profile_id, models.Run.status == "running")
        .first()
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="A run is already in progress.")
    has_prefs = (
        db.query(models.Preference).filter(models.Preference.profile_id == profile_id).count() > 0
    )
    if not has_prefs:
        raise HTTPException(status_code=409, detail="Set your job preferences first (card 4).")
    run = models.Run(profile_id=profile_id, kind=body.kind)
    db.add(run)
    db.commit()
    background.add_task(run_pipeline, profile_id, run.id, body.kind)
    return _run_out(run)


@router.get("/runs", response_model=list[RunOut])
def list_runs(profile_id: str, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    runs = (
        db.query(models.Run)
        .filter(models.Run.profile_id == profile_id)
        .order_by(models.Run.started_at.desc())
        .limit(10)
        .all()
    )
    return [_run_out(r) for r in runs]


@router.get("/jobs", response_model=JobsList)
def list_jobs(
    profile_id: str,
    limit: int = 100,
    offset: int = 0,
    sort: Literal["score", "new"] = "score",
    db: Session = Depends(get_db),
):
    _profile_or_404(db, profile_id)
    query = db.query(models.Job).filter(models.Job.profile_id == profile_id)
    count = query.count()
    order = (
        (models.Job.score.desc().nullslast(), models.Job.first_seen_at.desc(), models.Job.id)
        if sort == "score"
        else (models.Job.first_seen_at.desc(), models.Job.id)
    )
    rows = (
        query.order_by(*order)
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 200))
        .all()
    )
    packets = _latest_packets(db, [r.id for r in rows])
    return JobsList(count=count, items=[_job_item(r, packets.get(r.id)) for r in rows])


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(profile_id: str, job_id: str, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if job is None or job.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Job not found")
    base = _job_item(job, _latest_packets(db, [job.id]).get(job.id))
    return JobDetail(
        **base.model_dump(),
        urls=job.urls_json or [],
        jd_text=job.jd_text or "",
        score_json=job.score_json,
    )
