"""Tailoring stage: per job, build a truth-audited resume (+ cover letter) packet.

Chain: tailor (select/reorder/rephrase from the master profile ONLY) → adversarial
audit against the master profile → one revision round if flagged → Typst → PDF.
"""

import json
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel

from .. import llm, models
from ..config import settings
from ..ingest.service import latest_profile_row
from ..prefs import JobPreferences
from . import render

MODEL_TAILOR_DEFAULT = "claude-sonnet-4-6"  # user-overridable per profile (settings.models.tailoring)
TAILOR_CAP_DEFAULT = 5
JD_TRUNCATE = 14000


# --- schemas ----------------------------------------------------------------------


class TBullet(BaseModel):
    text: str
    source_doc_ids: list[str] = []  # provenance carried from the master profile


class TSkillGroup(BaseModel):
    name: str
    items: list[str] = []


class TRole(BaseModel):
    company: str
    title: str
    location: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    bullets: list[TBullet] = []


class TProject(BaseModel):
    name: str
    meta: Optional[str] = None  # one line: org / dates / outcome
    bullets: list[TBullet] = []


class TailoredResume(BaseModel):
    headline: str
    summary: str
    skills: list[TSkillGroup] = []
    roles: list[TRole] = []
    projects: list[TProject] = []
    ats_keywords_covered: list[str] = []
    ats_keywords_missing: list[str] = []


class CoverLetter(BaseModel):
    include: bool
    body_text: str = ""  # plain text paragraphs separated by blank lines
    hook: str = ""


class TailorResult(BaseModel):
    resume: TailoredResume
    cover_letter: CoverLetter
    jd_requirements_ranked: list[str] = []
    tailoring_notes: list[str] = []


class AuditFinding(BaseModel):
    claim: str
    verdict: Literal["unsupported", "stretched"]
    note: str = ""


class AuditResult(BaseModel):
    passed: bool
    findings: list[AuditFinding] = []  # only problems; empty when clean
    summary: str = ""


# --- prompts ----------------------------------------------------------------------

TAILOR_RULES = """\
You tailor ONE application (resume content + optional cover letter) for the candidate
above, for the job posting the user provides.

HARD CONSTRAINT — truthfulness:
- Every statement must be selected, reordered, or rephrased from the MASTER PROFILE
  above. Never invent experience, skills, metrics, dates, or tools. Rephrasing may use
  the job's vocabulary only where it accurately describes what the candidate did.
- Carry each bullet's source_doc_ids through from the master profile bullet(s) it came
  from. A separate auditor will reject unsupported claims.

Resume rules:
- Fits one page: at most 4 roles (most relevant first within reverse-chronological
  order), 2-4 bullets each, at most 3 projects with 1-2 bullets. Drop what doesn't
  serve THIS job.
- Lead bullets with impact + metrics. Weave the JD's actual keywords in truthfully —
  list what you covered in ats_keywords_covered and what the candidate genuinely lacks
  in ats_keywords_missing (never fake the missing ones).
- headline: one line positioning the candidate for THIS role.
- summary: 2-3 sentences targeted at this job's top requirements.
- skills: 3-5 groups, items reordered so JD-relevant skills come first; only real ones.

Cover letter rules:
- include=true when the posting asks for one OR a specific, credible hook exists
  (their domain matches the candidate's research/industry story). Otherwise false.
- 220-330 words, plain text, paragraphs separated by blank lines. Specific from the
  first sentence (no "I am writing to express..."). Use the cover-letter voice notes
  from the master profile where they fit. One concrete story > adjectives. No address
  header, no "Dear..." (the template adds it), no sign-off (template adds it).

tailoring_notes: 3-6 short lines for the candidate explaining what you emphasized,
reordered, or dropped and why."""

AUDIT_RULES = """\
You are an adversarial truthfulness auditor for a tailored resume and cover letter.
The MASTER PROFILE provided is the only source of truth (it was built from the
candidate's real documents and their own interview answers).

Check every factual claim in the tailored content: experiences, titles, dates,
metrics, tools, skills, publications, degrees.
- "unsupported": the claim does not appear in and cannot be reasonably inferred from
  the master profile. These are fabrications — flag every one.
- "stretched": technically grounded but materially exaggerated (e.g. "led" when the
  profile says "contributed", inflated scope or numbers).
Do NOT flag: reordering, omission, tone, or vocabulary borrowed from a job description
when the underlying activity is real. Judge substance, not phrasing.
passed = true only when there are zero unsupported claims (stretched-only may pass,
but list them). summary: one or two sentences."""

REVISE_RULES = """\
You previously tailored this application but an auditor flagged problems. Fix ONLY the
flagged claims: remove or rewrite each one so it is fully supported by the MASTER
PROFILE above. Keep everything else identical. Return the full corrected object."""


# --- chain ------------------------------------------------------------------------


def _tailor_system(profile_body: dict[str, Any], prefs: JobPreferences, design: str = "") -> str:
    system = (
        "[MASTER PROFILE — the only source of truth]\n"
        + json.dumps(profile_body, ensure_ascii=False)
        + "\n\n[CANDIDATE PREFERENCES]\n"
        + json.dumps(prefs.model_dump(), ensure_ascii=False)
        + "\n\n"
        + TAILOR_RULES
    )
    if design and design.strip():
        system += (
            "\n\n[CANDIDATE'S RÉSUMÉ DESIGN INSTRUCTIONS]\n"
            "The candidate specified how they want the résumé shaped (length, formatting, bullet "
            "style, etc.). Follow these exactly. Where they conflict with the general resume rules "
            "above — page count, number of bullets, bullet length — THESE INSTRUCTIONS WIN. Never "
            "violate the truthfulness constraint to satisfy them.\n"
            + design.strip()[:2000]
        )
    return system


def _job_block(job: models.Job, notes: str) -> str:
    verdict = job.score_json or {}
    parts = [
        f"Job: {job.title} @ {job.company} ({job.location or 'location unknown'})",
        f"Fit analysis from scoring: {verdict.get('rationale', 'n/a')}",
        f"Missing per scoring: {', '.join(verdict.get('missing_requirements') or []) or 'none'}",
    ]
    if notes:
        parts.append(f"CANDIDATE'S RE-TAILOR NOTES (must honor): {notes}")
    parts.append(f"\nFull job description:\n{(job.jd_text or '(none captured)')[:JD_TRUNCATE]}")
    return "\n".join(parts)


def _audit(client, profile_body: dict[str, Any], result: TailorResult, model: str) -> AuditResult:
    content = (
        "[MASTER PROFILE]\n"
        + json.dumps(profile_body, ensure_ascii=False)
        + "\n\n[TAILORED CONTENT TO AUDIT]\n"
        + json.dumps(result.model_dump(), ensure_ascii=False)
    )
    return llm.parse_call(
        client,
        model=model,
        system=AUDIT_RULES,
        content=content,
        schema=AuditResult,
        thinking=True,
        max_tokens=12000,
    )


def _render_packet(
    db, job: models.Job, profile_body: dict[str, Any], result: TailorResult, audit: AuditResult,
    version: int, notes: str,
) -> models.Packet:
    out_dir = (
        settings.files_dir / job.profile_id / "packets" / job.id / f"v{version}"
    )
    name = render.safe_filename(profile_body.get("full_name") or "Candidate")
    company = render.safe_filename(job.company)
    resume_pdf = out_dir / f"{name}_{company}_Resume.pdf"
    render.compile_pdf(render.resume_typ(profile_body, result.resume.model_dump()), resume_pdf)

    letter_pdf_path: Optional[str] = None
    if result.cover_letter.include and result.cover_letter.body_text.strip():
        letter_pdf = out_dir / f"{name}_{company}_Cover_Letter.pdf"
        render.compile_pdf(
            render.letter_typ(
                profile_body,
                {"company": job.company, "title": job.title},
                result.cover_letter.body_text,
            ),
            letter_pdf,
        )
        letter_pdf_path = str(letter_pdf)

    packet = models.Packet(
        job_id=job.id,
        version=version,
        status="ready" if audit.passed else "audit_flagged",
        tailor_json=result.model_dump(),
        audit_json=audit.model_dump(),
        resume_pdf=str(resume_pdf),
        letter_pdf=letter_pdf_path,
        retailor_notes=notes,
    )
    db.add(packet)
    return packet


def latest_packet(db, job_id: str) -> Optional[models.Packet]:
    return (
        db.query(models.Packet)
        .filter(models.Packet.job_id == job_id)
        .order_by(models.Packet.version.desc())
        .first()
    )


def tailor_job(db, job: models.Job, profile_body: dict[str, Any], prefs: JobPreferences,
               notes: str = "", model: str = MODEL_TAILOR_DEFAULT, design: str = "") -> models.Packet:
    """Full chain for one job: tailor → audit → revise-once-if-flagged → render → save."""
    client = llm.get_client(db)
    system = _tailor_system(profile_body, prefs, design)
    content = _job_block(job, notes)

    result = llm.parse_call(
        client, model=model, system=system, content=content,
        schema=TailorResult, thinking=True, max_tokens=32000, cache_system=True,
    )
    audit = _audit(client, profile_body, result, model)

    if not audit.passed:
        revise_content = (
            content
            + "\n\n[YOUR PREVIOUS ATTEMPT]\n"
            + json.dumps(result.model_dump(), ensure_ascii=False)
            + "\n\n[AUDIT FINDINGS TO FIX]\n"
            + json.dumps(audit.model_dump(), ensure_ascii=False)
            + "\n\n"
            + REVISE_RULES
        )
        result = llm.parse_call(
            client, model=model, system=system, content=revise_content,
            schema=TailorResult, thinking=True, max_tokens=32000, cache_system=True,
        )
        audit = _audit(client, profile_body, result, model)

    previous = latest_packet(db, job.id)
    version = (previous.version + 1) if previous else 1
    packet = _render_packet(db, job, profile_body, result, audit, version, notes)
    job.status = "tailored"
    db.commit()
    try:
        from ..telegram import delivery

        delivery.deliver_packet(db, packet)
    except Exception:  # noqa: BLE001 - delivery is best-effort
        pass
    return packet


def _context(db, profile_id: str) -> tuple[Optional[dict], Optional[JobPreferences]]:
    profile_row = latest_profile_row(db, profile_id)
    prefs_row = (
        db.query(models.Preference)
        .filter(models.Preference.profile_id == profile_id)
        .order_by(models.Preference.version.desc())
        .first()
    )
    if profile_row is None or prefs_row is None:
        return None, None
    return profile_row.body_json, JobPreferences(**prefs_row.structured_json)


def tailor_new(db, profile_id: str) -> tuple[dict, list[dict]]:
    """Stage: tailor shortlisted jobs that don't have a packet yet (capped)."""
    errors: list[dict] = []
    profile_body, prefs = _context(db, profile_id)
    if profile_body is None or prefs is None:
        return {}, [{"source": "tailoring", "error": "Needs a master profile and preferences."}]

    profile = db.get(models.Profile, profile_id)
    cap = int(((profile.settings_json or {}).get("caps") or {}).get("tailor_per_run", TAILOR_CAP_DEFAULT))
    model = llm.model_for(profile.settings_json, "tailoring", MODEL_TAILOR_DEFAULT)
    design = (profile.settings_json or {}).get("resume_design") or ""
    jobs = (
        db.query(models.Job)
        .filter(models.Job.profile_id == profile_id, models.Job.status == "shortlisted")
        .order_by(models.Job.score.desc().nullslast())
        .limit(cap)
        .all()
    )
    if not jobs:
        return {"tailored": 0, "note": "no shortlisted jobs without packets"}, []

    tailored = flagged = failed = letters = 0
    for job in jobs:
        try:
            packet = tailor_job(db, job, profile_body, prefs, model=model, design=design)
            tailored += 1
            if packet.status == "audit_flagged":
                flagged += 1
            if packet.letter_pdf:
                letters += 1
        except Exception as exc:  # noqa: BLE001 - per-job isolation
            db.rollback()
            failed += 1
            errors.append({"source": f"tailor:{job.company}", "error": llm.short_error(exc) or ""})
    db.commit()
    return {
        "tailored": tailored,
        "cover_letters": letters,
        "audit_flagged": flagged,
        "failed": failed,
        "cap": cap,
        "model": model,
    }, errors


def tailor_single(profile_id: str, job_id: str, notes: str = "") -> None:
    """Background task: tailor one specific job on demand (incl. re-tailor with notes)."""
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(models.Job, job_id)
        if job is None or job.profile_id != profile_id:
            return
        profile_body, prefs = _context(db, profile_id)
        if profile_body is None or prefs is None:
            job.status = "scored" if job.score is not None else "discovered"
            db.commit()
            return
        profile = db.get(models.Profile, profile_id)
        settings = profile.settings_json if profile else None
        model = llm.model_for(settings, "tailoring", MODEL_TAILOR_DEFAULT)
        design = (settings or {}).get("resume_design") or ""
        try:
            tailor_job(db, job, profile_body, prefs, notes=notes, model=model, design=design)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job = db.get(models.Job, job_id)
            verdict = (job.score_json or {}).get("recommend")
            job.status = "shortlisted" if verdict == "apply" else ("scored" if job.score is not None else "discovered")
            db.add(
                models.Packet(
                    job_id=job.id,
                    version=(latest_packet(db, job.id).version + 1) if latest_packet(db, job.id) else 1,
                    status="failed",
                    tailor_json={"error": llm.short_error(exc)},
                    retailor_notes=notes,
                )
            )
            db.commit()
    finally:
        db.close()
