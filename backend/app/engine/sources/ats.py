"""Tier-2 sources: public ATS job-board JSON endpoints (no auth, freshest data).

Companies on the profile's watchlist are resolved to their ATS board (Greenhouse,
Lever, or Ashby) by probing slug candidates; results are cached per profile.
"""

import re
from typing import Optional

from .base import RawPosting, http_get, to_int
from ..util import parse_dt, strip_html


def _slug_candidates(company: str) -> list[str]:
    base = company.strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "", base)
    hyphenated = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    out = []
    for cand in (compact, hyphenated):
        if cand and cand not in out:
            out.append(cand)
    return out


# --- per-ATS fetchers --------------------------------------------------------------


def fetch_greenhouse(slug: str, company: str) -> list[RawPosting]:
    response = http_get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"}
    )
    response.raise_for_status()
    postings = []
    for item in response.json().get("jobs", []) or []:
        url = item.get("absolute_url") or ""
        title = item.get("title") or ""
        if not url or not title:
            continue
        postings.append(
            RawPosting(
                source="greenhouse",
                url=url,
                title=title,
                company=company,
                location=(item.get("location") or {}).get("name"),
                posted_at=parse_dt(item.get("updated_at")),
                description=strip_html(item.get("content"))[:30000],
            )
        )
    return postings


def fetch_lever(slug: str, company: str) -> list[RawPosting]:
    response = http_get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []
    postings = []
    for item in data:
        url = item.get("hostedUrl") or ""
        title = item.get("text") or ""
        if not url or not title:
            continue
        categories = item.get("categories") or {}
        postings.append(
            RawPosting(
                source="lever",
                url=url,
                title=title,
                company=company,
                location=categories.get("location"),
                remote="remote" if (item.get("workplaceType") == "remote") else None,
                posted_at=parse_dt(item.get("createdAt")),
                description=(item.get("descriptionPlain") or strip_html(item.get("description")))[
                    :30000
                ],
            )
        )
    return postings


def fetch_ashby(slug: str, company: str) -> list[RawPosting]:
    response = http_get(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        params={"includeCompensation": "true"},
    )
    response.raise_for_status()
    postings = []
    for item in response.json().get("jobs", []) or []:
        url = item.get("jobUrl") or item.get("applyUrl") or ""
        title = item.get("title") or ""
        if not url or not title or not item.get("isListed", True):
            continue
        comp = item.get("compensation") or {}
        summary = comp.get("compensationTierSummary") or ""
        salary_min = salary_max = None
        currency = None
        match = re.search(r"([A-Z]{3})?\s*\$?([\d,]+)K?\s*[–-]\s*\$?([\d,]+)(K)?", summary)
        if match:
            scale = 1000 if match.group(4) else 1
            salary_min = to_int(match.group(2).replace(",", "")) and int(
                match.group(2).replace(",", "")
            ) * scale
            salary_max = to_int(match.group(3).replace(",", "")) and int(
                match.group(3).replace(",", "")
            ) * scale
            currency = match.group(1)
        postings.append(
            RawPosting(
                source="ashby",
                url=url,
                title=title,
                company=company,
                location=item.get("location"),
                remote="remote" if item.get("isRemote") else None,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency=currency,
                posted_at=parse_dt(item.get("publishedAt")),
                description=strip_html(item.get("descriptionHtml"))[:30000],
            )
        )
    return postings


_FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def resolve_board(company: str) -> Optional[dict[str, str]]:
    """Probe Greenhouse → Lever → Ashby for the company's public board. None if not found."""
    for slug in _slug_candidates(company):
        probes = [
            ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", {}),
            ("lever", f"https://api.lever.co/v0/postings/{slug}", {"mode": "json", "limit": "1"}),
            ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{slug}", {}),
        ]
        for ats, url, params in probes:
            try:
                response = http_get(url, params=params)
                if response.status_code != 200:
                    continue
                payload = response.json()
                if ats == "lever" and isinstance(payload, list):
                    return {"ats": ats, "slug": slug}
                if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
                    return {"ats": ats, "slug": slug}
            except Exception:  # noqa: BLE001 - probing; any failure means "not this one"
                continue
    return None


def fetch_board(ats: str, slug: str, company: str) -> list[RawPosting]:
    return _FETCHERS[ats](slug, company)
