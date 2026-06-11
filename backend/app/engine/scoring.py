"""LLM scoring: every discovered job gets a structured verdict against the candidate.

One stable system prompt per run (candidate digest + preferences + rules) with a cache
breakpoint; jobs fan out as user messages — calls 2..N read the cached prefix.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal, Optional

import anthropic
from pydantic import BaseModel

from .. import llm, models
from ..ingest.service import latest_profile_row
from ..prefs import JobPreferences

MODEL_SCORE = "claude-opus-4-8"
SCORE_CAP_DEFAULT = 80
JD_TRUNCATE = 12000
CONCURRENCY = 4


class ScoreVerdict(BaseModel):
    fit_score: int  # 0-100
    recommend: Literal["apply", "maybe", "skip"]
    rationale: str
    matched_requirements: list[str] = []
    missing_requirements: list[str] = []
    dealbreakers_triggered: list[str] = []
    salary_assessment: str = ""
    salary_estimate_min: Optional[int] = None
    salary_estimate_max: Optional[int] = None
    salary_estimate_currency: Optional[str] = None
    salary_meets_floor: Optional[bool] = None


SCORING_RULES = """\
You score ONE job posting per call for fit against the candidate above.

Rules:
- fit_score 0-100: 90+ exceptional (apply today), 75-89 strong, 60-74 plausible stretch,
  40-59 weak, <40 wrong role. Most jobs land below 75 — don't grade-inflate.
- Weigh heavily: role/title match to the target titles; required-skills overlap with the
  candidate's ACTUAL evidence (not generic adjacency); seniority alignment; location and
  remote compatibility; salary vs the candidate's floor; dealbreakers.
- Salary: if the posting lists none, estimate the likely annual range for this title,
  company, and location market — fill salary_estimate_* and be honest about uncertainty
  in salary_assessment. salary_meets_floor compares listed-or-estimated range against
  the candidate's floor (true only when the upper end clears it).
- dealbreakers_triggered: any candidate dealbreaker this posting violates (empty if none).
- recommend: "apply" = clear fit, no dealbreakers, salary plausible; "maybe" = decent
  fit with real doubts; "skip" = wrong role, dealbreaker, or salary clearly below floor.
- rationale: 2-3 specific sentences citing the candidate's actual experience and the
  posting's actual asks. No fluff, no repetition of the score.
- matched_requirements / missing_requirements: the posting's top asks, split by whether
  the candidate has concrete evidence for them."""


def profile_digest(body: dict[str, Any]) -> str:
    lines = [
        f"Name: {body.get('full_name')}",
        f"Headline: {body.get('headline')}",
        f"Location: {body.get('location')}",
        f"Summary: {body.get('summary')}",
        "",
        "Experience:",
    ]
    for role in body.get("roles", []):
        bullets = "; ".join(b.get("text", "") for b in (role.get("bullets") or [])[:3])
        lines.append(
            f"- {role.get('title')} @ {role.get('company')}"
            f" ({role.get('start')} → {role.get('end')}): {bullets}"
        )
    lines.append("")
    lines.append("Education:")
    for ed in body.get("education", []):
        lines.append(
            f"- {ed.get('degree')}, {ed.get('field')} — {ed.get('institution')}"
            f" ({ed.get('start')} → {ed.get('end')})"
        )
    lines.append("")
    lines.append("Skills:")
    for group in body.get("skills", []):
        lines.append(f"- {group.get('name')}: {', '.join(group.get('items') or [])}")
    extra = [f.get("text") for f in body.get("other_facts", []) if isinstance(f, dict)]
    if extra:
        lines.append("")
        lines.append("Also on file: " + " | ".join(x for x in extra if x))
    return "\n".join(line for line in lines if line is not None)[:8000]


def _build_system(body: dict[str, Any], prefs: JobPreferences) -> str:
    return (
        "[CANDIDATE PROFILE]\n"
        + profile_digest(body)
        + "\n\n[CANDIDATE PREFERENCES]\n"
        + json.dumps(prefs.model_dump(), ensure_ascii=False)
        + "\n\n"
        + SCORING_RULES
    )


def _job_block(job: models.Job) -> str:
    listed = (
        f"{job.salary_min}–{job.salary_max} {job.salary_currency or ''}"
        if (job.salary_min or job.salary_max)
        else "not listed"
    )
    return (
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location or 'unknown'}"
        f"{' (' + job.remote_type + ')' if job.remote_type else ''}\n"
        f"Salary listed: {listed}\n"
        f"Posted: {job.posted_at.date().isoformat() if job.posted_at else 'unknown'}\n\n"
        f"Description:\n{(job.jd_text or '(no description captured)')[:JD_TRUNCATE]}"
    )


class _AbortScoring(Exception):
    """Raised on auth/billing failures — pointless to keep hammering the API."""


def _score_one(
    client: anthropic.Anthropic, system: str, job: models.Job
) -> tuple[str, ScoreVerdict | Exception]:
    try:
        verdict = llm.parse_call(
            client,
            model=MODEL_SCORE,
            system=system,
            content=_job_block(job),
            schema=ScoreVerdict,
            max_tokens=2000,
            cache_system=True,
        )
        return job.id, verdict
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
        raise _AbortScoring(llm.friendly_llm_error(exc)) from exc
    except anthropic.BadRequestError as exc:
        if "credit" in str(exc).lower():
            raise _AbortScoring(llm.friendly_llm_error(exc)) from exc
        return job.id, exc
    except Exception as exc:  # noqa: BLE001 - per-job isolation
        return job.id, exc


def score_single(db, profile_id: str, job_id: str) -> None:
    """Score one job synchronously (ad-hoc flow). Raises on failure."""
    job = db.get(models.Job, job_id)
    if job is None or job.profile_id != profile_id:
        raise RuntimeError("Job not found.")
    prefs_row = (
        db.query(models.Preference)
        .filter(models.Preference.profile_id == profile_id)
        .order_by(models.Preference.version.desc())
        .first()
    )
    profile_row = latest_profile_row(db, profile_id)
    if prefs_row is None or profile_row is None:
        raise RuntimeError("Needs both a master profile and preferences.")
    client = llm.get_client(db)
    system = _build_system(profile_row.body_json, JobPreferences(**prefs_row.structured_json))
    _, result = _score_one(client, system, job)
    if isinstance(result, Exception):
        raise result
    job.score = max(0, min(100, int(result.fit_score)))
    job.score_json = result.model_dump()
    job.status = (
        "shortlisted"
        if (result.recommend == "apply" and not result.dealbreakers_triggered)
        else "scored"
    )
    db.commit()


def score_new(db, profile_id: str) -> tuple[dict, list[dict]]:
    """Stage: score every job in status 'discovered' (capped per run)."""
    errors: list[dict] = []

    prefs_row = (
        db.query(models.Preference)
        .filter(models.Preference.profile_id == profile_id)
        .order_by(models.Preference.version.desc())
        .first()
    )
    profile_row = latest_profile_row(db, profile_id)
    if prefs_row is None or profile_row is None:
        return {}, [
            {"source": "scoring", "error": "Needs both a master profile and preferences."}
        ]

    profile = db.get(models.Profile, profile_id)
    cap = int(((profile.settings_json or {}).get("caps") or {}).get("score_per_run", SCORE_CAP_DEFAULT))
    jobs = (
        db.query(models.Job)
        .filter(models.Job.profile_id == profile_id, models.Job.status == "discovered")
        .order_by(models.Job.first_seen_at.desc())
        .limit(cap)
        .all()
    )
    if not jobs:
        return {"scored": 0, "shortlisted": 0, "note": "nothing new to score"}, []

    client = llm.get_client(db)
    system = _build_system(profile_row.body_json, JobPreferences(**prefs_row.structured_json))

    results: dict[str, ScoreVerdict | Exception] = {}
    try:
        # First call alone writes the prompt cache; the rest fan out and read it.
        first_id, first_result = _score_one(client, system, jobs[0])
        results[first_id] = first_result
        if len(jobs) > 1:
            with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
                for job_id, result in pool.map(
                    lambda j: _score_one(client, system, j), jobs[1:]
                ):
                    results[job_id] = result
    except _AbortScoring as exc:
        errors.append({"source": "scoring", "error": f"aborted: {exc}"})

    scored = shortlisted = failed = 0
    score_sum = 0
    for job in jobs:
        result = results.get(job.id)
        if result is None:
            continue  # aborted before reaching this job; stays 'discovered'
        if isinstance(result, Exception):
            failed += 1
            if failed <= 5:
                errors.append({"source": f"score:{job.company}", "error": str(result)[:200]})
            continue
        job.score = max(0, min(100, int(result.fit_score)))
        job.score_json = result.model_dump()
        job.status = (
            "shortlisted"
            if (result.recommend == "apply" and not result.dealbreakers_triggered)
            else "scored"
        )
        scored += 1
        score_sum += job.score
        if job.status == "shortlisted":
            shortlisted += 1
    db.commit()

    stats = {
        "scored": scored,
        "shortlisted": shortlisted,
        "failed": failed,
        "avg_score": round(score_sum / scored, 1) if scored else None,
        "remaining_unscored": max(0, len(jobs) - scored - failed),
        "cap": cap,
    }
    return stats, errors
