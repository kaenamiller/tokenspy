from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CONFIG_DIR = _xdg_config / "tokenspy"
CONFIG_PATH = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = """\
[general]
poll_interval_seconds = 300
log_level = "INFO"

[providers.claude]
enabled = true
# auth_method: "oauth" (recommended) reads ~/.claude/.credentials.json from `claude auth login`.
#              "session" reads the claude.ai sessionKey cookie from Firefox instead.
auth_method = "oauth"
# session_key = "sk-ant-sid01-..."   # only used with auth_method = "session"
# organization_id = "1c493371-b7d4-4388-a109-609710abcf90"  # only used with auth_method = "session"

[providers.codex]
enabled = true
# Reads ~/.codex/auth.json automatically; nothing to configure.

[providers.cursor]
enabled = true
# Reads accessToken from cursor-agent auth.json (~/.config/cursor/auth.json on Linux).
# Override if your auth file lives somewhere else:
# auth_json_path = "~/.config/cursor/auth.json"
"""


@dataclass
class ClaudeConfig:
    enabled: bool = True
    auth_method: str = "oauth"
    session_key: Optional[str] = None
    organization_id: Optional[str] = None


@dataclass
class CodexConfig:
    enabled: bool = True


@dataclass
class CursorConfig:
    enabled: bool = True
    auth_json_path: Optional[str] = None


@dataclass
class Config:
    poll_interval_seconds: int = 300
    log_level: str = "INFO"
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG)

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    general = raw.get("general", {})
    providers = raw.get("providers", {})
    claude_raw = providers.get("claude", {})
    codex_raw = providers.get("codex", {})
    cursor_raw = providers.get("cursor", {})

    return Config(
        poll_interval_seconds=general.get("poll_interval_seconds", 300),
        log_level=general.get("log_level", "INFO"),
        claude=ClaudeConfig(
            enabled=claude_raw.get("enabled", True),
            auth_method=claude_raw.get("auth_method", "oauth"),
            session_key=claude_raw.get("session_key"),
            organization_id=claude_raw.get("organization_id"),
        ),
        codex=CodexConfig(
            enabled=codex_raw.get("enabled", True),
        ),
        cursor=CursorConfig(
            enabled=cursor_raw.get("enabled", True),
            auth_json_path=cursor_raw.get("auth_json_path"),
        ),
    )
