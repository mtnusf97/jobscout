"""Outbound delivery: per-packet cards with documents + buttons, and run digests."""

from datetime import datetime, timezone
from typing import Optional

from .. import models
from ..security import decrypt
from . import client


def _linked_bot(db, profile_id: str) -> Optional[models.TelegramBot]:
    bot = (
        db.query(models.TelegramBot)
        .filter(models.TelegramBot.profile_id == profile_id)
        .one_or_none()
    )
    if bot is None or bot.status != "linked" or bot.chat_id is None:
        return None
    return bot


def _salary_line(job: models.Job) -> str:
    verdict = job.score_json or {}
    if job.salary_min or job.salary_max:
        amounts = "–".join(str(round(v / 1000)) + "k" for v in [job.salary_min, job.salary_max] if v)
        return f"💰 {amounts} {job.salary_currency or ''} (listed)"
    if verdict.get("salary_estimate_min"):
        amounts = "–".join(
            str(round(v / 1000)) + "k"
            for v in [verdict.get("salary_estimate_min"), verdict.get("salary_estimate_max")]
            if v
        )
        return f"💰 ~{amounts} {verdict.get('salary_estimate_currency') or ''} (estimated)"
    return ""


def _card_text(job: models.Job, packet: models.Packet) -> str:
    verdict = job.score_json or {}
    tailor = packet.tailor_json or {}
    audit = packet.audit_json or {}
    lines = [f"🎯 {job.score or '–'}/100 — {job.title} @ {job.company}"]
    location = " · ".join(x for x in [job.location, job.remote_type] if x)
    if location:
        lines.append(f"📍 {location}")
    salary = _salary_line(job)
    if salary:
        lines.append(salary)
    if verdict.get("rationale"):
        lines.append(f"\nWhy you fit: {verdict['rationale']}")
    hook = (tailor.get("cover_letter") or {}).get("hook")
    if hook:
        lines.append(f"✉️ Letter hook: {hook}")
    missing = (tailor.get("resume") or {}).get("ats_keywords_missing") or []
    if missing:
        lines.append(f"⚠️ JD asks you lack (not faked): {', '.join(missing[:5])}")
    if audit.get("passed"):
        lines.append("✅ Truthfulness audit passed.")
    elif audit:
        lines.append(f"⚠️ Audit flags: {len(audit.get('findings') or [])} — review before sending.")
    lines.append("📎 Resume + letter attached below.")
    return "\n".join(lines)


def _buttons(job: models.Job) -> dict:
    rows = []
    if job.canonical_url.startswith("http"):
        rows.append([{"text": "Open posting ↗", "url": job.canonical_url}])
    rows.append(
        [
            {"text": "✅ Applied", "callback_data": f"act:applied:{job.id}"},
            {"text": "❌ Skip", "callback_data": f"act:skip:{job.id}"},
            {"text": "🔁 Re-tailor", "callback_data": f"act:retailor:{job.id}"},
        ]
    )
    return {"inline_keyboard": rows}


def deliver_packet(db, packet: models.Packet) -> bool:
    """Send one packet card + documents. Best-effort; returns True when sent."""
    job = db.get(models.Job, packet.job_id)
    if job is None:
        return False
    bot = _linked_bot(db, job.profile_id)
    if bot is None or packet.delivered_at is not None or packet.status == "failed":
        return False
    token = decrypt(bot.bot_token_enc)
    message = client.send_message(token, bot.chat_id, _card_text(job, packet), _buttons(job))
    if packet.resume_pdf:
        client.send_document(token, bot.chat_id, packet.resume_pdf)
    if packet.letter_pdf:
        client.send_document(token, bot.chat_id, packet.letter_pdf)
    packet.telegram_msg_id = message.get("message_id")
    packet.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return True


def deliver_pending(db, profile_id: str, cap: int = 10) -> int:
    """Send undelivered ready packets (used right after linking, and after runs)."""
    if _linked_bot(db, profile_id) is None:
        return 0
    rows = (
        db.query(models.Packet)
        .join(models.Job, models.Job.id == models.Packet.job_id)
        .filter(
            models.Job.profile_id == profile_id,
            models.Packet.delivered_at.is_(None),
            models.Packet.status != "failed",
        )
        .order_by(models.Packet.created_at.desc())
        .limit(cap)
        .all()
    )
    sent = 0
    for packet in rows:
        try:
            if deliver_packet(db, packet):
                sent += 1
        except client.TgError:
            continue
    return sent


def send_text(db, profile_id: str, text: str) -> bool:
    bot = _linked_bot(db, profile_id)
    if bot is None:
        return False
    client.send_message(decrypt(bot.bot_token_enc), bot.chat_id, text)
    return True


def send_digest(db, profile_id: str, run: models.Run) -> None:
    stats = run.stats_json or {}
    disc = stats.get("discovery") or {}
    scor = stats.get("scoring") or {}
    tail = stats.get("tailoring") or {}
    lines = [f"🗞 JobScout {run.kind} run {'✅ done' if run.status == 'done' else '❌ ' + run.status}"]
    if disc:
        lines.append(
            f"🔎 {disc.get('new', 0)} new jobs · {disc.get('merged_duplicates', 0)} dups merged"
        )
    if scor:
        lines.append(
            f"⚖️ {scor.get('scored', 0)} scored · {scor.get('shortlisted', 0)} shortlisted"
            + (f" · avg {scor.get('avg_score')}" if scor.get("avg_score") is not None else "")
        )
    if tail:
        lines.append(
            f"✂️ {tail.get('tailored', 0)} packet(s) tailored · {tail.get('cover_letters', 0)} letter(s)"
        )
    errors = run.errors_json or []
    if errors:
        lines.append(f"⚠️ {len(errors)} source warning(s) — details in the app.")
    send_text(db, profile_id, "\n".join(lines))
