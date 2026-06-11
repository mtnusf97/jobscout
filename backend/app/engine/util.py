"""Small helpers shared across the discovery engine."""

import hashlib
import html
import re
from datetime import datetime, timezone
from typing import Any, Optional

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    if "<" in text:
        text = html.unescape(text)  # Greenhouse double-escapes content
        text = _SCRIPT_RE.sub(" ", text)
        text = re.sub(r"<(br|/p|/li|/div|/h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
        text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:  # epoch millis
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, OSError, OverflowError):
        return None


def norm(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower()).strip()


def dedupe_key(company: str, title: str, location: Optional[str]) -> str:
    city = norm((location or "").split(",")[0])
    base = f"{norm(company)}|{norm(title)}|{city}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def jd_hash(description: str) -> str:
    normalized = re.sub(r"\s+", " ", (description or "").lower())[:20000]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def canonical_url(url: str) -> str:
    return (url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")


_GENERIC_TITLE_TOKENS = {"senior", "junior", "staff", "sr", "jr", "mid", "level", "ii", "iii"}


def relevance_tokens(titles: list[str], keywords_must: list[str]) -> set[str]:
    tokens: set[str] = set()
    for phrase in [*titles, *keywords_must]:
        for token in norm(phrase).split():
            if len(token) >= 2 and token not in _GENERIC_TITLE_TOKENS:
                tokens.add(token)
    return tokens


def title_is_relevant(title: str, tokens: set[str]) -> bool:
    if not tokens:
        return True
    title_tokens = set(norm(title).split())
    return bool(title_tokens & tokens)
