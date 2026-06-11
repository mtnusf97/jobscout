"""Daily scheduler: fires one full pipeline run per profile per day at the chosen time.

A 30-second daemon tick — no cron, no external scheduler. Config lives in
profiles.settings_json["schedule"] = {"enabled": bool, "time": "HH:MM", "last_date": "YYYY-MM-DD"}.
If the app was down (laptop asleep) at the target time, the run fires on the next tick
after wake — a late morning run beats no run.
"""

import threading
import time as _time
from datetime import datetime

from . import models
from .db import SessionLocal

_started = False


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="scheduler").start()


def _loop() -> None:
    while True:
        try:
            _tick()
        except Exception:  # noqa: BLE001 - the scheduler must never die
            pass
        _time.sleep(30)


def _tick() -> None:
    now = datetime.now()  # local time — schedule times are what the user's clock says
    today = now.date().isoformat()
    current = now.strftime("%H:%M")
    db = SessionLocal()
    try:
        for profile in db.query(models.Profile).all():
            settings_json = profile.settings_json or {}
            schedule = settings_json.get("schedule") or {}
            if not schedule.get("enabled"):
                continue
            target = schedule.get("time") or "08:00"
            if schedule.get("last_date") == today or current < target:
                continue
            active = (
                db.query(models.Run)
                .filter(models.Run.profile_id == profile.id, models.Run.status == "running")
                .first()
            )
            if active is not None:
                continue
            run = models.Run(profile_id=profile.id, kind="full")
            db.add(run)
            profile.settings_json = {
                **settings_json,
                "schedule": {**schedule, "last_date": today},
            }
            db.commit()

            from .engine.pipeline import run_pipeline

            threading.Thread(
                target=run_pipeline, args=(profile.id, run.id, "full"), daemon=True
            ).start()
    finally:
        db.close()
