"""Tests for the store module."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "daemon"))

from tokenspyd.schema import ProviderSnapshot, Window
from tokenspyd import store as _store_module
from tokenspyd.store import write_state, read_state


def _sample_snapshots():
    return [
        ProviderSnapshot(
            id="codex",
            display_name="Codex",
            status="ok",
            windows=[
                Window(id="five_hour", label="5h session", used_pct=10.0,
                       resets_at="2026-04-30T20:00:00Z", window_seconds=18000),
            ],
            last_polled_at="2026-04-30T15:00:00Z",
            error=None,
        )
    ]


def test_write_state_creates_valid_json(tmp_path):
    state_path = tmp_path / "current.json"
    write_state(_sample_snapshots(), path=state_path)
    data = json.loads(state_path.read_text())
    assert data["schema_version"] == 1
    assert len(data["providers"]) == 1
    assert data["providers"][0]["id"] == "codex"


def test_write_state_atomic(tmp_path):
    state_path = tmp_path / "current.json"
    write_state(_sample_snapshots(), path=state_path)
    original = state_path.read_text()

    # A second write should replace atomically
    snapshots2 = [ProviderSnapshot(
        id="codex", display_name="Codex", status="network_error",
        windows=[], last_polled_at="2026-04-30T16:00:00Z", error="timeout"
    )]
    write_state(snapshots2, path=state_path)
    data = json.loads(state_path.read_text())
    assert data["providers"][0]["status"] == "network_error"
    # tmp file should not remain
    assert not state_path.with_suffix(".json.tmp").exists()


def test_read_state_missing_file(tmp_path):
    result = read_state(tmp_path / "nonexistent.json")
    assert result is None


def test_read_state_corrupt_file(tmp_path):
    bad = tmp_path / "current.json"
    bad.write_text("garbage{{{")
    result = read_state(bad)
    assert result is None


def test_snapshot_to_dict_roundtrip():
    snap = _sample_snapshots()[0]
    d = snap.to_dict()
    assert d["id"] == "codex"
    assert d["status"] == "ok"
    assert len(d["windows"]) == 1
    assert d["windows"][0]["used_pct"] == 10.0
