from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from .. import llm, models, prefs
from ..db import get_db
from ..ingest import service

router = APIRouter()


class PreferencesOut(BaseModel):
    version: int
    raw_text: str
    structured: dict
    created_at: str


class ParseIn(BaseModel):
    raw_text: str = Field(min_length=10)


class EditIn(BaseModel):
    structured: dict


def _profile_or_404(db: Session, profile_id: str) -> models.Profile:
    profile = db.get(models.Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _latest(db: Session, profile_id: str) -> models.Preference | None:
    return (
        db.query(models.Preference)
        .filter(models.Preference.profile_id == profile_id)
        .order_by(models.Preference.version.desc())
        .first()
    )


def _out(row: models.Preference) -> PreferencesOut:
    return PreferencesOut(
        version=row.version,
        raw_text=row.raw_text,
        structured=row.structured_json,
        created_at=row.created_at.isoformat(),
    )


def _profile_context(db: Session, profile_id: str) -> dict:
    row = service.latest_profile_row(db, profile_id)
    if row is None:
        return {}
    body = row.body_json or {}
    auth_facts = [
        f.get("text")
        for f in body.get("other_facts", [])
        if isinstance(f, dict)
        and any(t in (f.get("text") or "").lower() for t in ("authoriz", "permit", "visa", "citizen"))
    ]
    return {
        "headline": body.get("headline"),
        "location": body.get("location"),
        "work_authorization": "; ".join(x for x in auth_facts if x) or None,
    }


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(profile_id: str, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    row = _latest(db, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No preferences yet — describe your target job first.")
    return _out(row)


@router.post("/preferences/parse", response_model=PreferencesOut)
def parse_preferences(profile_id: str, body: ParseIn, db: Session = Depends(get_db)):
    """Synchronous: turns the free-form description into structured preferences (~20-40s)."""
    _profile_or_404(db, profile_id)
    try:
        client = llm.get_client(db)
        parsed = prefs.parse_preferences(client, body.raw_text, _profile_context(db, profile_id))
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean API error
        raise HTTPException(status_code=502, detail=llm.friendly_llm_error(exc))
    latest = _latest(db, profile_id)
    row = models.Preference(
        profile_id=profile_id,
        version=(latest.version + 1) if latest else 1,
        raw_text=body.raw_text.strip(),
        structured_json=parsed.model_dump(),
    )
    db.add(row)
    db.commit()
    return _out(row)


@router.put("/preferences", response_model=PreferencesOut)
def edit_preferences(profile_id: str, body: EditIn, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    latest = _latest(db, profile_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No preferences yet — parse a description first.")
    try:
        validated = prefs.JobPreferences(**body.structured)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Preferences don't match the schema: {exc}")
    row = models.Preference(
        profile_id=profile_id,
        version=latest.version + 1,
        raw_text=latest.raw_text,
        structured_json=validated.model_dump(),
    )
    db.add(row)
    db.commit()
    return _out(row)
