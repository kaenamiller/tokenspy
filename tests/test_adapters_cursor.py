"""Tests for the Cursor adapter parser."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "daemon"))

from tokenspyd.adapters.cursor import _parse_windows, _iso_or_epoch


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "cursor_period_usage.json").read_text()
)


def test_parse_auto_and_api_windows():
    windows = _parse_windows(FIXTURE)
    assert len(windows) == 3

    auto = next(w for w in windows if w.id == "auto")
    assert auto.label == "Auto"
    assert auto.used_pct == pytest.approx(61.86, abs=0.1)
    assert auto.window_seconds == 2592000

    api = next(w for w in windows if w.id == "api")
    assert api.label == "API"
    assert api.used_pct == pytest.approx(60.53, abs=0.1)


def test_billing_cycle_end_parsed():
    windows = _parse_windows(FIXTURE)
    auto = next(w for w in windows if w.id == "auto")
    assert auto.resets_at is not None
    assert "T" in auto.resets_at
    assert auto.resets_at.endswith("Z")


def test_iso_or_epoch_string_passthrough():
    result = _iso_or_epoch("2026-05-01T00:00:00Z")
    assert result == "2026-05-01T00:00:00Z"


def test_iso_or_epoch_epoch_ms():
    ts_ms = 1777593600000  # 2026-05-01 00:00:00 UTC in ms
    result = _iso_or_epoch(ts_ms)
    assert "2026-05-01" in result


def test_iso_or_epoch_epoch_ms_string():
    # billingCycleEnd comes as a string containing epoch ms
    result = _iso_or_epoch("1777593600000")
    assert result is not None
    assert "2026-05-01" in result


def test_iso_or_epoch_none():
    assert _iso_or_epoch(None) is None


def test_fallback_legacy_shape():
    # Older response format before planUsage was added
    data = {
        "premiumRequestsTotal": 500,
        "premiumRequestsUsed": 87,
        "endOfPeriod": "2026-05-01T00:00:00.000Z",
    }
    windows = _parse_windows(data)
    auto = next(w for w in windows if w.id == "auto")
    assert auto.used_pct == pytest.approx(17.4, abs=0.1)


def test_parse_on_demand_spend_window():
    data = {
        **FIXTURE,
        "planUsage": {"totalPercentUsed": 8.68},
        "spendLimitUsage": {
            "individualLimit": 10000,
            "individualUsed": 0,
        },
    }
    windows = _parse_windows(data)
    assert any(w.id == "plan" for w in windows)
    on_demand = next(w for w in windows if w.id == "on_demand")
    assert on_demand.label == "On-demand spend"
    assert on_demand.used_pct == pytest.approx(0.0)
