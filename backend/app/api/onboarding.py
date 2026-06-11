from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..ingest import service
from ..ingest.schemas import MasterProfile

router = APIRouter()


def _profile_or_404(db: Session, profile_id: str) -> models.Profile:
    profile = db.get(models.Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _built_from_out(db: Session, built_from: dict) -> dict[str, schemas.BuiltFromEntry]:
    out: dict[str, schemas.BuiltFromEntry] = {}
    for alias, doc_id in (built_from or {}).items():
        doc = db.get(models.Document, doc_id)
        out[alias] = schemas.BuiltFromEntry(
            doc_id=doc_id, filename=doc.filename if doc else "(deleted document)"
        )
    return out


@router.get("/onboarding", response_model=schemas.OnboardingOut)
def onboarding_status(profile_id: str, db: Session = Depends(get_db)):
    profile = _profile_or_404(db, profile_id)
    return schemas.OnboardingOut(**service.get_status(profile))


@router.post("/build", response_model=schemas.OnboardingOut, status_code=202)
def build_profile(profile_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    profile = _profile_or_404(db, profile_id)
    status = service.get_status(profile)["status"]
    if status in ("building", "refining"):
        raise HTTPException(status_code=409, detail=f"Already {status} — wait for it to finish.")
    extracted = (
        db.query(models.Document)
        .filter(models.Document.profile_id == profile_id, models.Document.status == "extracted")
        .count()
    )
    if extracted == 0:
        raise HTTPException(status_code=409, detail="No extracted documents yet — upload first.")
    service.mark_building(db, profile_id)
    background.add_task(service.build_profile, profile_id)
    return schemas.OnboardingOut(status="building")


@router.get("/profile", response_model=schemas.MasterProfileOut)
def get_master_profile(profile_id: str, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    row = service.latest_profile_row(db, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No master profile yet — build it first.")
    return schemas.MasterProfileOut(
        version=row.version,
        origin=row.origin,
        created_at=row.created_at,
        built_from=_built_from_out(db, row.built_from),
        body=row.body_json,
    )


@router.put("/profile", response_model=schemas.MasterProfileOut)
def edit_master_profile(
    profile_id: str, body: schemas.ProfileBodyIn, db: Session = Depends(get_db)
):
    _profile_or_404(db, profile_id)
    current = service.latest_profile_row(db, profile_id)
    if current is None:
        raise HTTPException(status_code=404, detail="No master profile yet — build it first.")
    try:
        validated = MasterProfile(**body.body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Profile doesn't match the schema: {exc}")
    row = models.MasterProfileRow(
        profile_id=profile_id,
        version=current.version + 1,
        origin="edit",
        body_json=validated.model_dump(),
        built_from=current.built_from,
    )
    db.add(row)
    db.commit()
    return schemas.MasterProfileOut(
        version=row.version,
        origin=row.origin,
        created_at=row.created_at,
        built_from=_built_from_out(db, row.built_from),
        body=row.body_json,
    )


@router.get("/questions", response_model=list[schemas.QuestionOut])
def list_questions(profile_id: str, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    rows = (
        db.query(models.InterviewQuestion)
        .filter(
            models.InterviewQuestion.profile_id == profile_id,
            models.InterviewQuestion.status.in_(["open", "answered", "applied"]),
        )
        .order_by(models.InterviewQuestion.created_at)
        .all()
    )
    return [
        schemas.QuestionOut(
            id=r.id,
            question=r.question,
            reason=r.reason,
            status=r.status,
            answer=r.answer,
            created_at=r.created_at,
        )
        for r in rows
    ]


def _question_or_404(db: Session, profile_id: str, question_id: str) -> models.InterviewQuestion:
    row = db.get(models.InterviewQuestion, question_id)
    if row is None or row.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Question not found")
    return row


@router.post("/questions/{question_id}/answer", response_model=schemas.QuestionOut)
def answer_question(
    profile_id: str, question_id: str, body: schemas.AnswerIn, db: Session = Depends(get_db)
):
    row = _question_or_404(db, profile_id, question_id)
    row.answer = body.answer.strip()
    row.status = "answered"
    row.answered_at = datetime.now(timezone.utc)
    db.commit()
    return schemas.QuestionOut(
        id=row.id,
        question=row.question,
        reason=row.reason,
        status=row.status,
        answer=row.answer,
        created_at=row.created_at,
    )


@router.post("/questions/{question_id}/skip", response_model=schemas.QuestionOut)
def skip_question(profile_id: str, question_id: str, db: Session = Depends(get_db)):
    row = _question_or_404(db, profile_id, question_id)
    row.status = "skipped"
    db.commit()
    return schemas.QuestionOut(
        id=row.id,
        question=row.question,
        reason=row.reason,
        status=row.status,
        answer=row.answer,
        created_at=row.created_at,
    )


@router.post("/notes", response_model=schemas.QuestionOut, status_code=201)
def add_note(profile_id: str, body: schemas.NoteIn, db: Session = Depends(get_db)):
    """Free-form extra context from the candidate, applied on the next refine."""
    _profile_or_404(db, profile_id)
    row = models.InterviewQuestion(
        profile_id=profile_id,
        question="Anything else you want on file?",
        reason="Volunteered by the candidate.",
        status="answered",
        answer=body.text.strip(),
        answered_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return schemas.QuestionOut(
        id=row.id,
        question=row.question,
        reason=row.reason,
        status=row.status,
        answer=row.answer,
        created_at=row.created_at,
    )


@router.post("/refine", response_model=schemas.OnboardingOut, status_code=202)
def refine(profile_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    profile = _profile_or_404(db, profile_id)
    status = service.get_status(profile)["status"]
    if status in ("building", "refining"):
        raise HTTPException(status_code=409, detail=f"Already {status} — wait for it to finish.")
    if service.latest_profile_row(db, profile_id) is None:
        raise HTTPException(status_code=409, detail="No master profile yet — build it first.")
    answered = (
        db.query(models.InterviewQuestion)
        .filter(
            models.InterviewQuestion.profile_id == profile_id,
            models.InterviewQuestion.status == "answered",
        )
        .count()
    )
    if answered == 0:
        raise HTTPException(status_code=409, detail="No answered questions to apply yet.")
    service.mark_refining(db, profile_id)
    background.add_task(service.refine_with_answers, profile_id)
    return schemas.OnboardingOut(status="refining")
