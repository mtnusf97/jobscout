"""Thin Telegram Bot API client (raw HTTPS — no framework needed for our surface)."""

from pathlib import Path
from typing import Any, Optional

import httpx

API = "https://api.telegram.org"


class TgError(Exception):
    pass


def call(token: str, method: str, params: Optional[dict[str, Any]] = None, timeout: float = 35.0) -> Any:
    try:
        response = httpx.post(f"{API}/bot{token}/{method}", json=params or {}, timeout=timeout)
        data = response.json()
    except httpx.HTTPError as exc:
        raise TgError(
            "could not reach api.telegram.org — this network appears to block Telegram "
            "(common on corporate VPNs like Zscaler). It will work when JobScout runs on a "
            f"network or host where Telegram is reachable. [{type(exc).__name__}]"
        ) from exc
    except ValueError as exc:
        raise TgError("Telegram returned a non-JSON response") from exc
    if not data.get("ok"):
        raise TgError(data.get("description") or f"HTTP {response.status_code}")
    return data["result"]


def get_me(token: str) -> dict[str, Any]:
    return call(token, "getMe", timeout=15.0)


def get_updates(token: str, offset: int, poll_seconds: int = 25) -> list[dict[str, Any]]:
    return call(
        token,
        "getUpdates",
        {
            "offset": offset,
            "timeout": poll_seconds,
            "allowed_updates": ["message", "callback_query"],
        },
        timeout=poll_seconds + 10.0,
    )


def send_message(
    token: str,
    chat_id: int,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": True,
    }
    if reply_markup:
        params["reply_markup"] = reply_markup
    return call(token, "sendMessage", params)


def send_document(token: str, chat_id: int, path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise TgError(f"file missing: {file_path.name}")
    try:
        with file_path.open("rb") as fh:
            response = httpx.post(
                f"{API}/bot{token}/sendDocument",
                data={"chat_id": str(chat_id)},
                files={"document": (file_path.name, fh, "application/pdf")},
                timeout=120.0,
            )
        data = response.json()
    except httpx.HTTPError as exc:
        raise TgError(f"network error: {exc}") from exc
    if not data.get("ok"):
        raise TgError(data.get("description") or f"HTTP {response.status_code}")
    return data["result"]


def answer_callback(token: str, callback_id: str, text: str = "") -> None:
    call(token, "answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})
