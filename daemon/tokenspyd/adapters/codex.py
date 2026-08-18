from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from .base import Adapter
from ..config import CodexConfig
from ..schema import ProviderSnapshot, Window

logger = logging.getLogger(__name__)

_AUTH_PATH = Path.home() / ".codex" / "auth.json"
_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snap(status: str, error: str | None = None, windows: list[Window] | None = None) -> ProviderSnapshot:
    return ProviderSnapshot(
        id="codex",
        display_name="Codex",
        status=status,
        windows=windows or [],
        last_polled_at=_now(),
        error=error,
    )


def _jwt_is_expired(token: str) -> bool:
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp", 0)
        return exp < datetime.now(timezone.utc).timestamp()
    except Exception:
        return False


def _epoch_to_iso(ts: int | float) -> str:
    if ts > 1e11:
        ts = ts / 1000.0
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_windows(data: dict) -> list[Window]:
    """
    Parse wham/usage response. Field names have shifted over time; try all known variants.
    Real response shape (April 2026):
      rate_limit.primary_window.{used_percent, limit_window_seconds, reset_at}
      rate_limit.secondary_window.{used_percent, limit_window_seconds, reset_at}
    """
    rl = data.get("rate_limit") or data.get("rate_limits") or {}

    # Collect candidate window dicts, tagging them short/long by limit_window_seconds
    candidates: list[dict] = []
    for key in ("primary_window", "five_hour", "five_hour_limit", "five_hour_rate_limit"):
        window = rl.get(key)
        if isinstance(window, dict):
            candidates.append({"_role": "five_hour", **window})
            break

    for key in ("secondary_window", "weekly", "weekly_limit", "weekly_rate_limit"):
        window = rl.get(key)
        if isinstance(window, dict):
            candidates.append({"_role": "seven_day", **window})
            break

    # Fallback: if top-level keys are missing, sort by limit_window_seconds
    if not candidates:
        raw_windows = [v for v in rl.values() if isinstance(v, dict) and "limit_window_seconds" in v]
        raw_windows.sort(key=lambda w: w.get("limit_window_seconds", 0))
        for i, w in enumerate(raw_windows):
            w["_role"] = "five_hour" if i == 0 else "seven_day"
            candidates.append(w)

    windows: list[Window] = []
    for w in candidates:
        role = w.pop("_role", "five_hour")
        win_secs = w.get("limit_window_seconds", 18000 if role == "five_hour" else 604800)
        # The API has changed which window it calls "primary". Prefer the
        # actual duration over that unstable key when it is available.
        if win_secs >= 172800:
            role = "seven_day"
        label = "5h session" if role == "five_hour" else "Weekly"

        # used_pct
        if "used_percent" in w:
            used = float(w["used_percent"])
        elif "percent_left" in w:
            used = 100.0 - float(w["percent_left"])
        elif "remaining_percent" in w:
            used = 100.0 - float(w["remaining_percent"])
        else:
            used = 0.0

        # resets_at
        resets_at: Optional[str] = None
        for ts_key in ("reset_at", "reset_time_ms", "reset_time"):
            if ts_key in w:
                resets_at = _epoch_to_iso(w[ts_key])
                break

        windows.append(Window(
            id=role,
            label=label,
            used_pct=used,
            resets_at=resets_at,
            window_seconds=win_secs,
        ))

    return windows


class CodexAdapter(Adapter):
    id = "codex"
    display_name = "Codex"

    def __init__(self, config: CodexConfig):
        self.config = config

    async def fetch(self) -> ProviderSnapshot:
        if not self.config.enabled:
            return _snap("disabled")

        if not _AUTH_PATH.exists():
            return _snap("auth_missing", "~/.codex/auth.json not found. Run `codex login`.")

        try:
            auth = json.loads(_AUTH_PATH.read_text())
        except Exception as exc:
            return _snap("parse_error", f"Failed to read ~/.codex/auth.json: {exc}")

        tokens = auth.get("tokens") or {}
        access_token = tokens.get("access_token")
        account_id = tokens.get("account_id")

        if not access_token or not account_id:
            return _snap("auth_missing", "Codex token missing — run `codex login`.")

        if _jwt_is_expired(access_token):
            return _snap(
                "auth_expired",
                "Codex access token has expired. The next `codex` invocation will refresh it automatically.",
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "ChatGPT-Account-Id": account_id,
            "Accept": "application/json",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        }

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(_USAGE_URL, headers=headers, timeout=30)
        except httpx.NetworkError as exc:
            return _snap("network_error", str(exc))

        if r.status_code == 401:
            return _snap("auth_expired", "Codex token rejected (401). Run any `codex` command to refresh.")
        if r.status_code == 403:
            return _snap("auth_missing", "Codex access denied (403). Run `codex login`.")
        if r.status_code != 200:
            return _snap("parse_error", f"Unexpected HTTP {r.status_code} from Codex usage endpoint.")

        try:
            windows = _parse_windows(r.json())
            return _snap("ok", windows=windows)
        except Exception as exc:
            logger.exception("Failed to parse Codex response")
            return _snap("parse_error", f"Response parse error: {exc}")
