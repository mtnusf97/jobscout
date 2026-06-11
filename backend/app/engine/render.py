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


_PRELUDE = """\
#set page(paper: "us-letter", margin: (x: 1.5cm, y: 1.3cm))
#set text(font: ("Helvetica", "Arial", "Liberation Sans"), size: 9.8pt, fill: rgb("#1a1a1a"))
#set par(justify: false, leading: 0.52em)
#show link: it => text(fill: rgb("#1a4f8f"))[#it]
#let sect(title) = {
  v(7pt)
  text(size: 10pt, weight: "bold", tracking: 0.07em)[#upper(title)]
  v(-5pt)
  line(length: 100%, stroke: 0.6pt + rgb("#b0b0b0"))
  v(0pt)
}
"""


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


def resume_typ(profile_body: dict[str, Any], tailored: dict[str, Any]) -> str:
    contact = _contact(profile_body)
    parts = [_PRELUDE, _header(contact)]

    if tailored.get("headline"):
        parts.append(
            f'#align(center)[#text(size: 10pt, weight: "medium", fill: rgb("#333333"))'
            f"[{esc(tailored['headline'])}]]\n"
        )
    if tailored.get("summary"):
        parts.append('#sect("Summary")\n' + esc(tailored["summary"]) + "\n")

    skills = tailored.get("skills") or []
    if skills:
        parts.append('#sect("Skills")\n')
        for group in skills:
            parts.append(f"*{esc(group.get('name'))}:* {esc(', '.join(group.get('items') or []))} \\\n")

    roles = tailored.get("roles") or []
    if roles:
        parts.append('#sect("Experience")\n')
        for role in roles:
            dates = " – ".join(d for d in [role.get("start"), role.get("end")] if d)
            where = " · ".join(x for x in [role.get("location")] if x)
            right = esc(" · ".join(x for x in [where, dates] if x))
            parts.append(
                "#grid(columns: (1fr, auto), gutter: 6pt, "
                f"[*{esc(role.get('title'))}* — {esc(role.get('company'))}], "
                f'[#text(size: 8.8pt, fill: rgb("#555555"))[{right}]])\n'
            )
            for bullet in role.get("bullets") or []:
                parts.append(f"- {esc(bullet.get('text'))}\n")
            parts.append("#v(3pt)\n")

    projects = tailored.get("projects") or []
    if projects:
        parts.append('#sect("Selected Projects & Publications")\n')
        for project in projects:
            meta = f' #text(size: 8.8pt, fill: rgb("#555555"))[· {esc(project.get("meta"))}]' if project.get("meta") else ""
            parts.append(f"*{esc(project.get('name'))}*{meta} \\\n")
            for bullet in project.get("bullets") or []:
                parts.append(f"- {esc(bullet.get('text'))}\n")

    education = profile_body.get("education") or []
    if education:
        parts.append('#sect("Education")\n')
        for ed in education:
            dates = " – ".join(d for d in [ed.get("start"), ed.get("end")] if d)
            degree = ", ".join(x for x in [ed.get("degree"), ed.get("field")] if x)
            gpa = f" · GPA {esc(ed.get('gpa'))}" if ed.get("gpa") else ""
            parts.append(
                "#grid(columns: (1fr, auto), gutter: 6pt, "
                f"[*{esc(degree)}* — {esc(ed.get('institution'))}{gpa}], "
                f'[#text(size: 8.8pt, fill: rgb("#555555"))[{esc(dates)}]])\n'
            )
    return "".join(parts)


def letter_typ(profile_body: dict[str, Any], job: dict[str, str], body_text: str) -> str:
    contact = _contact(profile_body)
    paragraphs = [p.strip() for p in (body_text or "").split("\n\n") if p.strip()]
    parts = [
        _PRELUDE,
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
