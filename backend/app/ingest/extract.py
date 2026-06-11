"""Per-document fact extraction via Claude's multimodal understanding.

PDFs go in as native document blocks, images via vision, text as-is, DOCX converted
to markdown first. One extraction call per document → ExtractedFacts.
"""

import base64
from pathlib import Path
from typing import Any

import anthropic

from .. import llm
from .schemas import ExtractedFacts

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".gif"}

_IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

MAX_TEXT_CHARS = 200_000

EXTRACT_SYSTEM = """\
You extract structured career facts from ONE document, for a job-application assistant
that will later tailor resumes from these facts.

Rules:
- Extract only what the document actually contains. Never invent, infer numbers, or embellish.
- Preserve quantified achievements exactly (percentages, counts, scales, dollar amounts).
- Keep bullet substance close to verbatim; only clean up OCR/layout artifacts.
- Dates: "YYYY-MM" when determinable, "present" for ongoing, omit when unknown.
- Classify doc_type. For cover letters, also fill voice_notes: motivations, stories,
  phrasings, and tone worth reusing in future cover letters (these are gold — be generous).
- other_facts: valuable items that fit nowhere else (work authorization, availability,
  awards context, interests that signal fit).
- If the document is not about a person's career at all, still return the schema with
  doc_type "other" and whatever little applies."""


def content_blocks_for(path: Path, mime: str, filename: str) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        return [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": data},
            }
        ]
    if suffix in _IMAGE_MEDIA:
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        return [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": _IMAGE_MEDIA[suffix], "data": data},
            }
        ]
    if suffix == ".docx":
        import mammoth

        with path.open("rb") as fh:
            markdown = mammoth.convert_to_markdown(fh).value
        return [{"type": "text", "text": f"[Converted from DOCX: {filename}]\n\n{markdown[:MAX_TEXT_CHARS]}"}]
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return [{"type": "text", "text": f"[Text file: {filename}]\n\n{text[:MAX_TEXT_CHARS]}"}]
    raise ValueError(f"Unsupported file type: {suffix}")


def extract_document(
    client: anthropic.Anthropic, path: Path, mime: str, filename: str
) -> ExtractedFacts:
    blocks = content_blocks_for(path, mime, filename)
    blocks.append(
        {
            "type": "text",
            "text": f'Extract the career facts from this document (filename: "{filename}").',
        }
    )
    return llm.parse_call(
        client,
        model=llm.MODEL_EXTRACT,
        system=EXTRACT_SYSTEM,
        content=blocks,
        schema=ExtractedFacts,
    )
