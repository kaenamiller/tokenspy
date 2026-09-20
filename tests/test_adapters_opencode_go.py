"""Tests for the OpenCode Go adapter parser."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "daemon"))

from tokenspyd.adapters.opencode_go import _parse_windows


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "opencode_go_usage.json").read_text()
)


def test_parse_official_usage_windows():
    windows = _parse_windows(FIXTURE)

    assert [window.id for window in windows] == ["rolling", "weekly", "monthly"]
    assert [window.used_pct for window in windows] == [12.0, 25.0, 8.0]
    assert [window.window_seconds for window in windows] == [18000, 604800, 2592000]
    assert windows[0].resets_at == "2026-08-22T05:32:17Z"


def test_missing_usage_window_is_ignored():
    data = {**FIXTURE, "usage": {**FIXTURE["usage"], "weekly": None}}

    windows = _parse_windows(data)

    assert [window.id for window in windows] == ["rolling", "monthly"]


def test_percent_field_alias_is_supported():
    windows = _parse_windows({"rollingUsage": {"percent": 42, "resetInSec": 60}})

    assert windows[0].used_pct == pytest.approx(42.0)


def test_reset_in_seconds_field_is_supported():
    before = datetime.now(timezone.utc)
    windows = _parse_windows({"rollingUsage": {"usagePercent": 42, "resetInSec": 60}})
    after = datetime.now(timezone.utc)

    reset = datetime.fromisoformat(windows[0].resets_at.replace("Z", "+00:00"))
    assert before.timestamp() + 59 <= reset.timestamp() <= after.timestamp() + 60
