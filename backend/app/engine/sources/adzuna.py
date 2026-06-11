"""Adzuna public API — job search with salary data (free tier)."""

from ...prefs import JobPreferences
from .base import RawPosting, http_get, to_int
from ..util import parse_dt

_COUNTRY_HINTS = {
    "ca": ("canada", "toronto", "ontario", "vancouver", "montreal", "ottawa", "waterloo"),
    "us": ("united states", "usa", "new york", "california", "seattle", "boston", "austin"),
    "gb": ("united kingdom", "uk", "london", "manchester"),
    "de": ("germany", "berlin", "munich"),
    "nl": ("netherlands", "amsterdam"),
    "au": ("australia", "sydney", "melbourne"),
}


def _country(prefs: JobPreferences) -> str:
    haystack = " ".join([*prefs.locations, *(prefs.notes or [])]).lower()
    for code, hints in _COUNTRY_HINTS.items():
        if any(hint in haystack for hint in hints):
            return code
    return "us"


def fetch(prefs: JobPreferences, app_id: str, app_key: str) -> list[RawPosting]:
    country = _country(prefs)
    where = prefs.locations[0].split(",")[0] if prefs.locations else ""
    postings: list[RawPosting] = []
    for title in prefs.target_titles[:4] or ["software engineer"]:
        response = http_get(
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
            params={
                "app_id": app_id,
                "app_key": app_key,
                "what": title,
                "where": where,
                "results_per_page": 25,
                "max_days_old": 35,
                "content-type": "application/json",
            },
        )
        response.raise_for_status()
        for item in response.json().get("results", []) or []:
            url = item.get("redirect_url") or ""
            job_title = item.get("title") or ""
            company = (item.get("company") or {}).get("display_name") or ""
            if not url or not job_title or not company:
                continue
            postings.append(
                RawPosting(
                    source="adzuna",
                    url=url,
                    title=job_title.replace("<strong>", "").replace("</strong>", ""),
                    company=company,
                    location=(item.get("location") or {}).get("display_name"),
                    salary_min=to_int(item.get("salary_min")),
                    salary_max=to_int(item.get("salary_max")),
                    salary_currency={"ca": "CAD", "us": "USD", "gb": "GBP"}.get(country),
                    posted_at=parse_dt(item.get("created")),
                    description=(item.get("description") or "")[:30000],
                )
            )
    return postings
