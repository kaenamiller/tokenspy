from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from .base import Adapter
from ..config import ClaudeConfig
from ..schema import ProviderSnapshot, Window

logger = logging.getLogger(__name__)

_OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_CLAUDE_AI_ORGS_URL = "https://claude.ai/api/organizations"
_OAUTH_BETA = "oauth-2025-04-20"
_OAUTH_USER_AGENT = "claude-code/2.1.0"

# Hardcode org UUID discovered from /api/oauth/profile to avoid an extra request
_KNOWN_ORG_ID: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snap(status: str, error: str | None = None, windows: list[Window] | None = None) -> ProviderSnapshot:
    return ProviderSnapshot(
        id="claude",
        display_name="Claude",
        status=status,
        windows=windows or [],
        last_polled_at=_now(),
        error=error,
    )


def _parse_pct(value) -> float:
    """Accept 0–1 fraction or 0–100 percent and return 0–100."""
    f = float(value)
    return f * 100.0 if f <= 1.0 else f


def _normalize_iso(ts: Optional[str]) -> Optional[str]:
    """Normalize ISO 8601 timestamps (with offset or microseconds) to plain UTC Z form."""
    if not ts:
        return None
    try:
        from datetime import datetime, timezone as _tz
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        return dt.astimezone(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ts


def _parse_window_entry(w: Optional[dict], win_id: str, label: str, seconds: int) -> Optional[Window]:
    if not w or not isinstance(w, dict):
        return None
    # Anthropic's `utilization` is already a percentage in the 0–100 range.
    # In particular, 1.0 means 1%, not a fully-used fractional value.  Keep
    # the fractional fallback only for alternate field names used by older
    # integrations.
    if w.get("utilization") is not None:
        used_pct = float(w["utilization"])
    else:
        raw = w.get("used_percent", w.get("used_pct"))
        if raw is None:
            return None
        used_pct = _parse_pct(raw)

    if used_pct < 0:
        return None
    return Window(
        id=win_id,
        label=label,
        used_pct=used_pct,
        resets_at=_normalize_iso(w.get("resets_at") or w.get("reset_at") or w.get("resetAt")),
        window_seconds=seconds,
    )


def _parse_windows(data: dict) -> list[Window]:
    windows: list[Window] = []

    for key in ("five_hour", "5h", "primary", "short_window"):
        w = _parse_window_entry(data.get(key), "five_hour", "5h session", 18000)
        if w:
            windows.append(w)
            break

    for key in ("seven_day", "weekly", "7d", "secondary", "long_window"):
        w = _parse_window_entry(data.get(key), "seven_day", "Weekly", 604800)
        if w:
            windows.append(w)
            break

    # Named bonus windows (Max plan / feature-flagged)
    bonus = [
        ("seven_day_opus",    "Weekly Opus"),
        ("seven_day_sonnet",  "Weekly Sonnet"),
        ("seven_day_omelette","Weekly (omelette)"),
        ("seven_day_cowork",  "Weekly (cowork)"),
    ]
    for key, label in bonus:
        w = _parse_window_entry(data.get(key), key, label, 604800)
        if w:
            windows.append(w)

    return windows


class ClaudeAdapter(Adapter):
    id = "claude"
    display_name = "Claude"

    def __init__(self, config: ClaudeConfig):
        self.config = config

    async def fetch(self) -> ProviderSnapshot:
        if not self.config.enabled:
            return _snap("disabled")
        if self.config.auth_method == "session":
            return await self._fetch_session()
        return await self._fetch_oauth()

    # -- OAuth (Claude Code credentials, same source as BB) --

    async def _fetch_oauth(self) -> ProviderSnapshot:
        oauth = self._read_oauth_credentials()
        if not oauth:
            return _snap(
                "auth_missing",
                "Claude OAuth token not found. Run `claude auth login`, "
                "or set auth_method = 'session' in config.toml.",
            )

        token = oauth.get("accessToken")
        expires_at = oauth.get("expiresAt")
        if expires_at is not None and datetime.now(timezone.utc).timestamp() * 1000 >= float(expires_at):
            return _snap(
                "auth_expired",
                "Claude OAuth token has expired. Run `claude auth login` to refresh.",
            )

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    _OAUTH_USAGE_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "anthropic-beta": _OAUTH_BETA,
                        "User-Agent": _OAUTH_USER_AGENT,
                    },
                    timeout=30,
                )
        except httpx.NetworkError as exc:
            return _snap("network_error", str(exc))

        if r.status_code == 401:
            return _snap(
                "auth_expired",
                "Claude OAuth token rejected (401). Run `claude auth login` to refresh, "
                "or switch auth_method = 'session' in config.toml.",
            )
        if r.status_code == 429:
            return _snap(
                "parse_error",
                "Claude usage is rate limited right now. Try again shortly.",
            )
        if r.status_code == 403:
            return _snap(
                "auth_missing",
                "Claude OAuth access denied (403). This endpoint may not be available for your plan. "
                "Try auth_method = 'session' in config.toml.",
            )
        if r.status_code != 200:
            return _snap("parse_error", f"Unexpected HTTP {r.status_code} from Claude OAuth usage endpoint.")

        try:
            windows = _parse_windows(r.json())
            return _snap("ok", windows=windows)
        except Exception as exc:
            logger.exception("Failed to parse Claude OAuth response")
            return _snap("parse_error", f"Response parse error: {exc}")

    # -- Session cookie --

    async def _fetch_session(self) -> ProviderSnapshot:
        # Try Firefox first (auto); fall back to manual session_key in config
        ff_cookies = _read_firefox_cookies()
        session_key = self.config.session_key or (ff_cookies.get("sessionKey") if ff_cookies else None)

        if not session_key:
            return _snap(
                "auth_missing",
                "No Claude session key found. Either:\n"
                "  1. Log in to claude.ai in Firefox — tokenspyd will pick it up automatically.\n"
                "  2. Copy the sessionKey cookie from claude.ai and set session_key in\n"
                "     ~/.config/tokenspy/config.toml under [providers.claude].",
            )

        # Build cookie string — include Cloudflare cookies from Firefox to pass bot protection
        if ff_cookies:
            cf_keys = ["sessionKey", "cf_clearance", "__cf_bm", "anthropic-device-id"]
            cookie_str = "; ".join(f"{k}={ff_cookies[k]}" for k in cf_keys if k in ff_cookies)
            org_id = self.config.organization_id or ff_cookies.get("lastActiveOrg") or _KNOWN_ORG_ID
        else:
            cookie_str = f"sessionKey={session_key}"
            org_id = self.config.organization_id or _KNOWN_ORG_ID

        headers = {
            "Cookie": cookie_str,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://claude.ai/",
        }

        try:
            async with httpx.AsyncClient() as client:
                if not org_id:
                    r = await client.get(_CLAUDE_AI_ORGS_URL, headers=headers, timeout=30)
                    if r.status_code in (401, 403):
                        return _snap(
                            "auth_expired",
                            f"Claude session key rejected (HTTP {r.status_code}). "
                            "Log in to claude.ai in Firefox again.",
                        )
                    if r.status_code != 200:
                        return _snap("parse_error", f"Failed to fetch org list: HTTP {r.status_code}")
                    orgs = r.json()
                    if not orgs:
                        return _snap("parse_error", "No organizations found for this account.")
                    org_id = orgs[0].get("uuid") or orgs[0].get("id")

                r = await client.get(
                    f"https://claude.ai/api/organizations/{org_id}/usage",
                    headers=headers,
                    timeout=30,
                )
        except httpx.NetworkError as exc:
            return _snap("network_error", str(exc))

        if r.status_code in (401, 403):
            return _snap(
                "auth_expired",
                f"Claude session rejected (HTTP {r.status_code}). Log in to claude.ai in Firefox again.",
            )
        if r.status_code != 200:
            return _snap("parse_error", f"Unexpected HTTP {r.status_code} from Claude usage endpoint.")

        try:
            windows = _parse_windows(r.json())
            return _snap("ok", windows=windows)
        except Exception as exc:
            logger.exception("Failed to parse Claude session response")
            return _snap("parse_error", f"Response parse error: {exc}")

    def _read_oauth_credentials(self) -> Optional[dict]:
        creds_path = Path.home() / ".claude" / ".credentials.json"
        if creds_path.exists():
            try:
                creds = json.loads(creds_path.read_text())
                oauth = creds.get("claudeAiOauth")
                if isinstance(oauth, dict) and oauth.get("accessToken"):
                    return oauth
            except Exception:
                pass

        try:
            import secretstorage
            conn = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(conn)
            for item in collection.get_all_items():
                if item.get_attributes().get("application") == "Claude Code":
                    token = item.get_secret().decode()
                    if token:
                        return {"accessToken": token}
        except Exception:
            pass

        return None


_CF_COOKIES = {"sessionKey", "cf_clearance", "__cf_bm", "anthropic-device-id", "lastActiveOrg"}


def _read_firefox_cookies() -> Optional[dict]:
    """Read claude.ai cookies from Firefox — returns dict of name→value, or None if unavailable."""
    firefox_dir = Path.home() / ".mozilla" / "firefox"
    if not firefox_dir.exists():
        return None

    for cookies_db in sorted(firefox_dir.glob("*.default*/cookies.sqlite")):
        tmp: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
                tmp = Path(f.name)
            shutil.copy2(cookies_db, tmp)
            conn = sqlite3.connect(f"file:{tmp}?mode=ro&immutable=1", uri=True)
            rows = conn.execute(
                "SELECT name, value FROM moz_cookies WHERE host LIKE '%claude.ai'"
            ).fetchall()
            conn.close()
            cookies = {name: value for name, value in rows}
            if "sessionKey" in cookies:
                logger.debug("Read %d claude.ai cookies from Firefox profile %s",
                             len(cookies), cookies_db.parent.name)
                return cookies
        except Exception as exc:
            logger.debug("Error reading Firefox cookies from %s: %s", cookies_db, exc)
        finally:
            if tmp and tmp.exists():
                tmp.unlink(missing_ok=True)

    return None
