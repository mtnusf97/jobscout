"""JSearch (RapidAPI) — aggregates the Google-for-Jobs index (LinkedIn/Indeed/etc. syndication)."""

from ...prefs import JobPreferences
from .base import RawPosting, http_get, to_int
from ..util import parse_dt

API = "https://jsearch.p.rapidapi.com/search"
HOST = "jsearch.p.rapidapi.com"


def _queries(prefs: JobPreferences) -> list[str]:
    location = prefs.locations[0] if prefs.locations else (
        "remote" if prefs.remote_stance in ("remote_only", "remote_preferred") else ""
    )
    titles = prefs.target_titles[:4] or ["software engineer"]
    return [f"{title} in {location}".strip() if location else title for title in titles]


def fetch(prefs: JobPreferences, api_key: str) -> list[RawPosting]:
    postings: list[RawPosting] = []
    for query in _queries(prefs):
        response = http_get(
            API,
            params={"query": query, "page": "1", "num_pages": "1", "date_posted": "month"},
            headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": HOST},
        )
        response.raise_for_status()
        for item in response.json().get("data", []) or []:
            url = item.get("job_apply_link") or item.get("job_google_link") or ""
            title = item.get("job_title") or ""
            company = item.get("employer_name") or ""
            if not url or not title or not company:
                continue
            location = ", ".join(
                part
                for part in (item.get("job_city"), item.get("job_state"), item.get("job_country"))
                if part
            ) or None
            postings.append(
                RawPosting(
                    source="jsearch",
                    url=url,
                    title=title,
                    company=company,
                    location=location,
                    remote="remote" if item.get("job_is_remote") else None,
                    salary_min=to_int(item.get("job_min_salary")),
                    salary_max=to_int(item.get("job_max_salary")),
                    salary_currency=item.get("job_salary_currency"),
                    posted_at=parse_dt(item.get("job_posted_at_datetime_utc")),
                    description=(item.get("job_description") or "")[:30000],
                )
            )
    return postings
