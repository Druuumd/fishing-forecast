"""Regression tests for best_hours: dawn/dusk/lunar peak windows."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest


def _snap(make_snapshot_fixture, *, sunrise=None, sunset=None, moon_phase=0.5, **kw):
    """Build a snapshot with explicit sunrise/sunset for the test."""
    return make_snapshot_fixture(
        sunrise=sunrise,
        sunset=sunset,
        moon_phase=moon_phase,
        **kw,
    )


def test_no_sunrise_or_sunset_skips_dawn_dusk(krasnoyarsk_service, make_snapshot_fixture):
    """Polar regions or missing data — no dawn/dusk emitted, but solunar
    lunar windows are still computed from ephemeris."""
    snap = _snap(make_snapshot_fixture, sunrise=None, sunset=None)
    out = krasnoyarsk_service.best_hours(snap)
    kinds = [w["kind"] for w in out]
    assert "dawn" not in kinds
    assert "dusk" not in kinds


def test_dawn_and_dusk_windows_always_returned(krasnoyarsk_service, make_snapshot_fixture):
    """When sunrise/sunset are present, dawn and dusk windows are always
    emitted regardless of lunar phase."""
    sr = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)  # 07:00 local in Krasnoyarsk
    ss = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)  # 21:00 local
    snap = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.25)
    out = krasnoyarsk_service.best_hours(snap)
    kinds = [w["kind"] for w in out]
    assert "dawn" in kinds
    assert "dusk" in kinds


def test_dawn_window_centered_on_sunrise(krasnoyarsk_service, make_snapshot_fixture):
    sr = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    ss = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)
    snap = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.25)
    out = krasnoyarsk_service.best_hours(snap)
    dawn = next(w for w in out if w["kind"] == "dawn")
    assert dawn["start"] == sr - timedelta(hours=1)
    assert dawn["end"] == sr + timedelta(hours=1)
    assert dawn["intensity"] == 1.0


def test_dusk_window_centered_on_sunset(krasnoyarsk_service, make_snapshot_fixture):
    sr = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    ss = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)
    snap = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.25)
    out = krasnoyarsk_service.best_hours(snap)
    dusk = next(w for w in out if w["kind"] == "dusk")
    assert dusk["start"] == ss - timedelta(hours=1)
    assert dusk["end"] == ss + timedelta(hours=1)


def test_solunar_major_windows_present(krasnoyarsk_service, make_snapshot_fixture):
    """Real solunar majors are always computed (transit always exists);
    intensity is what carries the syzygy/quarter distinction now."""
    sr = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    ss = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)
    snap = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.5,
                 day=date(2026, 7, 15))
    out = krasnoyarsk_service.best_hours(snap)
    assert any(w["kind"] == "lunar_major" for w in out)


def test_solunar_majors_2h_minors_1h(krasnoyarsk_service, make_snapshot_fixture):
    """Major windows are 2h wide (±1h around transit), minor 1h (±30min)."""
    sr = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    ss = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)
    snap = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.5,
                 day=date(2026, 7, 15))
    out = krasnoyarsk_service.best_hours(snap)
    for w in out:
        if w["kind"] == "lunar_major":
            assert w["end"] - w["start"] == timedelta(hours=2)
        elif w["kind"] == "lunar_minor":
            assert w["end"] - w["start"] == timedelta(hours=1)


def test_windows_sorted_chronologically(krasnoyarsk_service, make_snapshot_fixture):
    sr = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    ss = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)
    snap = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.5)
    out = krasnoyarsk_service.best_hours(snap)
    starts = [w["start"] for w in out]
    assert starts == sorted(starts)


def test_solunar_intensity_higher_near_full_than_quarter(krasnoyarsk_service, make_snapshot_fixture):
    """Full-moon solunar window has higher intensity than quarter-moon."""
    sr = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    ss = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)
    full = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.5,
                 day=date(2026, 5, 1))  # actual full moon date
    quart = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.25,
                  day=date(2026, 4, 24))  # near-first-quarter
    full_majors = [w for w in krasnoyarsk_service.best_hours(full) if w["kind"] == "lunar_major"]
    quart_majors = [w for w in krasnoyarsk_service.best_hours(quart) if w["kind"] == "lunar_major"]
    if not full_majors or not quart_majors:
        pytest.skip("ephem returned no majors for one of the dates")
    assert full_majors[0]["intensity"] > quart_majors[0]["intensity"]


def test_intensity_in_range(krasnoyarsk_service, make_snapshot_fixture):
    sr = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    ss = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)
    snap = _snap(make_snapshot_fixture, sunrise=sr, sunset=ss, moon_phase=0.0)
    out = krasnoyarsk_service.best_hours(snap)
    for w in out:
        assert 0.0 <= w["intensity"] <= 1.0
