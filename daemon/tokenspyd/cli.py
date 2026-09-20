from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .store import STATE_PATH


def _build_adapters(config):
    from .adapters.claude import ClaudeAdapter
    from .adapters.codex import CodexAdapter
    from .adapters.cursor import CursorAdapter
    from .adapters.opencode_go import OpenCodeGoAdapter

    adapters = []
    if config.claude.enabled:
        adapters.append(ClaudeAdapter(config.claude))
    if config.codex.enabled:
        adapters.append(CodexAdapter(config.codex))
    if config.cursor.enabled:
        adapters.append(CursorAdapter(config.cursor))
    if config.opencode_go.enabled:
        adapters.append(OpenCodeGoAdapter(config.opencode_go))
    return adapters


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_run(args, config) -> None:
    from .poller import run_forever

    _setup_logging(config.log_level)
    adapters = _build_adapters(config)
    logging.getLogger(__name__).info("tokenspyd %s starting — %d adapters", __version__, len(adapters))
    asyncio.run(run_forever(config, adapters))


def cmd_poll_once(args, config) -> None:
    from .poller import poll_once

    _setup_logging(config.log_level)
    adapters = _build_adapters(config)
    snapshots = asyncio.run(poll_once(adapters))
    for snap in snapshots:
        status_str = snap.status
        if snap.status == "ok":
            bars = "  ".join(f"{w.label}: {w.used_pct:.1f}%" for w in snap.windows)
            print(f"  {snap.display_name}: {bars}")
        else:
            print(f"  {snap.display_name}: [{status_str}] {snap.error or ''}")
    print(f"\nState written to {STATE_PATH}")


def cmd_doctor(args, config) -> None:
    from .adapters.claude import ClaudeAdapter
    from .adapters.codex import CodexAdapter
    from .adapters.cursor import CursorAdapter
    from .adapters.opencode_go import OpenCodeGoAdapter

    _setup_logging("WARNING")
    print("tokenspyd doctor\n")

    checks = [
        ("Claude", config.claude.enabled, ClaudeAdapter(config.claude)),
        ("Codex", config.codex.enabled, CodexAdapter(config.codex)),
        ("Cursor", config.cursor.enabled, CursorAdapter(config.cursor)),
        ("OpenCode Go", config.opencode_go.enabled, OpenCodeGoAdapter(config.opencode_go)),
    ]

    async def run_checks():
        for name, enabled, adapter in checks:
            if not enabled:
                print(f"[SKIP] {name}: disabled in config.toml")
                continue
            print(f"[....] {name}: fetching...", end="", flush=True)
            snap = await asyncio.wait_for(adapter.fetch(), timeout=30)
            # \r + spaces clears the "fetching..." line before printing result
            clear = "\r" + " " * 60 + "\r"
            if snap.status == "ok":
                bars = ", ".join(f"{w.label}={w.used_pct:.1f}%" for w in snap.windows)
                print(f"{clear}[ OK ] {name}: {bars}")
            else:
                print(f"{clear}[FAIL] {name}: [{snap.status}] {snap.error}")

    asyncio.run(run_checks())
    print()


def cmd_version(args, config) -> None:
    print(f"tokenspyd {__version__}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="tokenspyd", description="AI usage poller")
    parser.add_argument("--config", type=Path, help="Path to config.toml")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Start the daemon (called by systemd)")
    sub.add_parser("poll-once", help="Poll all providers once and exit")
    sub.add_parser("doctor", help="Diagnose credential and connectivity issues")
    sub.add_parser("version", help="Print version and exit")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    config = load_config(args.config) if args.config else load_config()

    dispatch = {
        "run": cmd_run,
        "poll-once": cmd_poll_once,
        "doctor": cmd_doctor,
        "version": cmd_version,
    }
    dispatch[args.command](args, config)
