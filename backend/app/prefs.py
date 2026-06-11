"""Target-job preferences: free-form description → structured search profile."""

from typing import Any, Literal, Optional

import anthropic
from pydantic import BaseModel

from . import llm

MODEL_PREFS = "claude-opus-4-8"


class SalaryPref(BaseModel):
    floor: Optional[int] = None  # annual amount in `currency`
    target: Optional[int] = None
    currency: Optional[str] = None
    notes: Optional[str] = None


class JobPreferences(BaseModel):
    target_titles: list[str] = []
    seniority: Optional[str] = None
    locations: list[str] = []
    remote_stance: Optional[
        Literal["remote_only", "remote_preferred", "hybrid_ok", "onsite_ok", "flexible"]
    ] = None
    job_types: list[str] = []  # full-time, contract, internship, co-op...
    salary: Optional[SalaryPref] = None
    industries_preferred: list[str] = []
    industries_avoid: list[str] = []
    company_watchlist: list[str] = []
    company_blocklist: list[str] = []
    work_authorization: Optional[str] = None
    dealbreakers: list[str] = []
    soft_preferences: list[str] = []
    keywords_must: list[str] = []
    keywords_exclude: list[str] = []
    notes: list[str] = []
    clarifications_needed: list[str] = []


PARSE_SYSTEM = """\
You convert a candidate's free-form description of the job they want into a structured
search profile that a job-discovery agent will execute daily.

Rules:
- Capture only what they said or what's directly implied. Leave fields empty rather
  than inventing preferences they never expressed.
- salary: convert to annual integers in their currency ("90k" → 90000). A range maps
  to floor = lower bound, target = desired/upper. Note ambiguities in salary.notes.
- locations: as they'd appear in job postings (city, region, country).
- remote_stance: their attitude toward remote/hybrid/onsite work.
- dealbreakers: absolute exclusions stated by the candidate.
  soft_preferences: nice-to-haves.
- keywords_must / keywords_exclude: literal terms a search engine should require or
  filter out in titles/descriptions.
- clarifications_needed: at most 4 short questions, only where the description is
  ambiguous in ways that materially change the search (currency, seniority band,
  commuting radius, etc.).
- Candidate profile context may be provided. Use it ONLY to fill work_authorization
  and location defaults when the description itself doesn't say."""


def parse_preferences(
    client: anthropic.Anthropic, raw_text: str, profile_context: Optional[dict[str, Any]] = None
) -> JobPreferences:
    content = ""
    if profile_context:
        bits = [f"{k}: {v}" for k, v in profile_context.items() if v]
        if bits:
            content += "Candidate profile context:\n" + "\n".join(bits) + "\n\n"
    content += "The candidate's description of what they're looking for:\n\n" + raw_text.strip()
    return llm.parse_call(
        client,
        model=MODEL_PREFS,
        system=PARSE_SYSTEM,
        content=content,
        schema=JobPreferences,
        max_tokens=8000,
    )
