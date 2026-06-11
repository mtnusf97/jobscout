"""Per-bot long-poll listeners: /start linking, /run, button callbacks, re-tailor notes.

One daemon thread per connected bot, started at app startup and on connect. Threads
die with the process (incl. --reload restarts) and are restarted by the lifespan hook —
the getUpdates offset is re-derived from Telegram's queue, so nothing is lost.
"""

import threading
from datetime import datetime, timezone
from typing import Optional

from .. import models
from ..db import SessionLocal
from ..security import decrypt
from . import client, delivery

_registry: dict[str, threading.Event] = {}  # bot row id -> stop event
_pending_retailor: dict[int, str] = {}  # chat_id -> job_id awaiting notes
_lock = threading.Lock()

HELP_TEXT = (
    "JobScout commands:\n"
    "/run — run the full pipeline now (discover → score → tailor)\n"
    "/help — this message\n\n"
    "Packet cards arrive here automatically after every run. Use the buttons on each "
    "card; 🔁 Re-tailor will ask you to reply with notes."
)


def start_listener(bot_id: str) -> None:
    with _lock:
        if bot_id in _registry:
            return
        stop = threading.Event()
        _registry[bot_id] = stop
    thread = threading.Thread(target=_listen, args=(bot_id, stop), daemon=True, name=f"tg-{bot_id[:8]}")
    thread.start()


def stop_listener(bot_id: str) -> None:
    with _lock:
        stop = _registry.pop(bot_id, None)
    if stop is not None:
        stop.set()


def start_all() -> None:
    db = SessionLocal()
    try:
        for bot in db.query(models.TelegramBot).all():
            start_listener(bot.id)
    finally:
        db.close()


def _listen(bot_id: str, stop: threading.Event) -> None:
    offset = 0
    while not stop.is_set():
        db = SessionLocal()
        try:
            bot = db.get(models.TelegramBot, bot_id)
            if bot is None:
                return
            token = decrypt(bot.bot_token_enc)
            try:
                updates = client.get_updates(token, offset)
            except client.TgError:
                stop.wait(5)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    _handle(db, bot, token, update)
                except Exception:  # noqa: BLE001 - one bad update must not kill the loop
                    db.rollback()
        finally:
            db.close()


def _handle(db, bot: models.TelegramBot, token: str, update: dict) -> None:
    if "callback_query" in update:
        _handle_callback(db, bot, token, update["callback_query"])
        return
    message = update.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    text = (message.get("text") or "").strip()
    if chat_id is None or not text:
        return

    if text.startswith("/start"):
        payload = text.split(maxsplit=1)[1].strip() if " " in text else ""
        if bot.status == "linked" and bot.chat_id == chat_id:
            client.send_message(token, chat_id, "Already connected ✅\n\n" + HELP_TEXT)
        elif payload == bot.link_code:
            bot.chat_id = chat_id
            bot.status = "linked"
            bot.linked_at = datetime.now(timezone.utc)
            db.commit()
            client.send_message(
                token,
                chat_id,
                "🎉 Connected! JobScout will deliver tailored application packets here.\n\n"
                + HELP_TEXT,
            )
            sent = delivery.deliver_pending(db, bot.profile_id)
            if sent:
                client.send_message(token, chat_id, f"📦 {sent} packet(s) were waiting — sent above.")
        else:
            client.send_message(
                token,
                chat_id,
                "This bot links through the JobScout app — open your profile page and use "
                "the connect button there (it gives you the right /start link).",
            )
        return

    if bot.status != "linked" or bot.chat_id != chat_id:
        return  # ignore strangers / unlinked chats

    if text == "/run":
        started = _start_run(db, bot.profile_id)
        client.send_message(token, chat_id, started)
        return
    if text == "/help":
        client.send_message(token, chat_id, HELP_TEXT)
        return

    job_id = _pending_retailor.pop(chat_id, None)
    if job_id is not None:
        notes = "" if text == "-" else text
        job = db.get(models.Job, job_id)
        if job is None:
            client.send_message(token, chat_id, "That job vanished — try from the app.")
            return
        job.status = "tailoring"
        db.commit()
        from ..engine.tailoring import tailor_single

        threading.Thread(
            target=tailor_single, args=(bot.profile_id, job_id, notes), daemon=True
        ).start()
        client.send_message(
            token, chat_id, "🔁 Re-tailoring with your notes — the new packet lands here in a few minutes."
        )
        return

    client.send_message(token, chat_id, HELP_TEXT)


def _handle_callback(db, bot: models.TelegramBot, token: str, callback: dict) -> None:
    data = callback.get("data") or ""
    callback_id = callback.get("id") or ""
    chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
    if bot.status != "linked" or chat_id != bot.chat_id:
        client.answer_callback(token, callback_id, "Not linked.")
        return
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "act":
        client.answer_callback(token, callback_id)
        return
    _, action, job_id = parts
    job = db.get(models.Job, job_id)
    if job is None or job.profile_id != bot.profile_id:
        client.answer_callback(token, callback_id, "Job not found.")
        return
    if action == "applied":
        job.status = "applied"
        db.commit()
        client.answer_callback(token, callback_id, "Marked applied ✅ — good luck!")
    elif action == "skip":
        job.status = "skipped"
        db.commit()
        client.answer_callback(token, callback_id, "Skipped ❌")
    elif action == "retailor":
        _pending_retailor[chat_id] = job_id
        client.answer_callback(token, callback_id)
        client.send_message(
            token,
            chat_id,
            f"🔁 Re-tailor “{job.title} @ {job.company}”.\n"
            "Reply with notes for the agent (e.g. “emphasize leadership, drop the crypto "
            "project”) — or send “-” for none.",
        )
    else:
        client.answer_callback(token, callback_id)


def _start_run(db, profile_id: str) -> str:
    active = (
        db.query(models.Run)
        .filter(models.Run.profile_id == profile_id, models.Run.status == "running")
        .first()
    )
    if active is not None:
        return "A run is already in progress — the digest lands here when it finishes."
    run = models.Run(profile_id=profile_id, kind="full")
    db.add(run)
    db.commit()
    from ..engine.pipeline import run_pipeline

    threading.Thread(
        target=run_pipeline, args=(profile_id, run.id, "full"), daemon=True
    ).start()
    return "🔎 Pipeline started (discover → score → tailor). Digest + packets land here when done."
