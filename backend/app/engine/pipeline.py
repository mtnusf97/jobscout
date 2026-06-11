"""Pipeline runner: executes stages in order against one Run row, as a background task.

Stats commit progressively so the UI shows discovery results while scoring still runs.
"""

from datetime import datetime, timezone

from .. import models
from ..db import SessionLocal
from . import discovery, scoring, tailoring

STAGES = {
    "discovery": discovery.discover,
    "scoring": scoring.score_new,
    "tailoring": tailoring.tailor_new,
}

KIND_STAGES = {
    "full": ["discovery", "scoring", "tailoring"],
    "discovery": ["discovery"],
    "scoring": ["scoring"],
    "tailoring": ["tailoring"],
}


def run_pipeline(profile_id: str, run_id: str, kind: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.Run, run_id)
        if run is None:
            return
        all_stats: dict = {}
        all_errors: list = []
        for stage_name in KIND_STAGES.get(kind, ["discovery"]):
            try:
                stats, errors = STAGES[stage_name](db, profile_id)
            except Exception as exc:  # noqa: BLE001 - a stage crash must not zombie the run
                db.rollback()
                stats, errors = {}, [{"source": stage_name, "error": str(exc)[:300]}]
            all_stats[stage_name] = stats
            all_errors.extend(errors)
            run = db.get(models.Run, run_id)
            run.stats_json = dict(all_stats)
            run.errors_json = list(all_errors)
            db.commit()
        produced_anything = any(bool(v) for v in all_stats.values())
        run.status = "done" if (produced_anything or not all_errors) else "failed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        try:
            from ..telegram import delivery

            delivery.send_digest(db, profile_id, run)
        except Exception:  # noqa: BLE001 - delivery is best-effort
            pass
    finally:
        db.close()


def recover_interrupted_runs() -> None:
    """On startup: runs orphaned by a restart become failed-with-explanation."""
    db = SessionLocal()
    try:
        stuck = db.query(models.Run).filter(models.Run.status == "running").all()
        for run in stuck:
            run.status = "failed"
            run.errors_json = [
                *(run.errors_json or []),
                {"source": "run", "error": "Interrupted by a server restart — run again."},
            ]
            run.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
