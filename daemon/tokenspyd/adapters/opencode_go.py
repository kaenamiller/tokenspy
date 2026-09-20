from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from .base import Adapter
from ..config import OpenCodeGoConfig
from ..schema import ProviderSnapshot, Window

logger = logging.getLogger(__name__)

_USAGE_URL = "https://opencode.ai/zen/go/v1/usage"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_string() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _snap(status: str, error: str | None = None, windows: list[Window] | None = None) -> ProviderSnapshot:
    return ProviderSnapshot(
        id="opencode-go",
        display_name="OpenCode Go",
        status=status,
        windows=windows or [],
        last_polled_at=_now_string(),
        error=error,
    )


def _auth_path(config: OpenCodeGoConfig) -> Path:
    if config.auth_json_path:
        return Path(os.path.expanduser(config.auth_json_path))
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "opencode" / "auth.json"


def _reset_at(window: dict) -> Optional[str]:
    reset_in_sec = window.get("resetInSec", window.get("reset_in_seconds"))
    if reset_in_sec is not None:
        return (_now() + timedelta(seconds=float(reset_in_sec))).strftime("%Y-%m-%dT%H:%M:%SZ")

    reset_at = window.get("resetsAt", window.get("reset_at"))
    if reset_at is None:
        return None
    if isinstance(reset_at, (int, float)):
        if reset_at > 1e11:
            reset_at /= 1000.0
        return datetime.fromtimestamp(reset_at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(reset_at)


def _parse_windows(data: dict) -> list[Window]:
    windows: list[Window] = []
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else data
    definitions = (
        (("rollingUsage", "rolling"), "rolling", "Rolling", 18000),
        (("weeklyUsage", "weekly"), "weekly", "Weekly", 604800),
        (("monthlyUsage", "monthly"), "monthly", "Monthly", 2592000),
    )

    for keys, window_id, label, seconds in definitions:
        raw = next((usage.get(key) for key in keys if isinstance(usage.get(key), dict)), None)
        if not isinstance(raw, dict):
            continue
        percent = raw.get("usagePercent", raw.get("percent", raw.get("usage_percent")))
        if percent is None:
            continue
        windows.append(Window(
            id=window_id,
            label=label,
            used_pct=float(percent),
            resets_at=_reset_at(raw),
            window_seconds=seconds,
        ))

    return windows


class OpenCodeGoAdapter(Adapter):
    id = "opencode-go"
    display_name = "OpenCode Go"

    def __init__(self, config: OpenCodeGoConfig):
        self.config = config

    async def fetch(self) -> ProviderSnapshot:
        if not self.config.enabled:
            return _snap("disabled")

        auth_path = _auth_path(self.config)
        if not auth_path.exists():
            return _snap("auth_missing", f"{auth_path} not found. Run `opencode auth login`.")

        try:
            auth = json.loads(auth_path.read_text())
        except Exception as exc:
            return _snap("parse_error", f"Failed to read {auth_path}: {exc}")

        credentials = auth.get("opencode-go") if isinstance(auth, dict) else None
        api_key = credentials.get("key") if isinstance(credentials, dict) else None
        if not api_key:
            return _snap("auth_missing", "OpenCode Go API key not found. Run `opencode auth login`.")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    _USAGE_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Accept": "application/json",
                    },
                    timeout=30,
                )
        except httpx.RequestError as exc:
            return _snap("network_error", str(exc))

        if response.status_code == 401:
            return _snap("auth_expired", "OpenCode Go API key rejected (401). Run `opencode auth login`.")
        if response.status_code == 403:
            return _snap("auth_missing", "OpenCode Go subscription is not active for this API key.")
        if response.status_code != 200:
            return _snap("parse_error", f"Unexpected HTTP {response.status_code} from OpenCode Go usage endpoint.")

        try:
            data = response.json()
            windows = _parse_windows(data)
            if not windows:
                return _snap("parse_error", "OpenCode Go usage response contained no usage windows.")
            return _snap("ok", windows=windows)
        except Exception as exc:
            logger.exception("Failed to parse OpenCode Go response")
            return _snap("parse_error", f"Response parse error: {exc}")
