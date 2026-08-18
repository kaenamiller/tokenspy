# Meter — Implementation Plan

A KDE Plasma 6 desktop widget that displays available usage from Claude (Pro/Max), OpenAI Codex (ChatGPT Plus/Pro), and Cursor (Pro), all in one place.

## Background and motivation

Each of the three providers gives users a fixed monthly subscription quota that is split across multiple usage windows (typically a 5-hour rolling window plus a 7-day weekly window). None of them currently expose this quota data through a documented public API for individual subscribers — the official APIs (Anthropic Admin API, Cursor Admin API, OpenAI Compliance/Analytics API) are all restricted to organization/team/enterprise plans.

However, **all three settings dashboards are powered by internal JSON endpoints that can be called directly from a logged-in session**. Several open-source projects have demonstrated this works reliably:

- **Claude:** `dependentsign/ClaudeUsageWidget` (macOS WidgetKit) and `f-is-h/Usage4Claude` (macOS menu bar) hit `https://api.anthropic.com/api/oauth/usage` (OAuth) or `https://claude.ai/api/organizations/{orgId}/usage` (session cookie).
- **OpenAI Codex:** `RioArisk/codex-auth-manager` and a documented Python script at knightli.com hit `https://chatgpt.com/backend-api/wham/usage` using the access token from `~/.codex/auth.json`.
- **Cursor:** `lixwen/cursor-usage-monitor` (VS Code extension) hits `https://cursor.com/api/dashboard/get-current-period-usage` using the `WorkosCursorSessionToken` cookie pulled from Cursor's local SQLite at `~/.config/Cursor/User/globalStorage/state.vscdb`.

There is no equivalent for Linux + KDE Plasma. This project fills that gap. The user runs Fedora with KDE Plasma 6.

These endpoints are **unofficial and undocumented** and may change without notice. The architecture must isolate provider-specific code behind clean adapters so when one breaks (and one will, eventually), the fix is local to a single file.

## Goals

1. A small background daemon that polls all three providers every 5 minutes and writes a normalized snapshot to a JSON file.
2. A KDE Plasma 6 plasmoid that reads that JSON file and renders six progress bars (5h + weekly for Claude, 5h + weekly for Codex, Auto + API for Cursor), with color-coded utilization, time-to-reset, and graceful states for auth failures.
3. Installable on Fedora with KDE Plasma 6 with one command per component.

## Non-goals (v1)

- Windows, macOS, or other Linux desktop environments. Plasma 6 only.
- Historical analytics, burn-rate prediction, or extrapolation. The widget is a gas gauge, not a dashboard. (Possible v2.)
- Multi-account support. One account per provider. (Possible v2.)
- Configuring the widget's polling cadence from the GUI. Edit the config file. (Possible v2.)
- Notifications/alerts. (Possible v2.)
- Anthropic Admin API or Cursor Admin API integration (those are for orgs).

## Repository layout

```
meter/
├── README.md
├── LICENSE                              # MIT
├── pyproject.toml                       # uses hatchling; declares meterd entrypoint
├── install.sh                           # convenience: pipx install + systemd + plasmoid
├── uninstall.sh
├── daemon/
│   └── meterd/
│       ├── __init__.py
│       ├── __main__.py                  # `python -m meterd`
│       ├── cli.py                       # argparse: run, poll-once, doctor, version
│       ├── config.py                    # load ~/.config/meter/config.toml
│       ├── poller.py                    # asyncio main loop
│       ├── store.py                     # atomic JSON writes to state file
│       ├── schema.py                    # ProviderSnapshot, Window dataclasses
│       └── adapters/
│           ├── __init__.py
│           ├── base.py                  # Adapter ABC
│           ├── claude.py
│           ├── codex.py
│           └── cursor.py
├── plasmoid/
│   └── package/
│       ├── metadata.json
│       ├── contents/
│       │   ├── ui/
│       │   │   ├── main.qml             # PlasmoidItem root
│       │   │   ├── CompactView.qml      # panel/icon view
│       │   │   ├── FullView.qml         # popup / desktop view
│       │   │   ├── ProviderRow.qml      # single row: label, bar, %, reset
│       │   │   └── configGeneral.qml    # config dialog
│       │   └── config/
│       │       ├── config.qml
│       │       └── main.xml
├── systemd/
│   ├── meterd.service                   # user unit
│   └── meterd.timer                     # alternative to internal loop (optional)
└── tests/
    ├── test_adapters_claude.py
    ├── test_adapters_codex.py
    ├── test_adapters_cursor.py
    ├── test_normalizer.py
    └── fixtures/                        # canned JSON responses captured from real APIs
        ├── claude_oauth_usage.json
        ├── codex_wham_usage.json
        └── cursor_period_usage.json
```

## Phase 1 — The daemon (`meterd`)

### Tech choices

- **Python 3.11+**. Standard library `asyncio` for the polling loop, `httpx` for HTTP (handles cookies cleanly and has good async support), `tomllib` for config, `sqlite3` for reading Cursor's state.vscdb. No FastAPI, no heavy frameworks.
- **Packaging:** `pyproject.toml` with hatchling. Installable via `pipx install .` from the repo root. This puts a `meterd` script on the user's PATH.
- **Logging:** stdlib `logging` to journald (systemd handles this for free if you log to stderr).

### State file (the public interface to the widget)

Path: `$XDG_STATE_HOME/meter/current.json`, defaulting to `~/.local/state/meter/current.json`.

Schema (validate this against a JSON Schema in the codebase):

```json
{
  "schema_version": 1,
  "generated_at": "2026-04-30T15:42:11Z",
  "providers": [
    {
      "id": "claude",
      "display_name": "Claude",
      "status": "ok",
      "windows": [
        {
          "id": "five_hour",
          "label": "5h session",
          "used_pct": 47.3,
          "resets_at": "2026-04-30T18:30:00Z",
          "window_seconds": 18000
        },
        {
          "id": "seven_day",
          "label": "Weekly",
          "used_pct": 22.1,
          "resets_at": "2026-05-04T00:00:00Z",
          "window_seconds": 604800
        }
      ],
      "last_polled_at": "2026-04-30T15:42:09Z",
      "error": null
    },
    {
      "id": "codex",
      "display_name": "Codex",
      "status": "ok",
      "windows": [
        { "id": "five_hour", "label": "5h", "used_pct": 12.0, "resets_at": "...", "window_seconds": 18000 },
        { "id": "weekly",    "label": "Weekly", "used_pct": 38.5, "resets_at": "...", "window_seconds": 604800 }
      ],
      "last_polled_at": "...",
      "error": null
    },
    {
      "id": "cursor",
      "display_name": "Cursor",
      "status": "auth_expired",
      "windows": [],
      "last_polled_at": "2026-04-30T15:42:10Z",
      "error": "WorkosCursorSessionToken cookie not found in state.vscdb. Sign in to Cursor and try again."
    }
  ]
}
```

`status` is one of: `ok`, `auth_expired`, `auth_missing`, `network_error`, `parse_error`, `disabled`.

`used_pct` is a float 0–100 (or sometimes >100 — see provider notes; clamp to 100 only at render time, never in storage).

Atomic write: write to `current.json.tmp` in the same directory, then `os.replace()`. The widget should handle a momentary `FileNotFoundError` gracefully but with this pattern it shouldn't happen.

### Config file

Path: `$XDG_CONFIG_HOME/meter/config.toml`, defaulting to `~/.config/meter/config.toml`.

```toml
[general]
poll_interval_seconds = 300
log_level = "INFO"

[providers.claude]
enabled = true
# auth_method: "oauth" reads ~/.claude/.credentials.json (Claude Code OAuth token)
#              "session" uses session_key + organization_id below
auth_method = "oauth"
# session_key = "sk-ant-sid01-..."
# organization_id = "00000000-0000-0000-0000-000000000000"

[providers.codex]
enabled = true
# Reads ~/.codex/auth.json automatically; nothing to configure.

[providers.cursor]
enabled = true
# Reads WorkosCursorSessionToken from Cursor's state.vscdb automatically.
# Override the path if Cursor is installed somewhere unusual:
# state_db_path = "~/.config/Cursor/User/globalStorage/state.vscdb"
```

If the file doesn't exist, the daemon creates one with the defaults above on first run.

### Adapter interface (`adapters/base.py`)

```python
from abc import ABC, abstractmethod
from typing import Optional
from .schema import ProviderSnapshot

class Adapter(ABC):
    id: str                    # "claude" | "codex" | "cursor"
    display_name: str

    @abstractmethod
    async def fetch(self) -> ProviderSnapshot:
        """
        Returns a ProviderSnapshot. Should NEVER raise — convert all
        errors into a snapshot with status != "ok" and a useful error
        message. The poller treats exceptions as bugs.
        """
        ...
```

The poller calls `adapter.fetch()` for each enabled provider concurrently with `asyncio.gather(..., return_exceptions=True)`, applies a per-call timeout of 30 seconds, and writes the combined result to the state file.

### Adapter: Claude (`adapters/claude.py`)

Two auth modes:

**Mode A — OAuth (preferred).** Read the Claude Code OAuth token. The agent should investigate the actual file used by current Claude Code on Linux:
- Check `~/.claude/.credentials.json` first.
- If not present, check the libsecret keyring under the `Claude Code` schema (use `secretstorage` Python package).
- Surface a clear error ("OAuth token not found; run `claude auth login` or switch `auth_method` to `session` in config.toml") if neither works.

Then: `GET https://api.anthropic.com/api/oauth/usage` with `Authorization: Bearer <token>`.

**Mode B — Session cookie.** Read `session_key` and `organization_id` from config. If `organization_id` is omitted, call `GET https://claude.ai/api/organizations` first and use the first org's UUID. Then: `GET https://claude.ai/api/organizations/{orgId}/usage` with `Cookie: sessionKey=<session_key>`.

**Response parsing.** Both modes return the same shape (verify this against a real captured response — that's what the test fixture is for). Map:
- `five_hour.utilization` (0–100 or 0–1; check and normalize) → `used_pct`
- `five_hour.resets_at` (ISO 8601 UTC) → `resets_at`
- `seven_day.utilization` → second window's `used_pct`
- `seven_day.resets_at` → second window's `resets_at`

If the response also has `seven_day_opus` / `seven_day_sonnet` (Max plan), include them as additional windows. The user is on the $20/month Pro plan so this likely won't appear, but handle it.

**Errors.**
- 401 → `auth_expired`, error message says how to refresh (re-login to Claude Code, or update session_key in config).
- 403 → `auth_missing` with similar message.
- Network error → `network_error`.
- Other 4xx/5xx → `parse_error` with the status code in the message.

### Adapter: Codex (`adapters/codex.py`)

1. Read `~/.codex/auth.json`. Extract `tokens.access_token` and `tokens.account_id`. If either is missing or the file doesn't exist → `auth_missing` with message "Codex CLI not signed in; run `codex login`".
2. Decode the JWT exp claim (it's in the `access_token`). If expired → `auth_expired` with "Codex token expired; the next `codex` invocation will refresh it automatically."
3. `GET https://chatgpt.com/backend-api/wham/usage` with headers:
   ```
   Authorization: Bearer <access_token>
   ChatGPT-Account-Id: <account_id>
   Accept: application/json
   Origin: https://chatgpt.com
   Referer: https://chatgpt.com/
   User-Agent: Mozilla/5.0
   ```
4. Parse `rate_limit` (or `rate_limits`) sub-object. The schema is in flux; handle both old and new field names. Reference: the working Python script at https://www.knightli.com/en/2026/04/12/codex-usage-quota-check/ enumerates all the fallbacks. Specifically:
   - Look for `five_hour`, then `five_hour_limit`, then `five_hour_rate_limit`, then `primary_window` for the 5-hour entry.
   - Look for `weekly`, then `weekly_limit`, then `weekly_rate_limit`, then `secondary_window` for the weekly entry.
   - If both windows have the same name, infer from `limit_window_seconds` (≤6h → five_hour, ≥6 days → weekly).
   - Reset time may be `reset_time_ms` or `reset_at`, in either epoch ms or epoch seconds (heuristic: > 10^11 means ms).
   - Percentage may be `percent_left` (then `100 - x`), `remaining_percent` (then `100 - x`), or `used_percent` (use directly).
5. Errors map the same way as Claude.

### Adapter: Cursor (`adapters/cursor.py`)

1. Read `~/.config/Cursor/User/globalStorage/state.vscdb` (sqlite3). The cookie is stored as a JSON value in the `ItemTable` table — find the row whose key is related to the WorkOS session. The agent must verify the exact key by inspecting a real database; common candidates are:
   - `cursorAuth/cursorAuth.workosCursorSessionToken`
   - Other `cursorAuth/*` keys that contain the WorkOS JWT.
   Reference implementation: `lixwen/cursor-usage-monitor` does exactly this lookup; read its source.
2. Extract the cookie value. If absent → `auth_missing` with "Sign in to Cursor and try again."
3. `POST https://cursor.com/api/dashboard/get-current-period-usage` with body `{}`, headers `Content-Type: application/json`, and cookie `WorkosCursorSessionToken=<value>`.
4. Parse the response. Map two windows:
   - **Auto** — internal models / Composer quota. Field names to check (verify against a captured response): `auto`, `included_usage`, `composer_usage`, etc.
   - **API** — external/usage-based-pricing models. Check: `api`, `usage_based`, `external`.
   - The Cursor "Spending" tab shows these as percentages of the included monthly allowance; surface the same. Reset is the end of the current billing period.
5. Errors: 400 has been observed intermittently in the wild (forum.cursor.com) — treat as `parse_error` with a "Cursor's dashboard endpoint is unavailable; try again later" message.

### Polling loop (`poller.py`)

```python
async def run_forever(config: Config) -> None:
    adapters = build_adapters(config)
    while True:
        snapshots = await asyncio.gather(
            *(asyncio.wait_for(a.fetch(), timeout=30) for a in adapters),
            return_exceptions=True,
        )
        # Convert any Exception into a fail-snapshot
        results = [coerce_to_snapshot(a, s) for a, s in zip(adapters, snapshots)]
        store.write_state(results)
        await asyncio.sleep(config.poll_interval_seconds)
```

Stagger initial polls by a few seconds so the three providers don't all hit at once on startup. After the first successful poll, exit code 0 if `meterd poll-once` was used (for testing).

### CLI

- `meterd run` — start the daemon (this is what systemd calls).
- `meterd poll-once` — poll every enabled provider once, write the state file, print a summary, exit. Useful for cron setups and for debugging.
- `meterd doctor` — for each enabled provider, attempt to read credentials, print where it found them, attempt one fetch, print the result. **Do not print the actual tokens.** This is the first thing a user runs to diagnose problems.
- `meterd version`

### systemd user unit (`systemd/meterd.service`)

```ini
[Unit]
Description=Meter — AI usage poller
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/meterd run
Restart=on-failure
RestartSec=30s
# Don't run while screen-locked or paused — pointless to poll if the user isn't working
# (omit if you'd rather it always run)

[Install]
WantedBy=default.target
```

Install with `systemctl --user enable --now meterd.service`. If the user wants polling while logged out: `loginctl enable-linger $USER`. The user probably does *not* want this — when they're not logged in they're not burning quota — so default to off.

### Tests

- One test per adapter that loads a fixture JSON file, runs the parser, and asserts the normalized output matches expected values.
- One test for `store.write_state` confirming atomicity (write fails halfway → old state is preserved).
- One test for the schema (validate output against the JSON schema).

The agent must capture **at least one real response from each provider** during development and commit them as fixtures (with any tokens/UUIDs scrubbed). Without fixtures the parsing code is untestable and the project is fragile.

## Phase 2 — The plasmoid

### Tech choices

- KDE Plasma 6 / Qt 6 / KF6. Plasma 5 compatibility is **not** a goal — the user runs current Fedora KDE which ships Plasma 6.
- Pure QML + JavaScript. No C++ plugin. No external Qt modules beyond what ships with Plasma 6.
- Read the daemon's state file via `XMLHttpRequest('file:///...')` — this works fine in QML and is the simplest possible IPC.

### `metadata.json`

```json
{
  "KPlugin": {
    "Authors": [{ "Name": "Kaena", "Email": "" }],
    "Category": "System Information",
    "Description": "Track AI subscription usage across Claude, Codex, and Cursor",
    "Icon": "view-statistics",
    "Id": "com.kaena.meter",
    "Name": "Meter",
    "Version": "0.1.0",
    "Website": "https://github.com/kaena/meter",
    "License": "MIT"
  },
  "KPackageStructure": "Plasma/Applet",
  "X-Plasma-API-Minimum-Version": "6.0"
}
```

### `main.qml` (Plasma 6 patterns — these are subtly different from Plasma 5)

```qml
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property var snapshot: null
    property string fetchError: ""

    Plasmoid.toolTipMainText: snapshot
        ? "Meter — " + snapshot.providers.length + " providers"
        : "Meter (loading…)"

    function refresh() {
        const path = StandardPaths.writableLocation(StandardPaths.GenericStateLocation)
                   + "/meter/current.json"
        const xhr = new XMLHttpRequest()
        xhr.open("GET", "file://" + path)
        xhr.onreadystatechange = function() {
            if (xhr.readyState === XMLHttpRequest.DONE) {
                if (xhr.status === 200 || xhr.status === 0) {
                    try {
                        snapshot = JSON.parse(xhr.responseText)
                        fetchError = ""
                    } catch (e) {
                        fetchError = "State file is malformed"
                    }
                } else {
                    fetchError = "Daemon hasn't written state yet — is meterd running?"
                }
            }
        }
        xhr.send()
    }

    Timer {
        interval: 30000          // re-read every 30s; daemon updates every 5min
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    compactRepresentation: CompactView { snapshot: root.snapshot }
    fullRepresentation: FullView {
        snapshot: root.snapshot
        fetchError: root.fetchError
    }
}
```

(QtQml `StandardPaths` import may be needed; if it isn't available in QML, hardcode `Qt.resolvedUrl(Qt.application.arguments[0])` style won't work either — fallback is to read `$HOME` from the environment via a tiny helper. The agent should figure out the cleanest path for Plasma 6.)

### Compact representation

A single icon + the **highest** `used_pct` across all windows of all providers, color-coded:
- 0–60% → theme accent / green
- 60–80% → yellow
- 80–95% → orange
- 95%+ → red

Click anchors the popup; popup shows the full view.

### Full representation

Vertical list of provider rows, each row showing:

```
[icon] Claude
       5h session     ████████░░  47%  resets in 2h 47m
       Weekly         ██░░░░░░░░  22%  resets Mon 4 May
```

Use `Kirigami.Theme.textColor`, `disabledTextColor`, etc. so it auto-themes. Use a horizontal `PlasmaComponents.ProgressBar` with custom color for the warning thresholds (the default theme bar doesn't easily change color; the agent may need to draw a `Rectangle` instead — see existing system-monitor plasmoids for examples).

For each row, render a sensible state:
- `status: "ok"` → bars and percentages.
- `status: "auth_expired" | "auth_missing"` → the row is greyed out and shows the error message inline.
- `status: "network_error" | "parse_error"` → row shows ⚠ + the error message, last successful poll time at the bottom.
- `status: "disabled"` → row is hidden (the user opted out in config).

Reset time formatting: under 24h shows "in 2h 47m", over 24h shows "Mon 4 May" (locale-aware via Kirigami's date formatting).

If `fetchError` is non-empty (state file missing/malformed), show a single banner at the top explaining how to start the daemon: `systemctl --user start meterd.service`.

### Configuration dialog (`configGeneral.qml`)

Minimal v1:
- Path to state file (defaulted, rarely changed).
- Refresh interval inside the widget (default 30s).
- Toggle to hide individual providers from the display.

That's it. All credential and adapter config lives in the daemon's `config.toml`. The widget never sees a token.

### Installation

```bash
kpackagetool6 --type Plasma/Applet --install plasmoid/package
# or to update an existing install:
kpackagetool6 --type Plasma/Applet --upgrade plasmoid/package
```

Test loop during development:
```bash
plasmoidviewer6 -a plasmoid/package
```

## Phase 3 — Install and uninstall scripts

### `install.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Install the Python daemon
pipx install --force "$(dirname "$(readlink -f "$0")")"

# 2. Install the systemd user unit
mkdir -p ~/.config/systemd/user
cp systemd/meterd.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now meterd.service

# 3. Install the plasmoid
kpackagetool6 --type Plasma/Applet --install plasmoid/package \
  || kpackagetool6 --type Plasma/Applet --upgrade plasmoid/package

# 4. Run the doctor to surface any auth issues
meterd doctor

cat <<EOF

✓ Meter is installed.

Right-click your desktop or panel → Add Widgets… → search "Meter" to add it.

Config: ~/.config/meter/config.toml
State:  ~/.local/state/meter/current.json
Logs:   journalctl --user -u meterd -f

EOF
```

### `uninstall.sh`

Reverse of the above: stop service, disable, remove unit, `kpackagetool6 --remove`, `pipx uninstall meter`. Leave config and state files alone (offer `--purge`).

## Validation checklist for the agent

Before declaring done, verify each of the following:

1. `meterd doctor` runs cleanly with no providers configured (it should report all three as `disabled` or `auth_missing` with helpful next steps).
2. With Claude Code signed in, `meterd doctor` for Claude finds the OAuth token and successfully fetches usage. The captured fixture matches the live response shape.
3. With Codex CLI signed in, same for Codex.
4. With Cursor signed in, same for Cursor.
5. `systemctl --user start meterd.service` runs the daemon. `journalctl --user -u meterd -f` shows poll cycles every 5 minutes.
6. The state file appears at `~/.local/state/meter/current.json` and validates against the schema.
7. `kpackagetool6 --install plasmoid/package` succeeds. The widget appears in the "Add Widgets" picker.
8. Adding the widget to the desktop renders six rows. Adding it to a panel renders one compact icon with a percentage.
9. Killing the daemon and waiting 30s → the widget shows the "daemon not running" banner.
10. Manually corrupting `current.json` (write `garbage`) → the widget shows the malformed-state banner without crashing.
11. Manually editing the state file to set Claude's `status` to `auth_expired` → that row renders greyed out with the error message.
12. After Claude resets at the next 5h boundary, the displayed percentage drops accordingly within one polling cycle.

## Risks and known unknowns

- **Cookie-based auth (claude.ai sessionKey, Cursor WorkosCursorSessionToken) expires.** Codex and Claude OAuth refresh themselves; the others won't. Plan for graceful failure with clear UX, not auto-refresh.
- **The Cursor endpoint has been observed returning 400 intermittently.** The reference forum thread is https://forum.cursor.com/t/i-cant-get-my-usage-info/155469 — keep an eye on it. The adapter must not crash on this; it should report `parse_error` and let the next poll succeed.
- **Codex `wham/usage` field names have shifted before** (`primary_window`/`secondary_window` ↔ `five_hour`/`weekly`) — the adapter's resilient parser is essential, not optional.
- **Claude Max plan responses include extra `seven_day_opus` / `seven_day_sonnet` windows.** The user is on Pro so probably won't see these, but the schema and the widget should accommodate any number of windows per provider — don't hardcode "exactly two".
- **Plasma 6 QML APIs differ from Plasma 5** in subtle ways the agent will trip over if it Googles older tutorials. The KDE porting guide at https://develop.kde.org/docs/plasma/widget/porting_kf6/ is the authoritative reference. Notable: `PlasmoidItem` (not `Item`) as root; `Plasmoid.compactRepresentation` lives directly on the root element; `metadata.json` (not `metadata.desktop`).
- **Reading SQLite from Python while Cursor is running** can rarely produce a "database is locked" error — open with `sqlite3.connect("file:...?mode=ro&immutable=1", uri=True)` to avoid this.

## References (for the implementing agent)

- Claude usage endpoint and OAuth pattern: https://github.com/dependentsign/ClaudeUsageWidget (Swift, but the API calls translate directly)
- Multi-account Claude session-cookie pattern: https://github.com/f-is-h/Usage4Claude
- Codex `wham/usage` fully-worked Python: https://www.knightli.com/en/2026/04/12/codex-usage-quota-check/
- Cursor cookie-from-state.vscdb pattern: https://github.com/lixwen/cursor-usage-monitor
- Claude Code reverse-engineering of unified-ratelimit headers: https://www.claudecodecamp.com/p/i-tried-to-reverse-engineer-claude-code-s-usage-limits
- KDE Plasma 6 widget setup: https://develop.kde.org/docs/plasma/widget/setup/
- KDE Plasma 6 porting guide: https://develop.kde.org/docs/plasma/widget/porting_kf6/
- HTTP fetch in QML (Edmundson): https://blog.davidedmundson.co.uk/blog/plasmoid-tutorial-2-getting-data/

## Build order

For an agent implementing this end-to-end, the path of least pain is:

1. **Project skeleton + Claude adapter + tests + fixture.** Get one provider all the way working in Python before touching the others. Verify with `meterd poll-once`.
2. **Codex adapter + tests + fixture.**
3. **Cursor adapter + tests + fixture.**
4. **Poller, store, CLI, config.** Wire the three adapters into a real daemon. Verify with `systemctl --user`.
5. **Plasmoid `metadata.json` + minimal `main.qml`** that reads the state file and just dumps the JSON as text. Verify with `plasmoidviewer6`.
6. **Full representation with provider rows.** Iterate on visual design.
7. **Compact representation.**
8. **Config dialog.**
9. **Install/uninstall scripts. README.**

Each step should pass its tests before moving on. The agent should ask the user to capture real API responses (with tokens scrubbed) at step 1, 2, and 3 — there's no substitute for a real fixture.
