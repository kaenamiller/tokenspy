"""Tests for the Codex adapter parser."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "daemon"))

from tokenspyd.adapters.codex import _parse_windows, _epoch_to_iso


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "codex_wham_usage.json").read_text()
)


def test_parse_primary_secondary_windows():
    windows = _parse_windows(FIXTURE)
    assert len(windows) == 2

    five_h = next(w for w in windows if w.id == "five_hour")
    assert five_h.label == "5h session"
    assert five_h.used_pct == 1.0
    assert five_h.window_seconds == 18000

    weekly = next(w for w in windows if w.id == "seven_day")
    assert weekly.label == "Weekly"
    assert weekly.used_pct == 17.0
    assert weekly.window_seconds == 604800


def test_reset_at_epoch_to_iso():
    windows = _parse_windows(FIXTURE)
    five_h = next(w for w in windows if w.id == "five_hour")
    assert five_h.resets_at is not None
    assert "T" in five_h.resets_at
    assert five_h.resets_at.endswith("Z")


def test_epoch_ms_detection():
    ts_s = 1777627731
    ts_ms = ts_s * 1000
    assert _epoch_to_iso(ts_s) == _epoch_to_iso(ts_ms)


def test_percent_left_variant():
    data = {
        "rate_limit": {
            "primary_window": {
                "percent_left": 60.0,
                "limit_window_seconds": 18000,
                "reset_at": 1777627731,
            }
        }
    }
    windows = _parse_windows(data)
    assert windows[0].used_pct == 40.0


def test_remaining_percent_variant():
    data = {
        "rate_limit": {
            "primary_window": {
                "remaining_percent": 75.0,
                "limit_window_seconds": 18000,
                "reset_at": 1777627731,
            }
        }
    }
    windows = _parse_windows(data)
    assert windows[0].used_pct == 25.0


def test_five_hour_weekly_field_names():
    data = {
        "rate_limit": {
            "five_hour": {
                "used_percent": 50.0,
                "limit_window_seconds": 18000,
                "reset_at": 1777627731,
            },
            "weekly": {
                "used_percent": 30.0,
                "limit_window_seconds": 604800,
                "reset_at": 1777961671,
            },
        }
    }
    windows = _parse_windows(data)
    assert len(windows) == 2
    assert windows[0].used_pct == 50.0
    assert windows[1].used_pct == 30.0


def test_null_window_is_ignored():
    """The API may omit the weekly window by returning null."""
    data = {
        "rate_limit": {
            "primary_window": {
                "used_percent": 25.0,
                "limit_window_seconds": 604800,
                "reset_at": 1777627731,
            },
            "secondary_window": None,
        }
    }

    windows = _parse_windows(data)

    assert len(windows) == 1
    assert windows[0].id == "seven_day"
    assert windows[0].label == "Weekly"
    assert windows[0].used_pct == 25.0
