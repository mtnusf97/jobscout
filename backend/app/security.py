"""Encryption-at-rest for credentials.

A Fernet key is generated once into data/secret.key (0600, gitignored). Losing the key
file means re-entering credentials in the UI — by design, nothing secret lives in git.
"""

import os
from typing import Optional

from cryptography.fernet import Fernet

from .config import settings

_fernet: Optional[Fernet] = None


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        path = settings.secret_key_path
        if not path.exists():
            path.write_bytes(Fernet.generate_key())
            os.chmod(path, 0o600)
        _fernet = Fernet(path.read_bytes())
    return _fernet


def encrypt(value: str) -> bytes:
    return get_fernet().encrypt(value.encode("utf-8"))


def decrypt(blob: bytes) -> str:
    return get_fernet().decrypt(blob).decode("utf-8")


def mask(value: str) -> str:
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:6]}…{value[-4:]}"
