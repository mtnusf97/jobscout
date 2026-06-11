"""Merge per-document extractions into the master profile; refine it with interview answers."""

import json
from typing import Any

import anthropic

from .. import llm
from .schemas import MergeResult, RefineResult

MERGE_SYSTEM = """\
You merge per-document career extractions into ONE master profile — the single source
of truth a resume-tailoring agent will select from later. The candidate will review it.

Rules:
- Superset, not summary: keep every distinct bullet and fact. Merge near-duplicates,
  keeping the most specific, metric-rich wording.
- Same company with overlapping or adjacent dates = the same role; union its bullets.
  A promotion (new title, same company) stays a separate role.
- Provenance: tag every item's source_doc_ids with the document ids it came from
  (e.g. ["D1","D3"]). This powers a truthfulness audit later — be accurate.
- Never invent. When documents conflict (dates, titles, GPA, numbers), prefer the more
  recent / more detailed document AND add an open_question asking the candidate to confirm.
- open_questions: at most 8, ordered by value. Cover: conflicts between documents;
  roles or projects with no quantified outcomes; missing dates; missing contact info;
  work authorization / location constraints if absent; unexplained gaps > 6 months.
  Each question is ONE direct question to the candidate; reason = one sentence on why
  it matters for job applications.
- skills: group into 3–6 named groups (e.g. "Programming", "ML & Data", "Tools & Infra").
- headline: one line describing the candidate (e.g. "Computational neuroscience PhD
  candidate & ML engineer").
- narrative: 150–300 words, third person, the career arc and strongest selling points.
- voice_notes: carry over the cover-letter voice material.
- summary: 2–4 sentence professional summary suitable as a resume top section."""

REFINE_SYSTEM = """\
You update a master career profile with the candidate's own interview answers.

Rules:
- The candidate is the authority: their answers override conflicting earlier data.
- Work every informative answer into the profile as facts (new bullets, corrected dates,
  filled contact/authorization fields, richer metrics). Tag content added or changed this
  way with source_doc_ids ["interview"].
- If an answer says "skip" or contains no information, change nothing for it.
- Keep everything else exactly as it is — do not drop, rewrite, or re-tag unrelated content.
- resolution_notes: one line per answer describing what changed (or "no change")."""


def merge_documents(
    client: anthropic.Anthropic, doc_payloads: list[dict[str, Any]]
) -> MergeResult:
    """doc_payloads: [{"id": "D1", "filename": ..., "doc_type": ..., "facts": {...}}, ...]"""
    content = (
        "Per-document extractions to merge:\n\n```json\n"
        + json.dumps(doc_payloads, ensure_ascii=False, indent=1)
        + "\n```\n\nMerge these into the master profile."
    )
    return llm.parse_call(
        client,
        model=llm.MODEL_MERGE,
        system=MERGE_SYSTEM,
        content=content,
        schema=MergeResult,
        thinking=True,
    )


def refine_profile(
    client: anthropic.Anthropic,
    profile_body: dict[str, Any],
    answers: list[dict[str, str]],
) -> RefineResult:
    """answers: [{"question": ..., "answer": ...}, ...]"""
    content = (
        "Current master profile:\n\n```json\n"
        + json.dumps(profile_body, ensure_ascii=False, indent=1)
        + "\n```\n\nThe candidate's interview answers:\n\n```json\n"
        + json.dumps(answers, ensure_ascii=False, indent=1)
        + "\n```\n\nApply the answers and return the updated profile."
    )
    return llm.parse_call(
        client,
        model=llm.MODEL_REFINE,
        system=REFINE_SYSTEM,
        content=content,
        schema=RefineResult,
        thinking=True,
    )
