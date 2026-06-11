from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter()


def _out(profile: models.Profile) -> schemas.ProfileOut:
    return schemas.ProfileOut(
        id=profile.id,
        name=profile.name,
        created_at=profile.created_at,
        settings=profile.settings_json or {},
    )


def _get_or_404(db: Session, profile_id: str) -> models.Profile:
    profile = db.get(models.Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.get("", response_model=list[schemas.ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    rows = db.query(models.Profile).order_by(models.Profile.created_at).all()
    return [_out(row) for row in rows]


@router.post("", response_model=schemas.ProfileOut, status_code=201)
def create_profile(body: schemas.ProfileCreate, db: Session = Depends(get_db)):
    profile = models.Profile(name=body.name.strip())
    db.add(profile)
    db.commit()
    return _out(profile)


@router.get("/{profile_id}", response_model=schemas.ProfileOut)
def get_profile(profile_id: str, db: Session = Depends(get_db)):
    return _out(_get_or_404(db, profile_id))


@router.patch("/{profile_id}", response_model=schemas.ProfileOut)
def update_profile(profile_id: str, body: schemas.ProfileUpdate, db: Session = Depends(get_db)):
    profile = _get_or_404(db, profile_id)
    if body.name is not None:
        profile.name = body.name.strip()
    if body.settings is not None:
        profile.settings_json = body.settings
    db.commit()
    return _out(profile)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    profile = _get_or_404(db, profile_id)
    db.delete(profile)
    db.commit()
