import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import encrypt
from ..telegram import client, delivery, service

router = APIRouter()


class ConnectIn(BaseModel):
    token: str = Field(min_length=20)


class TelegramStateOut(BaseModel):
    connected: bool
    status: Optional[str] = None
    bot_username: Optional[str] = None
    link_url: Optional[str] = None
    linked_at: Optional[datetime] = None


def _profile_or_404(db: Session, profile_id: str) -> models.Profile:
    profile = db.get(models.Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _row(db: Session, profile_id: str) -> Optional[models.TelegramBot]:
    return (
        db.query(models.TelegramBot)
        .filter(models.TelegramBot.profile_id == profile_id)
        .one_or_none()
    )


def _state(bot: Optional[models.TelegramBot]) -> TelegramStateOut:
    if bot is None:
        return TelegramStateOut(connected=False)
    return TelegramStateOut(
        connected=bot.status == "linked",
        status=bot.status,
        bot_username=bot.bot_username,
        link_url=f"https://t.me/{bot.bot_username}?start={bot.link_code}"
        if bot.status == "pending"
        else None,
        linked_at=bot.linked_at,
    )


@router.get("/telegram", response_model=TelegramStateOut)
def get_state(profile_id: str, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    return _state(_row(db, profile_id))


@router.post("/telegram", response_model=TelegramStateOut)
def connect(profile_id: str, body: ConnectIn, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    token = body.token.strip()
    try:
        me = client.get_me(token)
    except client.TgError as exc:
        raise HTTPException(status_code=400, detail=f"Telegram rejected this token: {exc}")
    username = me.get("username") or me.get("first_name") or "bot"

    existing = _row(db, profile_id)
    if existing is not None:
        service.stop_listener(existing.id)
        db.delete(existing)
        db.flush()
    bot = models.TelegramBot(
        profile_id=profile_id,
        bot_token_enc=encrypt(token),
        bot_username=username,
        link_code=secrets.token_urlsafe(8)[:12],
    )
    db.add(bot)
    db.commit()
    service.start_listener(bot.id)
    return _state(bot)


@router.post("/telegram/test", response_model=dict)
def send_test(profile_id: str, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    sent = delivery.send_text(db, profile_id, "✅ JobScout test — this channel is connected.")
    if not sent:
        raise HTTPException(status_code=409, detail="Not linked yet — finish the /start step.")
    return {"sent": True}


@router.delete("/telegram", status_code=204)
def disconnect(profile_id: str, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    bot = _row(db, profile_id)
    if bot is not None:
        service.stop_listener(bot.id)
        db.delete(bot)
        db.commit()
