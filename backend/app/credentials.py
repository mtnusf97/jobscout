"""Credential registry + validation + encrypted storage.

Every key the app ever needs is declared here so the Settings UI can render itself:
what the key is for, where to get it, which roadmap phase needs it, and how it is
validated ("live" = a real test call on save, "format" = shape check now, validated
live when the feature that uses it lands).
"""

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

from . import models, schemas
from .security import decrypt, encrypt, mask


@dataclass(frozen=True)
class CredentialSpec:
    name: str
    label: str
    description: str
    help_url: str
    phase: int  # roadmap phase where it becomes needed
    validation: str  # "live" | "format"


REGISTRY: list[CredentialSpec] = [
    CredentialSpec(
        name="anthropic_api_key",
        label="Anthropic API key",
        description=(
            "Powers every LLM step: document extraction, job scoring, resume tailoring, "
            "cover letters, and the truthfulness audit. Required before anything else."
        ),
        help_url="https://platform.claude.com/",
        phase=0,
        validation="live",
    ),
    CredentialSpec(
        name="rapidapi_jsearch_key",
        label="RapidAPI key (JSearch)",
        description=(
            "Job discovery via JSearch, the Google-for-Jobs aggregator (carries LinkedIn/"
            "Indeed/Glassdoor-syndicated postings). Needed at Phase 3 — discovery."
        ),
        help_url="https://rapidapi.com/",
        phase=3,
        validation="format",
    ),
    CredentialSpec(
        name="adzuna_app_id",
        label="Adzuna app ID",
        description="Job discovery + salary data via Adzuna (free tier). Needed at Phase 3.",
        help_url="https://developer.adzuna.com/",
        phase=3,
        validation="format",
    ),
    CredentialSpec(
        name="adzuna_app_key",
        label="Adzuna app key",
        description="Pairs with the Adzuna app ID. Needed at Phase 3.",
        help_url="https://developer.adzuna.com/",
        phase=3,
        validation="format",
    ),
    CredentialSpec(
        name="jooble_api_key",
        label="Jooble API key (optional)",
        description="Extra discovery coverage via Jooble. Optional, Phase 3.",
        help_url="https://jooble.org/api/about",
        phase=3,
        validation="format",
    ),
]

_SPECS = {spec.name: spec for spec in REGISTRY}


# --- validators ---------------------------------------------------------------


def _validate_anthropic_key(value: str) -> tuple[bool, str]:
    import anthropic

    client = anthropic.Anthropic(api_key=value, max_retries=0, timeout=30.0)
    try:
        client.models.list()
        # models.list is free and proves auth only — a 1-token inference probe also
        # proves the account has credits (costs a fraction of a cent).
        client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True, "Validated live against the Anthropic API (auth + credits OK)."
    except anthropic.AuthenticationError:
        return False, "Anthropic rejected this key (authentication failed). Check for typos."
    except anthropic.PermissionDeniedError:
        return False, "Key authenticated but lacks permission — check its workspace/scopes."
    except anthropic.APIConnectionError:
        return False, "Could not reach the Anthropic API — check your network and retry."
    except anthropic.BadRequestError as exc:
        if "credit balance" in str(exc).lower():
            return False, (
                "Key is valid, but the Anthropic account has no API credits — add credits "
                "under Plans & Billing on platform.claude.com, then re-validate."
            )
        return False, f"Anthropic rejected the validation request: {str(exc)[:200]}"
    except anthropic.APIStatusError as exc:
        return False, f"Unexpected Anthropic API response (HTTP {exc.status_code})."


_LIVE_VALIDATORS: dict[str, Callable[[str], tuple[bool, str]]] = {
    "anthropic_api_key": _validate_anthropic_key,
}


def _format_check(value: str) -> tuple[bool, str]:
    if len(value.strip()) < 8 or any(ch.isspace() for ch in value.strip()):
        return False, "That doesn't look like a key (too short or contains whitespace)."
    return True, "Saved. Format looks right — it will be validated live when its feature lands."


# --- service ------------------------------------------------------------------


def _get_row(db: Session, name: str) -> Optional[models.Credential]:
    return (
        db.query(models.Credential)
        .filter(
            models.Credential.scope == "instance",
            models.Credential.profile_id.is_(None),
            models.Credential.name == name,
        )
        .one_or_none()
    )


def _state(spec: CredentialSpec, row: Optional[models.Credential]) -> schemas.CredentialStateOut:
    return schemas.CredentialStateOut(
        name=spec.name,
        label=spec.label,
        description=spec.description,
        help_url=spec.help_url,
        phase=spec.phase,
        validation=spec.validation,  # type: ignore[arg-type]
        is_set=row is not None,
        masked_value=mask(decrypt(row.value_enc)) if row is not None else None,
        last_validated_at=row.last_validated_at if row is not None else None,
    )


def list_states(db: Session) -> list[schemas.CredentialStateOut]:
    return [_state(spec, _get_row(db, spec.name)) for spec in REGISTRY]


def get_value(db: Session, name: str) -> Optional[str]:
    """Decrypted value for internal use (LLM calls, source modules). Never exposed via API."""
    row = _get_row(db, name)
    return decrypt(row.value_enc) if row is not None else None


def set_credential(db: Session, name: str, value: str) -> schemas.CredentialResultOut:
    spec = _SPECS.get(name)
    if spec is None:
        raise KeyError(name)
    value = value.strip()

    if spec.validation == "live":
        valid, message = _LIVE_VALIDATORS[name](value)
    else:
        valid, message = _format_check(value)

    row = _get_row(db, name)
    if row is None:
        row = models.Credential(scope="instance", profile_id=None, name=name, value_enc=encrypt(value))
        db.add(row)
    else:
        row.value_enc = encrypt(value)
    row.last_validated_at = models.utcnow() if (valid and spec.validation == "live") else None
    db.commit()

    return schemas.CredentialResultOut(state=_state(spec, row), valid=valid, message=message)


def revalidate(db: Session, name: str) -> schemas.CredentialResultOut:
    spec = _SPECS.get(name)
    if spec is None:
        raise KeyError(name)
    row = _get_row(db, name)
    if row is None:
        raise LookupError(name)

    value = decrypt(row.value_enc)
    if spec.validation == "live":
        valid, message = _LIVE_VALIDATORS[name](value)
    else:
        valid, message = _format_check(value)
    row.last_validated_at = models.utcnow() if (valid and spec.validation == "live") else None
    db.commit()

    return schemas.CredentialResultOut(state=_state(spec, row), valid=valid, message=message)


def delete_credential(db: Session, name: str) -> bool:
    if name not in _SPECS:
        raise KeyError(name)
    row = _get_row(db, name)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
