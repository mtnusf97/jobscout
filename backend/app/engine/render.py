"""Typst rendering: tailored resume / cover letter → ATS-safe single-column PDF."""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

_ESC_RE = re.compile(r"([\\#$*_\[\]<>@`~])")


def esc(value: Optional[str]) -> str:
    return _ESC_RE.sub(r"\\\1", value or "")


def _typst_bin() -> str:
    binary = shutil.which("typst") or "/opt/homebrew/bin/typst"
    if not Path(binary).exists():
        raise RuntimeError("Typst is not installed (brew install typst).")
    return binary


# Font-fit ladder: shrink the résumé a notch at a time (floor ~8.6pt, still readable) to
# pull a slightly-too-long résumé onto the target page count without calling the LLM.
_SCALES = (1.0, 0.96, 0.92, 0.88)

# Invisible marker Typst reports the final page count for (read back by page_count()).
_PAGECOUNT_META = "\n#context [#metadata(counter(page).final().first()) <pagecount>]\n"


def _prelude(scale: float = 1.0) -> str:
    return (
        '#set page(paper: "us-letter", margin: (x: 1.5cm, y: 1.3cm))\n'
        f'#set text(font: ("Helvetica", "Arial", "Liberation Sans"), size: {round(9.8 * scale, 2)}pt, fill: rgb("#1a1a1a"))\n'
        "#set par(justify: false, leading: 0.52em)\n"
        '#show link: it => text(fill: rgb("#1a4f8f"))[#it]\n'
        "#let sect(title) = {\n"
        f"  v({round(7 * scale, 2)}pt)\n"
        f'  text(size: {round(10 * scale, 2)}pt, weight: "bold", tracking: 0.07em)[#upper(title)]\n'
        "  v(-5pt)\n"
        '  line(length: 100%, stroke: 0.6pt + rgb("#b0b0b0"))\n'
        "  v(0pt)\n"
        "}\n"
    )


def _contact(profile_body: dict[str, Any]) -> dict[str, str]:
    emails = profile_body.get("emails") or []
    phones = profile_body.get("phones") or []
    links = profile_body.get("links") or []
    return {
        "name": profile_body.get("full_name") or "Candidate",
        "line": " · ".join(
            part
            for part in [
                profile_body.get("location"),
                emails[0] if emails else None,
                phones[0] if phones else None,
                *links[:2],
            ]
            if part
        ),
    }


def _header(contact: dict[str, str]) -> str:
    return (
        f'#align(center)[#text(size: 16.5pt, weight: "bold")[{esc(contact["name"])}]]\n'
        f'#align(center)[#text(size: 8.8pt, fill: rgb("#444444"))[{esc(contact["line"])}]]\n'
    )


# Reorderable résumé sections. The model can permute these via `section_order` (driven by
# the design box, e.g. "keep skills at the end"); anything it omits keeps the default order.
_DEFAULT_SECTION_ORDER = ("summary", "skills", "experience", "projects", "education")
_SECTION_ALIASES = {
    "roles": "experience",
    "work": "experience",
    "work experience": "experience",
    "publications": "projects",
    "projects & publications": "projects",
    "selected projects & publications": "projects",
}


def resume_typ(profile_body: dict[str, Any], tailored: dict[str, Any], scale: float = 1.0) -> str:
    contact = _contact(profile_body)
    parts = [_prelude(scale), _header(contact)]

    if tailored.get("headline"):
        parts.append(
            f'#align(center)[#text(size: {round(10 * scale, 2)}pt, weight: "medium", fill: rgb("#333333"))'
            f"[{esc(tailored['headline'])}]]\n"
        )

    sections: dict[str, str] = {}

    if tailored.get("summary"):
        sections["summary"] = '#sect("Summary")\n' + esc(tailored["summary"]) + "\n"

    skills = tailored.get("skills") or []
    if skills:
        buf = ['#sect("Skills")\n']
        for group in skills:
            buf.append(f"*{esc(group.get('name'))}:* {esc(', '.join(group.get('items') or []))} \\\n")
        sections["skills"] = "".join(buf)

    roles = tailored.get("roles") or []
    if roles:
        buf = ['#sect("Experience")\n']
        for role in roles:
            dates = " – ".join(d for d in [role.get("start"), role.get("end")] if d)
            where = " · ".join(x for x in [role.get("location")] if x)
            right = esc(" · ".join(x for x in [where, dates] if x))
            buf.append(
                "#grid(columns: (1fr, auto), gutter: 6pt, "
                f"[*{esc(role.get('title'))}* — {esc(role.get('company'))}], "
                f'[#text(size: 8.8pt, fill: rgb("#555555"))[{right}]])\n'
            )
            for bullet in role.get("bullets") or []:
                buf.append(f"- {esc(bullet.get('text'))}\n")
            buf.append(f"#v({round(3 * scale, 2)}pt)\n")
        sections["experience"] = "".join(buf)

    projects = tailored.get("projects") or []
    if projects:
        buf = ['#sect("Selected Projects & Publications")\n']
        for project in projects:
            meta = f' #text(size: 8.8pt, fill: rgb("#555555"))[· {esc(project.get("meta"))}]' if project.get("meta") else ""
            buf.append(f"*{esc(project.get('name'))}*{meta} \\\n")
            for bullet in project.get("bullets") or []:
                buf.append(f"- {esc(bullet.get('text'))}\n")
        sections["projects"] = "".join(buf)

    # Education from the TAILORED result when the model set it (so design instructions like
    # "leave off my bachelor" take effect); fall back to the master profile only when the
    # model left the field untouched (None), never when it deliberately returned [].
    education = tailored.get("education")
    if education is None:
        education = profile_body.get("education") or []
    if education:
        buf = ['#sect("Education")\n']
        for ed in education:
            dates = " – ".join(d for d in [ed.get("start"), ed.get("end")] if d)
            degree = ", ".join(x for x in [ed.get("degree"), ed.get("field")] if x)
            gpa = f" · GPA {esc(ed.get('gpa'))}" if ed.get("gpa") else ""
            buf.append(
                "#grid(columns: (1fr, auto), gutter: 6pt, "
                f"[*{esc(degree)}* — {esc(ed.get('institution'))}{gpa}], "
                f'[#text(size: 8.8pt, fill: rgb("#555555"))[{esc(dates)}]])\n'
            )
        sections["education"] = "".join(buf)

    # Emit in the model's requested order (design-driven), then anything it didn't list
    # in the default order. Unknown/duplicate keys are ignored.
    requested = [
        _SECTION_ALIASES.get(k, k)
        for k in (str(s).strip().lower() for s in (tailored.get("section_order") or []))
    ]
    emitted: set[str] = set()
    for key in [*requested, *_DEFAULT_SECTION_ORDER]:
        if key in sections and key not in emitted:
            parts.append(sections[key])
            emitted.add(key)

    parts.append(_PAGECOUNT_META)
    return "".join(parts)


def page_count(typ_source: str) -> int:
    """Total rendered page count via a Typst metadata query. Returns 0 if unmeasurable."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".typ", delete=False, encoding="utf-8") as fh:
        fh.write(typ_source)
        path = Path(fh.name)
    try:
        result = subprocess.run(
            [_typst_bin(), "query", str(path), "<pagecount>", "--field", "value", "--one"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = result.stdout.strip()
        return int(out) if result.returncode == 0 and out.isdigit() else 0
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0
    finally:
        path.unlink(missing_ok=True)


def fit_resume(
    profile_body: dict[str, Any], tailored: dict[str, Any], target: Optional[int]
) -> tuple[str, int]:
    """Return (typst_source, page_count), shrinking the font a notch at a time to reach
    `target` pages when possible — no LLM involved. target falsy → no fitting (scale 1.0)."""
    if not target:
        src = resume_typ(profile_body, tailored, 1.0)
        return src, page_count(src)
    best: Optional[tuple[str, int]] = None
    for scale in _SCALES:
        src = resume_typ(profile_body, tailored, scale)
        pages = page_count(src)
        if pages == 0:  # measurement failed — use as-is, don't fight it
            return src, 0
        if pages <= target:
            return src, pages
        if best is None or pages < best[1]:
            best = (src, pages)
    return best if best is not None else (resume_typ(profile_body, tailored, 1.0), 0)


def letter_typ(profile_body: dict[str, Any], job: dict[str, str], body_text: str) -> str:
    contact = _contact(profile_body)
    paragraphs = [p.strip() for p in (body_text or "").split("\n\n") if p.strip()]
    parts = [
        _prelude(),
        _header(contact),
        "#v(14pt)\n",
        f"*{esc(job.get('company'))}* — re: {esc(job.get('title'))}\n#v(8pt)\n",
        f"Dear {esc(job.get('company'))} Hiring Team,\n#v(2pt)\n",
    ]
    for paragraph in paragraphs:
        parts.append(esc(paragraph) + "\n#v(6pt)\n")
    parts.append(f"#v(4pt)\nSincerely, \\\n{esc(contact['name'])}\n")
    return "".join(parts)


def compile_pdf(typ_source: str, out_pdf: Path) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    typ_path = out_pdf.with_suffix(".typ")
    typ_path.write_text(typ_source, encoding="utf-8")
    result = subprocess.run(
        [_typst_bin(), "compile", str(typ_path), str(out_pdf)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Typst compile failed: {result.stderr[-600:]}")


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")[:60] or "file"
