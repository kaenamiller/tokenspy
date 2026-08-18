"""Tests for the Claude adapter parser."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "daemon"))

from tokenspyd.adapters.claude import _parse_windows, _parse_pct, _normalize_iso


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "claude_oauth_usage.json").read_text()
)


def test_parse_five_hour_and_weekly():
    windows = _parse_windows(FIXTURE)
    ids = [w.id for w in windows]
    assert "five_hour" in ids
    assert "seven_day" in ids

    five_h = next(w for w in windows if w.id == "five_hour")
    assert five_h.label == "5h session"
    assert five_h.used_pct == pytest.approx(18.0)
    assert five_h.resets_at == "2026-05-02T10:39:59Z"
    assert five_h.window_seconds == 18000

    weekly = next(w for w in windows if w.id == "seven_day")
    assert weekly.label == "Weekly"
    assert weekly.used_pct == pytest.approx(18.0)
    assert weekly.resets_at == "2026-05-06T05:00:00Z"


def test_null_windows_skipped():
    windows = _parse_windows(FIXTURE)
    ids = [w.id for w in windows]
    # These are null in the fixture — should not appear
    assert "seven_day_opus" not in ids
    assert "seven_day_sonnet" not in ids


def test_nonnull_bonus_window_included():
    data = {
        "five_hour": {"utilization": 10.0, "resets_at": "2026-05-02T10:00:00Z"},
        "seven_day": {"utilization": 20.0, "resets_at": "2026-05-06T05:00:00Z"},
        "seven_day_opus": {"utilization": 50.0, "resets_at": "2026-05-06T05:00:00Z"},
    }
    windows = _parse_windows(data)
    ids = [w.id for w in windows]
    assert "seven_day_opus" in ids


def test_parse_pct_fraction():
    assert _parse_pct(0.473) == pytest.approx(47.3)
    assert _parse_pct(18.0) == pytest.approx(18.0)
    assert _parse_pct(1.0) == pytest.approx(100.0)
    assert _parse_pct(0.0) == pytest.approx(0.0)


def test_utilization_uses_claudes_percentage_scale_at_one_percent():
    """Claude returns utilization as 0–100, so 1.0 must remain 1%."""
    data = {
        "five_hour": {"utilization": 0.0, "resets_at": None},
        "seven_day": {"utilization": 1.0, "resets_at": "2026-07-29T05:00:00Z"},
    }

    windows = _parse_windows(data)
    weekly = next(w for w in windows if w.id == "seven_day")
    assert weekly.used_pct == pytest.approx(1.0)


def test_normalize_iso_with_offset():
    result = _normalize_iso("2026-05-02T10:39:59.857274+00:00")
    assert result == "2026-05-02T10:39:59Z"


def test_normalize_iso_already_z():
    result = _normalize_iso("2026-05-04T00:00:00Z")
    assert result == "2026-05-04T00:00:00Z"


def test_normalize_iso_none():
    assert _normalize_iso(None) is None


def test_seven_day_field_name_alias():
    data = {
        "five_hour": {"utilization": 10.0, "resets_at": "2026-04-30T18:00:00Z"},
        "weekly": {"utilization": 20.0, "resets_at": "2026-05-04T00:00:00Z"},
    }
    windows = _parse_windows(data)
    assert len(windows) == 2
    assert windows[1].id == "seven_day"
