"""Discovery stage: query all enabled sources, normalize, dedupe against history, store.

Every source is isolated — one failing source lands in the errors list, never kills
the stage. Run-row management lives in engine.pipeline.
"""

from datetime import datetime, timezone
from typing import Optional

from .. import credentials, models
from ..prefs import JobPreferences
from .sources import adzuna, ats, jooble, jsearch
from .sources.base import RawPosting
from .util import canonical_url, dedupe_key, jd_hash, relevance_tokens, title_is_relevant


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _latest_prefs(db, profile_id: str) -> Optional[JobPreferences]:
    row = (
        db.query(models.Preference)
        .filter(models.Preference.profile_id == profile_id)
        .order_by(models.Preference.version.desc())
        .first()
    )
    if row is None:
        return None
    return JobPreferences(**row.structured_json)


def _upsert(db, profile_id: str, posting: RawPosting) -> str:
    """Insert or merge one posting. Returns 'new' | 'merged'."""
    canon = canonical_url(posting.url)
    dkey = dedupe_key(posting.company, posting.title, posting.location)
    existing = (
        db.query(models.Job)
        .filter(
            models.Job.profile_id == profile_id,
            (models.Job.canonical_url == canon) | (models.Job.dedupe_key == dkey),
        )
        .first()
    )
    if existing is not None:
        if posting.source not in (existing.sources_json or []):
            existing.sources_json = [*(existing.sources_json or []), posting.source]
        if posting.url not in (existing.urls_json or []):
            existing.urls_json = [*(existing.urls_json or []), posting.url]
        if len(posting.description) > len(existing.jd_text or ""):
            existing.jd_text = posting.description
            existing.jd_hash = jd_hash(posting.description)
        if existing.salary_min is None and posting.salary_min is not None:
            existing.salary_min = posting.salary_min
            existing.salary_max = posting.salary_max
            existing.salary_currency = posting.salary_currency
        existing.last_seen_at = _utcnow()
        return "merged"

    db.add(
        models.Job(
            profile_id=profile_id,
            sources_json=[posting.source],
            urls_json=[posting.url],
            canonical_url=canon,
            company=posting.company.strip()[:200],
            title=posting.title.strip()[:300],
            location=(posting.location or None),
            remote_type=posting.remote,
            salary_min=posting.salary_min,
            salary_max=posting.salary_max,
            salary_currency=posting.salary_currency,
            posted_at=posting.posted_at,
            jd_text=posting.description,
            jd_hash=jd_hash(posting.description),
            dedupe_key=dkey,
        )
    )
    return "new"


def discover(db, profile_id: str) -> tuple[dict, list[dict]]:
    """Stage: fetch → relevance gate → dedupe → store. Returns (stats, errors)."""
    errors: list[dict] = []
    by_source: dict[str, int] = {}
    postings: list[RawPosting] = []

    prefs = _latest_prefs(db, profile_id)
    if prefs is None:
        return {}, [{"source": "preferences", "error": "No preferences set yet."}]

    # --- Tier 1: aggregator APIs ------------------------------------------------
    jsearch_key = credentials.get_value(db, "rapidapi_jsearch_key")
    if jsearch_key:
        try:
            found = jsearch.fetch(prefs, jsearch_key)
            by_source["jsearch"] = len(found)
            postings.extend(found)
        except Exception as exc:  # noqa: BLE001
            errors.append({"source": "jsearch", "error": str(exc)[:300]})
    else:
        errors.append({"source": "jsearch", "error": "skipped — no RapidAPI key in Settings"})

    adzuna_id = credentials.get_value(db, "adzuna_app_id")
    adzuna_key = credentials.get_value(db, "adzuna_app_key")
    if adzuna_id and adzuna_key:
        try:
            found = adzuna.fetch(prefs, adzuna_id, adzuna_key)
            by_source["adzuna"] = len(found)
            postings.extend(found)
        except Exception as exc:  # noqa: BLE001
            errors.append({"source": "adzuna", "error": str(exc)[:300]})
    else:
        errors.append({"source": "adzuna", "error": "skipped — no Adzuna keys in Settings"})

    jooble_key = credentials.get_value(db, "jooble_api_key")
    if jooble_key:
        try:
            found = jooble.fetch(prefs, jooble_key)
            by_source["jooble"] = len(found)
            postings.extend(found)
        except Exception as exc:  # noqa: BLE001
            errors.append({"source": "jooble", "error": str(exc)[:300]})

    # --- Cheap relevance gate on aggregator results -------------------------------
    # Aggregators keyword-match loosely ("Tech Lead" → "Sales Support Coordinator").
    # Require ≥1 meaningful title/keyword token in the posting title; nuanced judgment
    # stays with LLM scoring.
    tokens = relevance_tokens(prefs.target_titles, prefs.keywords_must)
    irrelevant_skipped = len(postings)
    postings = [p for p in postings if title_is_relevant(p.title, tokens)]
    irrelevant_skipped -= len(postings)

    # --- Salary sanity: hourly rates / garbage minimums → unknown ------------------
    for posting in postings:
        if posting.salary_min is not None and posting.salary_min < 10000:
            posting.salary_min = None
            posting.salary_max = None
            posting.salary_currency = None

    # --- Tier 2: ATS boards for the watchlist -------------------------------------
    watchlist = prefs.company_watchlist or []
    if watchlist:
        profile = db.get(models.Profile, profile_id)
        cache: dict = dict((profile.settings_json or {}).get("ats_boards") or {})
        for company in watchlist[:25]:
            try:
                board = cache.get(company, "unresolved")
                if board == "unresolved":
                    board = ats.resolve_board(company)
                    cache[company] = board
                if not board:
                    continue
                found = ats.fetch_board(board["ats"], board["slug"], company)
                kept = [p for p in found if title_is_relevant(p.title, tokens)]
                irrelevant_skipped += len(found) - len(kept)
                by_source[f"ats:{company}"] = len(kept)
                postings.extend(kept)
            except Exception as exc:  # noqa: BLE001
                errors.append({"source": f"ats:{company}", "error": str(exc)[:300]})
        profile.settings_json = {**(profile.settings_json or {}), "ats_boards": cache}

    # --- Dedupe + store ------------------------------------------------------------
    new_count = 0
    merged_count = 0
    for posting in postings:
        if _upsert(db, profile_id, posting) == "new":
            new_count += 1
        else:
            merged_count += 1
        db.flush()
    db.commit()

    stats = {
        "total_fetched": len(postings),
        "new": new_count,
        "merged_duplicates": merged_count,
        "irrelevant_skipped": irrelevant_skipped,
        "by_source": by_source,
        "watchlist_size": len(watchlist),
    }
    return stats, errors
