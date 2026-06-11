from datetime import datetime
from typing import Optional

import httpx
from pydantic import BaseModel

USER_AGENT = "JobScout/0.4 (personal job-search agent)"
TIMEOUT = httpx.Timeout(45.0)  # job APIs (JSearch especially) are routinely slow


class RawPosting(BaseModel):
    source: str
    url: str
    title: str
    company: str
    location: Optional[str] = None
    remote: Optional[str] = None  # remote | hybrid | onsite | None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    posted_at: Optional[datetime] = None
    description: str = ""


def http_get(url: str, **kwargs) -> httpx.Response:
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    try:
        return httpx.get(url, headers=headers, timeout=TIMEOUT, follow_redirects=True, **kwargs)
    except httpx.TimeoutException:
        # third-party job APIs are routinely slow for a beat — one retry is cheap
        return httpx.get(url, headers=headers, timeout=TIMEOUT, follow_redirects=True, **kwargs)


def to_int(value) -> Optional[int]:
    try:
        if value is None:
            return None
        number = float(value)
        return int(round(number)) if number > 0 else None
    except (TypeError, ValueError):
        return None
