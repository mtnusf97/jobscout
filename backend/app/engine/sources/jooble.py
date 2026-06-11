"""Jooble API (optional) — extra discovery coverage."""

import httpx

from ...prefs import JobPreferences
from .base import TIMEOUT, USER_AGENT, RawPosting
from ..util import parse_dt, strip_html


def fetch(prefs: JobPreferences, api_key: str) -> list[RawPosting]:
    location = prefs.locations[0].split(",")[0] if prefs.locations else ""
    postings: list[RawPosting] = []
    for title in prefs.target_titles[:3] or ["software engineer"]:
        response = httpx.post(
            f"https://jooble.org/api/{api_key}",
            json={"keywords": title, "location": location},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        for item in response.json().get("jobs", []) or []:
            url = item.get("link") or ""
            job_title = item.get("title") or ""
            company = item.get("company") or ""
            if not url or not job_title or not company:
                continue
            postings.append(
                RawPosting(
                    source="jooble",
                    url=url,
                    title=strip_html(job_title),
                    company=company,
                    location=item.get("location"),
                    posted_at=parse_dt(item.get("updated")),
                    description=strip_html(item.get("snippet"))[:30000],
                )
            )
    return postings
