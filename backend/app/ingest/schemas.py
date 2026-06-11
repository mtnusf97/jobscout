"""Pydantic schemas for the LLM steps of onboarding (extraction → merge → refine).

These are structured-output schemas: keep them JSON-schema friendly (no recursion,
no numeric constraints).
"""

from typing import Literal, Optional

from pydantic import BaseModel

# --- per-document extraction ----------------------------------------------------


class ExtractedRole(BaseModel):
    company: str
    title: str
    location: Optional[str] = None
    start: Optional[str] = None  # "YYYY-MM" when determinable
    end: Optional[str] = None  # "YYYY-MM" or "present"
    bullets: list[str] = []


class ExtractedEducation(BaseModel):
    institution: str
    degree: str
    field: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    gpa: Optional[str] = None
    notes: list[str] = []


class ExtractedProject(BaseModel):
    name: str
    organization: Optional[str] = None
    dates: Optional[str] = None
    bullets: list[str] = []
    outcome: Optional[str] = None  # e.g. resulting publication, award, deployment


class ExtractedFacts(BaseModel):
    doc_type: Literal[
        "resume", "cv", "cover_letter", "narrative", "profile_screenshot", "other"
    ]
    full_name: Optional[str] = None
    emails: list[str] = []
    phones: list[str] = []
    links: list[str] = []
    location: Optional[str] = None
    summary: Optional[str] = None
    roles: list[ExtractedRole] = []
    education: list[ExtractedEducation] = []
    projects: list[ExtractedProject] = []
    publications: list[str] = []
    skills: list[str] = []
    certifications: list[str] = []
    awards: list[str] = []
    languages: list[str] = []
    voice_notes: list[str] = []
    other_facts: list[str] = []


# --- merged master profile ------------------------------------------------------


class PBullet(BaseModel):
    text: str
    source_doc_ids: list[str] = []  # document aliases ("D1") or "interview"


class PRole(BaseModel):
    company: str
    title: str
    location: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    bullets: list[PBullet] = []
    source_doc_ids: list[str] = []


class PEducation(BaseModel):
    institution: str
    degree: str
    field: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    gpa: Optional[str] = None
    notes: list[str] = []
    source_doc_ids: list[str] = []


class PProject(BaseModel):
    name: str
    organization: Optional[str] = None
    dates: Optional[str] = None
    bullets: list[PBullet] = []
    outcome: Optional[str] = None
    source_doc_ids: list[str] = []


class PSkillGroup(BaseModel):
    name: str
    items: list[str] = []


class MasterProfile(BaseModel):
    full_name: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    emails: list[str] = []
    phones: list[str] = []
    links: list[str] = []
    summary: Optional[str] = None
    roles: list[PRole] = []
    education: list[PEducation] = []
    projects: list[PProject] = []
    publications: list[PBullet] = []
    skills: list[PSkillGroup] = []
    certifications: list[str] = []
    awards: list[str] = []
    languages: list[str] = []
    voice_notes: list[str] = []
    other_facts: list[PBullet] = []
    narrative: Optional[str] = None


class OpenQuestion(BaseModel):
    question: str
    reason: str


class MergeResult(BaseModel):
    profile: MasterProfile
    open_questions: list[OpenQuestion] = []
    merge_notes: list[str] = []


class RefineResult(BaseModel):
    profile: MasterProfile
    resolution_notes: list[str] = []
