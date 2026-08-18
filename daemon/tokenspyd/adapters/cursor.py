from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from .base import Adapter
from ..config import CursorConfig
from ..schema import ProviderSnapshot, Window

logger = logging.getLogger(__name__)

_DASHBOARD_BASE = "https://api2.cursor.sh/aiserver.v1.DashboardService"
_CONNECT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Connect-Protocol-Version": "1",
    "x-cursor-client-type": "cli",
    "x-cursor-client-version": "cli-tokenspyd",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snap(status: str, error: str | None = None, windows: list[Window] | None = None) -> ProviderSnapshot:
    return ProviderSnapshot(
        id="cursor",
        display_name="Cursor",
        status=status,
        windows=windows or [],
        last_polled_at=_now(),
        error=error,
    )


def _default_auth_json_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Cursor" / "auth.json"
    if sys.platform == "darwin":
        return Path.home() / ".cursor" / "auth.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "cursor" / "auth.json"


def _read_access_token(auth_path: Path) -> Optional[str]:
    """Read accessToken from cursor-agent auth.json (same source as BB)."""
    if not auth_path.exists():
        return None
    try:
        data = json.loads(auth_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to read Cursor auth.json: %s", exc)
        return None
    token = data.get("accessToken")
    return token if isinstance(token, str) and token else None


def _iso_or_epoch(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        if value.isdigit():
            ts = float(value)
            if ts > 1e11:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            dt = datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return value
    ts = float(value)
    if ts > 1e11:
        ts /= 1000.0
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_windows(data: dict) -> list[Window]:
    """
    Response shape from api2.cursor.sh GetCurrentPeriodUsage:
      billingCycleEnd: epoch-ms string
      planUsage.autoPercentUsed / apiPercentUsed / totalPercentUsed
      spendLimitUsage.{individual,overall,pooled}Limit/Used
    """
    windows: list[Window] = []
    resets_at = _iso_or_epoch(data.get("billingCycleEnd") or data.get("endOfPeriod"))
    plan = data.get("planUsage") or {}

    auto_pct = plan.get("autoPercentUsed")
    if auto_pct is not None:
        windows.append(Window(
            id="auto",
            label="Auto",
            used_pct=float(auto_pct),
            resets_at=resets_at,
            window_seconds=2592000,
        ))

    api_pct = plan.get("apiPercentUsed")
    if api_pct is not None:
        windows.append(Window(
            id="api",
            label="API",
            used_pct=float(api_pct),
            resets_at=resets_at,
            window_seconds=2592000,
        ))

    if not windows:
        total_pct = plan.get("totalPercentUsed")
        if total_pct is not None:
            windows.append(Window(
                id="plan",
                label="Plan usage",
                used_pct=float(total_pct),
                resets_at=resets_at,
                window_seconds=2592000,
            ))

    spend = data.get("spendLimitUsage") or {}
    on_demand = None
    if spend.get("overallLimit") is not None:
        on_demand = {
            "limit": spend.get("overallLimit"),
            "used": spend.get("overallUsed") or 0,
        }
    elif spend.get("individualLimit") is not None:
        on_demand = {
            "limit": spend.get("individualLimit"),
            "used": spend.get("individualUsed") or 0,
        }
    elif spend.get("pooledLimit") is not None:
        on_demand = {
            "limit": spend.get("pooledLimit"),
            "used": spend.get("pooledUsed") or 0,
        }

    if on_demand and on_demand["limit"]:
        limit = float(on_demand["limit"])
        used = float(on_demand["used"])
        windows.append(Window(
            id="on_demand",
            label="On-demand spend",
            used_pct=used / limit * 100.0 if limit > 0 else 0.0,
            resets_at=resets_at,
            window_seconds=2592000,
        ))

    if not windows:
        for field, win_id, label in [
            ("premiumRequestsUsed", "auto", "Auto"),
            ("gpt4", "auto", "Auto"),
        ]:
            total_field = {
                "premiumRequestsUsed": "premiumRequestsTotal",
                "gpt4": "gpt4MaxUsage",
            }.get(field)
            used = data.get(field)
            total = data.get(total_field) if total_field else None
            if used is not None and total:
                windows.append(Window(
                    id=win_id,
                    label=label,
                    used_pct=float(used) / float(total) * 100.0,
                    resets_at=resets_at,
                    window_seconds=2592000,
                ))
                break

    return windows


class CursorAdapter(Adapter):
    id = "cursor"
    display_name = "Cursor"

    def __init__(self, config: CursorConfig):
        self.config = config
        if config.auth_json_path:
            self._auth_path = Path(config.auth_json_path).expanduser()
        else:
            self._auth_path = _default_auth_json_path()

    async def _dashboard_request(self, client: httpx.AsyncClient, method: str, token: str) -> httpx.Response:
        return await client.post(
            f"{_DASHBOARD_BASE}/{method}",
            json={},
            headers={
                **_CONNECT_HEADERS,
                "Authorization": f"Bearer {token}",
            },
            timeout=30,
        )

    async def fetch(self) -> ProviderSnapshot:
        if not self.config.enabled:
            return _snap("disabled")

        token = _read_access_token(self._auth_path)
        if not token:
            return _snap(
                "auth_missing",
                f"No Cursor access token found. Run `cursor-agent login` — "
                f"tokenspyd reads {self._auth_path}.",
            )

        try:
            async with httpx.AsyncClient() as client:
                r = await self._dashboard_request(client, "GetCurrentPeriodUsage", token)
        except httpx.NetworkError as exc:
            return _snap("network_error", str(exc))

        if r.status_code == 401:
            return _snap(
                "auth_expired",
                "Cursor access token rejected (401). Run `cursor-agent login` to refresh.",
            )
        if r.status_code != 200:
            return _snap(
                "parse_error",
                f"Cursor usage request failed (HTTP {r.status_code}).",
            )

        try:
            windows = _parse_windows(r.json())
            return _snap("ok", windows=windows)
        except Exception as exc:
            logger.exception("Failed to parse Cursor response")
            return _snap("parse_error", f"Response parse error: {exc}")
